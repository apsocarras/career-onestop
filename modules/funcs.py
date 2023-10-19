import requests 
import yaml
import json
import datetime as dt
import time
import os
import random
from azure.storage.blob import BlobServiceClient, BlobType
from email_validator import validate_email, EmailNotValidError
from bs4 import BeautifulSoup
from modules.utils import load_config, load_json, request, log_azure, clean_field_text
from modules.utils import get_email_address, check_email_address, load_processed_response_ids, post_cos

## --- For larger/core functions in the app  --- ## 

## GET/Load question-answer keys for SurveyMonkey Survey and CareerOneStop Skills Matcher
def get_qa_key(api=None, fetch=False) -> dict:
    """
    Load list of questions/answers from either the Survey Monkey API `/details` endpoint or from CareerOneStop SkillsMatcher. 

    Args: 

    api (str):   Must be one of 'sm' (for Skills Monkey Survey) or 'cos' (for CareerOneStop)

    fetch (bool):   Whether to GET new question/answer key from api or to just use locally saved copy (default is False). 

          If loading our cached copy fails, automatically set to True.

          If fetch == True:
            If the GET request fails, we use our cached copy.
            If the question/answer details have changed, we use the new version and update our cached copy. 
                Any such changes to the survey in either SurveyMonkey or CareerOneStop may break combine_qa_keys() and this app as a whole.            

        Note 500 requests/month limit to SM -- if going to use fetch option, may want to only do so periodically.

    """
    data = load_config()
    SM_DATA = data['sm']['copy-real']
    COS_DATA = data['cos']

    # Set SM vs. COS variables
    if api == "sm": 
        url = f"{SM_DATA['base_url']}/details"
        headers = SM_DATA['headers']
        cached_fp = "../data/real-survey/copy/copy-sm-survey-key.json"
    elif api == "cos":
        url = COS_DATA['url']
        headers = COS_DATA['headers']
        cached_fp = "../data/real-survey/copy/copy-cos-survey-key.json"

    else:
        raise Exception("`api` must be one of `sm` (SurveyMonkey) or `cos` (CareerOneStop)")
    
    # Load cached details 
    cached_key = load_json(cached_fp)
    if cached_key is None: 
        log_azure(f"WARNING: Loading {cached_fp} failed. Fetching new {api.upper()} key.")
        fetch = True

    ## Attempt Request (if fetch == True)
    fetched_key = None
    if fetch: 
        try: 
            response = request(url=url, headers=headers, method="GET")
            if response.status_code != 200:
                log_azure(f"WARNING: GET {api.upper()} survey details -- Response Code: {response.status_code} -- Proceeding with cached file: {cached_fp}")
            else: 
                fetched_key = response.json()
        except Exception as e: 
            log_azure(f"ERROR: GET {api.upper()} survey details -- Error: {str(e)} -- Proceeding with cached file: {cached_fp}")

    ## Return Block
    if fetched_key is None and cached_key is None:
        raise Exception(f"ERROR: Failed both to fetch new copy and to load cached copy of {api.upper()} Q/A key.")  
    elif fetched_key is None: 
        return cached_key
    elif fetched_key != cached_key: # This block will never run so long as one of 
        log_azure(f"WARNING: GET {api.upper()} survey details -- Fetched Q/A key conflicts with cached copy {cached_fp} -- Updating.")           
        with open(cached_fp, "w") as file: 
            json.dump(fetched_key, file)
        return fetched_key
    else: 
        log_azure(f"INFO: GET {api.upper()} survey details -- Fetched Q/A key matches cached copy {cached_fp}")
        return fetched_key

