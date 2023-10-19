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
from funcs.utils import load_config, load_json, request, log_azure, clean_field_text, get_email_address, check_email_address

## ------ MAIN FUNCTIONS IN APP ------- ## 

## GET/Load question-answer keys for SurveyMonkey Survey and CareerOneStop Skills Matcher
def get_qa_key(api=None, fetch=False) -> dict:
    """
    Load list of questions/answers from either the Survey Monkey API `/details` endpoint or from CareerOneStop. 

    Args: 

    api (str):   Must be one of 'sm' (for Skills Monkey Survey) or 'cos' (for CareerOneStop)

    fetch (bool):   Whether to GET new question/answer key from api or to just use locally saved copy (default is False). 

          If loading our cached copy fails, automatically set to True.

          If fetch == True:
            If the GET request fails, we use our cached copy.
            If the question/answer details have changed, we update our cached copy. Any such changes may break combine_qa_keys() and this app as a whole.            

        Note 500 requests/month limit to SM -- if going to use fetch option, may want to only do so periodically.

    """
    data = load_config('../creds/api-key.yaml')
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
    """Creates translation map from SM to COS using the question/answer keys of each.
    
    Args: 

    fetch (bool): Setting for get_qa_key() -- whether to only load local cache of question/answer keys or to fetch new copies.
    
    """

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
def get_sm_survey_responses(per_page=100, start_created_at=None, status='completed', sort_by='date_modified', sort_order='DESC',**params):
    """GET 100 most recent survey responses from /surveys/{id}/responses/bulk

    -The SM API returns survey responses in pages, up to 100 `per_page`.
        - Set the `sort_order` parameter to filter for responses after a certain date 

    Args: 

    per_page (int): Number of resources to return per page. Max of 100 allowed per page. 

    start_created_at (DateString): Only retrieve responses started after this date. e.g. 2023-10-01T02:20:44+00:00

    status (str): Status of the response: completed, partial, overquota, disqualified.

        'completed': The respondent answered all required questions they saw and clicked Done on the last page of the survey.
        'partial': The respondent entered at least one answer and clicked Next on at least one survey page, but didn't click Done on the last page of the survey.

    sort_by (str): Field used to sort returned responses
    
    sort_order (str): Sort order: ASC or DESC

    **params: Can accept other keyword arguments as listed in the SurveyMonkey API 
        (https://api.surveymonkey.com/v3/docs?shell#api-endpoints-get-surveys-id-responses-bulk)


    """

    data = load_config('../creds/api-key.yaml')
    SM_DATA = data['sm']['copy-real']
    url = SM_DATA['base_url'] + f"/responses/bulk"
    
    now = dt.datetime.utcnow()
    thirty_days_ago = (now - dt.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    default_params = {

        "per_page":"100", 
        "start_created_at":thirty_days_ago,
        "status":"completed",
        "sort_by":"date_modified", 
        "sort_order":"DESC"

    }

    for def_param in default_params.keys(): 
        if def_param not in params.keys(): 
            params[def_param] = default_params[def_param]     

    response = request(url=url, headers=SM_DATA['headers'], params=params, method="GET")
    response_json = response.json()

    return response_json

## Process these responses
def process_sm_responses(sm_survey_responses) -> list[dict]: 
    """Filter and process new SM survey responses from get_sm_survey_responses()

        - Checks for unexpected question ids vs. the combined Q/A key.
        - Checks against DB for already processed responses 
        - Checks if response includes valid email address (`has_valid_email()`)
        - Loads (raw) new responses into database (into 'processing' table) until they are finished
           - When these responses are successfully sent to COS and then emailed to user, they will be moved to main DB table.
    """

    ## -- Read list of already processed responses from database (TO-DO) -- ##
    # Database useful to check against repeated user email or IP + answers (avoid redundant emails), for retries of failures 

    placeholder_processed_response_ids = []
    ## -------------------------------------------------------------------- ## 

    # Create/load question answer/key map 
    combined_map = combine_qa_keys()

    ## 1.) Check for unexpected question ids in new responses vs. those in COS translation map. Attempt to refresh keys if there's a mismatch.
    # If there are still unexpected ids, there's probably an error with combine_qa_keys().
    new_resp_question_ids = set(q['id'] for resp in sm_survey_responses['data'] for p in resp['pages'] for q in p['questions']
                    if q['id'] not in placeholder_processed_response_ids)
    refreshes = 0
    while refreshes < 2: 
        skills_matcher_ids = set(combined_map['skills-matcher'].keys())
        non_skills_matcher_ids = set(combined_map['non-skills-matcher'].keys())
        expected_ids = skills_matcher_ids.union(non_skills_matcher_ids)
        unexpected_ids = new_resp_question_ids.difference(expected_ids)

        if len(unexpected_ids) > 0: 
            if refreshes == 0:  
                log_azure(f"WARNING: Unexpected question ids in SM responses: {unexpected_ids}. Refreshing question/answer key map.")
                combined_map = combine_qa_keys(fetch=True)
            elif refreshes == 1: 
                log_azure(f"ERROR: Unexpected question ids remain after refresh: {unexpected_ids}.") 
                raise Exception(f"ERROR: Unexpected question ids remain after refresh: {unexpected_ids}.")
            refreshes += 1
        else: 
            break 

    ## 2.) Filter for new survey responses (against 'sent'/'processed' tables in database)
    processed_responses = []
    for resp in sm_survey_responses['data']: 
        if resp['id'] not in placeholder_processed_response_ids: # and has_valid_email(resp check_deliverability=False) 
            # TO-DO: Do the email validation in the actual email sending function 
            resp_dict = {
            'response_id':resp['id'],
            'collector_id':resp['collector_id'], 
            'questions':[] 
            }

            ## Add questions information
            for p in resp['pages']:
                for q_resp in p['questions']:
                    # e.g. q_resp = {'id': '156451072', 'answers': [{'other_id': '1149785635', 'text': 'Online'}]}
                    # e.g. q_resp = {'id': '156451075', 'answers': [{'choice_id': '1149785640'}]}
                    # e.g. q_resp = {'id': '143922396', 'answers': [{'tag_data': [], 'text': '19977'}]}

                    # Match given question (q_resp) to question object in combined answer key (q_map)
                    question_type = 'non-skills-matcher' if q_resp['id'] in non_skills_matcher_ids else 'skills-matcher'
                    q_map = combined_map[question_type][q_resp['id']] # match based on question type and sm question id 

                    if q_map['answers'] is not None: # if the answer key has answer choices listed for the question
                         
                        q_map_answer_key = {a['id']['sm']:a for a in q_map['answers']}
                        
                        answers = [q_map_answer_key[a['choice_id']] 
                                   for a in q_resp['answers'] if 'choice_id' in a.keys()] \
                                + [{'id':{'sm':a['other_id']}, 'text':{'sm':a['text']}} 
                                   for a in q_resp['answers'] if 'other_id' in a.keys()] 
                    else:
                        answers = q_resp['answers']

                    resp_dict['questions'].append({'question_id':q_map['question_id'], 
                                                'page_number':q_map['page_number'],
                                                'question_number':q_map['question_number'], 
                                                'question_family': q_map['question_family'],
                                                'question_text':q_map['question_text'],
                                                'question_type':question_type, 
                                                'answers':answers})
                    

            ## Autofill any missing questions in the current response
            current_resp_question_ids = [q['question_id']['sm'] for q in resp_dict['questions']]
            for q_map in list(combined_map['non-skills-matcher'].values()) + list(combined_map['skills-matcher'].values()):
                if q_map['question_id']['sm'] not in current_resp_question_ids:

                    auto_fill_answer = [q_map['answers'][0]] if q_map['question_type'] == 'skills-matcher' else None # Auto fill with the beginner answer

                    fill_dict = {
                        'question_id':q_map['question_id'], 
                        'page_number':q_map['page_number'],
                        'question_number':q_map['question_number'], 
                        'question_family': q_map['question_family'],
                        'question_text':q_map['question_text'],
                        'question_type':q_map['question_type'], 

                        # Addressing omitted question 
                        'answers':auto_fill_answer,
                        'omitted':True
                    }

                    resp_dict['questions'].append(fill_dict)
        
            resp_dict['questions'] = sorted(resp_dict['questions'], key=lambda q:int(q['question_number']['sm']))

        processed_responses.append(resp_dict)

    ## -- 3. Write (raw) new responses to 'processing' table in DB (TO-DO)  -- ## 
    # load_to_db(...)
    ## -------------------------------------------------------------------- ## 

    return processed_responses

## Auto-fill answers in a processed response dict
# def auto_fill_answers(resp:dict) -> dict:
#     """Autofill the responses in a survey response from survey monkey"""

#     resp_copy = resp.copy()
#     resp_question_ids = [q['question_id'] for p in resp_copy['pages'] for q in p['questions']]

#     # Load stored key 
#     combined_map = combine_qa_keys()

#     for q_map in list(combined_map.values()): 
#         if q_map['question_id']['sm'] in resp_question_ids:
#             continue 
#         else: 
#             auto_fill_dict =  q_map.copy()
#             auto_fill_dict['answers'] = [q_map['answers'][0]]
#             auto_fill_dict['answers'][0]['auto_filled'] = True
            
#         resp_copy['questions'].append(auto_fill_dict)

#     return resp_copy


## POST these processed responses to the COS Skills Survey

def create_cos_request_body(resp:dict) -> tuple:
    """Create a COS request body from a processed SurveyMonkey response dict"""

    ## COS request object looks like: 
    # cos_request = {'SKAValueList':
    #             [{'ElementId':q['question_id']['cos'], 
    #             'DataValue':str(q['answers'][0]['id']['cos'])} for q in skills_matcher_questions.values()]}

    # Load combined answer key 
    combined_map = combine_qa_keys()

    # Create question-answer key of provided questions in processed survey response
    resp_map = {} # cos question_id : cos answer_id
    for q in resp['questions']:
        if q['question_type'] == 'skills-matcher':
            resp_map[q['question_id']['cos']] = q['answers'][0]['id']['cos']
 
    # Fill out request body using stored map and processed respsonse dict 
    cos_request_body = {'SKAValueList':[]}
    ommitted_questions = []
    for q_map in combined_map['skills-matcher'].values(): 
        # ElementId = COS question id 
        element_id = q_map['question_id']['cos'] 
        # If answer for question wasn't provided, autofill DataValue for question with lowest rank answer from stored key for the  question
        if element_id in resp_map.keys():
            data_value = str(resp_map[element_id])
        else: 
            ## TO-DO: do something with these auto-filled values -- return in tuple? 
            data_value = str(q_map['answers'][0]['id']['cos'])
            ommitted_questions.append()
        
        cos_request_body['SKAValueList'].append({'ElementId':element_id, 'DataValue':data_value})
    
    return cos_request_body
            

def post_cos(processed_sm_responses:list[dict]): 
    """Translate processed SM survey responses to COS POST objects, retrieve COS responses.
    Fills omitted skills response answers as 'Beginner' before sending to COS API."""

    # Load data for making POST requests 
    data = load_config('../creds/api-key.yaml')
    COS_DATA = data['cos']

    # Add COS request object and COS response to each dict in the processed_sm_responses  
    responses_copy = processed_sm_responses.copy()
    for resp in responses_copy:
        email_address = get_email(resp) 
        has_valid_email, error_message = check_email(email_address) 
        if has_valid_email: # tuple: bool, valid/error message
            cos_request = create_cos_request_body(resp)
            cos_response = request(method="POST", 
                            url=COS_DATA['url'],
                            json=cos_request, 
                            headers=COS_DATA['headers'])
            try: 
                cos_response = cos_response.json()
            except: 
                log_azure(f"WARNING: {resp['response_id']}, failed to unpack COS API response JSON ({cos_response.status_code}). Leaving as 'None'.")
                cos_response = None       
        else: 
            log_azure(f"WARNING: {resp['response_id']} contains invalid email address: {email_address} -- {error_message}. Skipping.")
            cos_request = None
            cos_response = None
        
        resp['cos_request'] = cos_request
        resp['cos_response'] = cos_response 

    return responses_copy





            