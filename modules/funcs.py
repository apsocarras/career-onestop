import json
import datetime as dt

from .logger import logger
from .utils import load_config, load_json, request, clean_field_text
from .utils import load_processed_response_ids

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

    SM_DATA = data['sm']
    COS_DATA = data['cos']

    # Set SM vs. COS variables
    if api == "sm":
        url = f"{SM_DATA['base_url']}/details"
        headers = SM_DATA['headers']
        cached_fp = SM_DATA['survey-details-fp']
    elif api == "cos":
        url = COS_DATA['url']
        headers = COS_DATA['headers']
        cached_fp = COS_DATA['survey-details-fp']
    else:
        raise Exception("`api` must be one of `sm` (SurveyMonkey) or `cos` (CareerOneStop)")

    # Load cached details
    cached_key = load_json(cached_fp)
    if cached_key is None:
        logger.warning(f"Loading {cached_fp} failed. Fetching new {api.upper()} key.")
        fetch = True

    ## Attempt Request (if fetch == True)
    fetched_key = None
    if fetch:
        try:
            response = request(url=url, headers=headers, method="GET")
            if response.status_code != 200:
                logger.error(f"GET {api.upper()} survey details -- Response Code: {response.status_code} -- Proceeding with cached file: {cached_fp}")
            else:
                fetched_key = response.json()
        except Exception as e:
            logger.error(f"GET {api.upper()} survey details -- Error: {str(e)} -- Proceeding with cached file: {cached_fp}")

    ## Return Block
    if fetched_key is None and cached_key is None:
        raise Exception(f"ERROR: Failed both to fetch new copy and to load cached copy of {api.upper()} Q/A key.")
    elif fetched_key is None:
        return cached_key
    elif fetched_key != cached_key: # This block will never run so long as one of
        logger.warning(f"GET {api.upper()} survey details -- Fetched Q/A key conflicts with cached copy {cached_fp} -- Updating.")
        with open(cached_fp, "w") as file:
            json.dump(fetched_key, file)
        return fetched_key
    else:
        logger.info("GET {api.upper()} survey details -- Fetched Q/A key matches cached copy {cached_fp}")
        return fetched_key

## Using keys from get_qa_key(), create translation map from Survey Monkey key to COS key
def combine_qa_keys(fetch=False) -> dict:
    """
    Creates translation map from SM to COS using the question/answer keys of each.

    Args:

    fetch (bool): Setting for get_qa_key() -- whether to only load local cache of question/answer keys or to fetch new copies.
        Used if when a new SurveyMonkey response is retrieved there are unexpected question ids.

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

            answers = [] # previously answers = None messed with searching arrays
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
        logger.error(error_text)
        # raise Exception(error_text)

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
            error_text = f"Number of answer options in SM question #{combined_map['skills-matcher'][n]['question_number']['sm']} != number of COS answer levels."
            logger.error(error_text)
            # raise Exception(error_text)
        for m in range(len(combined_map['skills-matcher'][n]['answers'])):
            combined_map['skills-matcher'][n]['answers'][m]['id']['cos'] = cos_answer_ids[m]['id']
            combined_map['skills-matcher'][n]['answers'][m]['text']['cos'] = cos_answer_ids[m]['text']

    ## Casting question lists to dictionary, with keys being the survey monkey question ids, for easier lookup in translation
    # Making these lists to start with made the previous iterate/insertion step easier
    combined_map['skills-matcher'] = {q['question_id']['sm']:q for q in combined_map['skills-matcher']}
    combined_map['non-skills-matcher'] = {q['question_id']['sm']:q for q in combined_map['non-skills-matcher']}


    return combined_map

## GET all survey responses from Survey monkey API
def get_sm_survey_responses(per_page=100,
                            start_created_at=None,
                            status='completed',
                            sort_by='date_modified',
                            sort_order='DESC',
                            minimum_minutes=5,
                            test_mode=False) -> list:
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

    test_mode (bool): Whether to load a cached copy of its typical output for testing purposes and to reduce the number of calls to the SM API.

    """

    survey_responses = []
    processed_response_ids = load_processed_response_ids()

    if test_mode:
        fp = "data/test_mode_sm_survey_responses.json"
        logger.debug(f"Loading cached {fp}")
        survey_responses = load_json(fp)
    else:
        data = load_config()
        SM_DATA = data['sm']
        url = SM_DATA['base_url'] + "/responses/bulk"

        params = {"per_page":str(per_page),
                  "status":status,
                  "total_time_min":str(minimum_minutes),
                  "total_time_units":"minute",
                  "sort_by":sort_by,
                  "sort_order":sort_order}
        
        print(params)

        if isinstance(start_created_at, dt.datetime): # i.e. if not None and a valid datetime object
            try:
                format_string = "%Y-%m-%dT%H:%M:%S+00:00"
                date_string = dt.datetime.strftime(start_created_at, format=format_string)
                params['start_created_at'] = date_string
            except:
                logger.warning(f"Improper datetime given for `start_created_at`. Skipping from GET {url}")

        ## GET Request
        while not any(resp['id'] in processed_response_ids for resp in survey_responses):
            # ^^ If all the survey responses in the current response page from SurveyMonkey API are new, need to also GET survey responses from the next page (if another page is available)
            # Triggers for the first GET request as well because survey_responses is empty

            response = request(url=url, headers=SM_DATA['headers'], params=params, method="GET")

            error_message = 'Failed to retrieve SurveyMonkey response after multiple attempts'
            if response is None:
                logger.error(error_message)
                raise Exception(error_message)
            elif response.status_code != 200:
                logger.error(error_message)
                raise Exception(error_message + f" (Status: {response.status_code})")
            else:
                current_response_page = response.json()
                survey_responses.extend(current_response_page['data'])

            # Checks for any additional pages listed in the current SM response page
            if 'links' in current_response_page.keys() and 'next' in current_response_page['links'].keys():
                # URL for the next page, GET on the next loop
                url = current_response_page['links']['next']
            else:
                break

    ## Remove from the retrieved list any responses which were already processed
    survey_responses = [resp for resp in survey_responses if resp['id'] not in processed_response_ids]
    if len(survey_responses) == 0:
        logger.info('No new survey responses.')

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
            q_map['answers'] = [q_map['answers'][0]] if q_map['question_type'] == 'skills-matcher' else None

        # If the answer key has answer choices listed for the question
        elif len(q_map['answers']) > 0:

            q_map_answer_key = {a['id']['sm']:a for a in q_map['answers']}
            answers = []

            for a in resp_question_answers[q_map['question_id']['sm']]:
                if 'choice_id' in a.keys():
                    answers.append(q_map_answer_key[a['choice_id']])
                elif 'other_id' or 'row_id' in a.keys():
                    # These questions have text in them which we need to clean, so treated differently from 'choice_id'
                    alt_id = 'other_id' if 'other_id' in a.keys() else 'row_id'
                    answers.append({'id':{'sm':a[alt_id]}, 'text':{'sm':clean_field_text(a['text'])}})
                else:
                    logger.warning(f"New kind of question and answer was added ({a})-- survey must have been changed")
                    answers.append(a)

            q_map['answers'] = answers

        else:
            q_map['answers'] = resp_question_answers[q_map['question_id']['sm']]
            for a in q_map['answers']:
                if 'text' in a.keys():
                    a['text'] = clean_field_text(a['text'])

        resp_dict['questions'].append(q_map)

    return resp_dict