## Using keys from get_qa_key(), create translation map from Survey Monkey key to COS key 
def combine_qa_keys(fetch=False) -> dict: 
    """
    Creates translation map from SM to COS using the question/answer keys of each.
    
    Args: 

    fetch (bool): Setting for get_qa_key() -- whether to only load local cache of question/answer keys or to fetch new copies.
        This option is used in combine_qa_keys() within process_sm_responses(), if when a new SurveyMonkey response is retrieved there are unexpected question ids.
    
    """
    ## TO-DO: This function should be able to store and read specific timestamped versions of the translation map to be backwards compatible following any survey changes.

    # GET/Load answer keys 
    sm_key = get_qa_key("sm", fetch=fetch)
    cos_key = get_qa_key("cos", fetch=fetch)

    ## Prepare translation map between answer keys
    combined_map = {
        'non-skills-matcher':[], # not to send to COS (background questions)
        'skills-matcher':[], # to send to COS skills matcher 
    }

    ## Adding relevant SM information to map
    sm_question_number = 1
    for p in sm_key['pages']:
        for q in p['questions']:
        
            question_type = 'skills-matcher' if "skills matcher" in p['title'].lower()  else "non-skills-matcher" 
            
            answers = None  
            if 'choice' in q['family']: # single_choice, multiple_choice 
                # Main answer choices
                answers = [{'id':{'sm':a['id']}, 'text':{'sm':clean_field_text(a['text'])}} for a in q['answers']['choices']]
                # 'Other' option
                if 'other' in q['answers'].keys(): 
                    answers.append({
                        'id':{'sm':q['answers']['other']['id']},
                        'text':{'sm':clean_field_text(q['answers']['other']['text'])}
                        })
            elif q['family'] == 'datetime':
                answers = [{'id':{'sm':q['answers']['rows'][0]['id']},
                            'text':{'sm':clean_field_text(q['answers']['rows'][0]['text'])}}]

            combined_map[question_type].append({
                'question_id':{'sm':q['id']},
                'page_number': p['position'],
                'question_number':{'sm':sm_question_number}, # q['position'] gives the question's position on the current page, not its absolute number
                'question_family':q['family'],
                'question_text':{'sm':clean_field_text([h['heading'] for h in q['headings']][0])},
                'question_type':question_type,
                'answers':answers
            })

            sm_question_number += 1

    if len(combined_map['skills-matcher']) != len(cos_key['Skills']):
        error_text = f"ERROR: No. of skills-matcher questions retrieved from SM {len(combined_map['skills-matcher'])} doesn't match number in COS {len(cos_key['Skills'])}"
        log_azure(error_text)
        raise Exception(error_text)

    ## Add COS information
    for n in range(len(combined_map['skills-matcher'])): 
        cos_q = cos_key['Skills'][n]
        cos_answer_ids = [{'id':cos_q["DataPoint20"], 'text':cos_q['AnchorFirst']},
                          {'id':cos_q["DataPoint35"], 'text':cos_q['AnchorSecond']}, 
                          {'id':cos_q["DataPoint50"], 'text':cos_q['AnchorThrid']}, 
                          {'id':cos_q["DataPoint65"], 'text':cos_q['AnchorFourth']}, 
                          {'id':cos_q["DataPoint80"], 'text':cos_q['AnchorLast']}]

        combined_map['skills-matcher'][n]['question_id']['cos'] = cos_q['ElementId']
        combined_map['skills-matcher'][n]['question_number']['cos'] = n + 1 # correcting for 0 index in loop
        combined_map['skills-matcher'][n]['question_text']['cos'] = cos_q['Question']

        # Add cos answer ids and text 
        if len(combined_map['skills-matcher'][n]['answers']) != len(cos_answer_ids):
            error_text = f"ERROR: No. of answer options in SM question #{combined_map['skills-matcher'][n]['question_number']['sm']} != number of COS answer levels."
            log_azure(error_text)
            raise Exception(error_text)
        for m in range(len(combined_map['skills-matcher'][n]['answers'])):
            combined_map['skills-matcher'][n]['answers'][m]['id']['cos'] = cos_answer_ids[m]['id']
            combined_map['skills-matcher'][n]['answers'][m]['text']['cos'] = cos_answer_ids[m]['text']

    ## Casting question lists to dictionary, with keys being the survey monkey question ids, for easier lookup in translation
    # Making these lists to start with made the previous iterate/insertion step easier
    combined_map['skills-matcher'] = {q['question_id']['sm']:q for q in combined_map['skills-matcher']}
    combined_map['non-skills-matcher'] = {q['question_id']['sm']:q for q in combined_map['non-skills-matcher']}


    return combined_map

## GET all survey responses from Survey monkey API
def get_sm_survey_responses(per_page=100, start_created_at=None, status='completed', sort_by='date_modified', sort_order='DESC', minimum_minutes=5) -> list:
    """
    GET new survey responses from /surveys/{id}/responses/bulk

    Args: 

    per_page (int): Number of resources to return per page (response). Max of 100 allowed per page. 

    start_created_at (datetime.datetime): Only retrieve responses started after this date. e.g. 2023-10-01T02:20:44+00:00

    status (str): Status of the response: completed, partial, overquota, disqualified.

        'completed': The respondent answered all required questions they saw and clicked Done on the last page of the survey.
        'partial': The respondent entered at least one answer and clicked Next on at least one survey page, but didn't click Done on the last page of the survey.

    minimum_minutes (int): The required minimum number of minutes spent on the survey.

    sort_by (str): Field used to sort returned responses
    
    sort_order (str): Sort order: ASC or DESC

    """

    ## Configure GET Request 
    data = load_config()
    SM_DATA = data['sm']['copy-real']
    url = SM_DATA['base_url'] + f"/responses/bulk"
    
    params = {"per_page":per_page,
              "status":status,
              "total_time_taken":str(minimum_minutes),
              "total_time_units":"minute",
              "sort_by":sort_by, 
              "sort_order":sort_order}

    if isinstance(start_created_at, dt.datetime): # i.e. if not None and a valid datetime object
        try: 
            format_string = "%Y-%m-%dT%H:%M:%S+00:00"
            date_string = start_created_at.format(format_string)
            params['start_created_at'] = date_string
        except: 
            log_azure(f"WARNING: Improper datetime given for `start_created_at`. Skipping from GET {url}")

    ## GET Request 
    survey_responses = []
    processed_response_ids = load_processed_response_ids() # TO-DO: 

    # If all the survey responses in the current response page from SurveyMonkey API are new, need to also GET survey responses from the next page (if another page is available)
    # Triggers for the first GET request as well because survey_responses is empty

    while not any(resp['id'] in processed_response_ids for resp in survey_responses): 

        response = request(url=url, headers=SM_DATA['headers'], params=params, method="GET")
    
        # Error handling 
        error_message = 'Failed to retrieve SurveyMonkey response after multiple attempts'
        if response is None: 
            raise Exception(error_message)
        elif response.status_code != 200:
            raise Exception(error_message + f": {response.status_code}")
        else:
            try:          
                current_response_page = response.json()
                survey_responses.extend(current_response_page['data'])
            except: 
                raise Exception(f'Unable to extract SurveyMonkey Response JSON: {response.content}')
            
        # Checks for any additional pages listed in the current SM response page 
        if 'links' in current_response_page.keys() and 'next' in current_response_page['links'].keys():
            # URL for the next page, GET on the next loop
            url = current_response_page['links']['next']
        else: 
            break
            
    return survey_responses

## Add information from combined answer key to these responses
def translate_sm_response(resp:dict, combined_map:dict) -> dict: 
    """
    "Translate" a raw SM survey response from get_sm_survey_responses() to a combined response format
        - Adds combined question/answer information from both the SurveyMonkey and COS answer keys
    """

    resp_dict = {
    'response_id':resp['id'],
    'collector_id':resp['collector_id'], # TO-DO: write function to include collector name
    'questions':[] 
    }

    # Get question_answer key from current response
    resp_question_answers = {q['id']:q['answers'] for p in resp['pages'] for q in p['questions']}

    ## Add matching questions information from combined qa key 
    for q_map in list(combined_map['non-skills-matcher'].values()) + list(combined_map['skills-matcher'].values()):
        
        # If current question is omitted from the response, auto-fill from question answer key
        if q_map['question_id']['sm'] not in resp_question_answers.keys():
            q_map['auto_filled'] = True
            q_map['answers'] = [q_map['answers'][0]] if q_map['question_type'] == 'skills-matcher' else None\

        # If the answer key has answer choices listed for the question 
        elif q_map['answers'] is not None:    
            
            q_map_answer_key = {a['id']['sm']:a for a in q_map['answers']}

            resp_answers = [q_map_answer_key[a['choice_id']] 
                            if 'choice_id' in a.keys() 
                            else {'id':{'sm':a['other_id']}, 'text':{'sm':clean_field_text(a['text'])}}
                            for a in resp_question_answers[q_map['question_id']['sm']]]
            
            q_map['answers'] = resp_answers

        else: 
            q_map['answers'] = resp_question_answers[q_map['question_id']['sm']]
            for a in q_map['answers']: 
                if 'text' in a.keys():
                    a['text'] = clean_field_text(a['text'])
        
        resp_dict['questions'].append(q_map)

    return resp_dict








            