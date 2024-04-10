import requests
import yaml
import json
import datetime as dt
import time
import os
import random
import urllib
import html
import re
import pytz
from email_validator import validate_email, EmailNotValidError
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from .logger import logger

#### --- For smaller or more general functions than those in funcs.py --- ####
## ----------------------------------------------------------------------------- ##
# Generic Utils/Wrappers #

## GET/POST request wrapper
def request(method:str, url:str, headers:dict, data=None, json=None, params=None, max_retries=2) -> requests.Response:
    """Generic wrapper for request with logging and retries."""

    format_string = "%Y-%m-%dT%H:%M:%S+00:00"
    attempts = 0

    while attempts <= max_retries:
        try:
            start_time = time.time()
            if method == "GET":
                response = requests.get(url, headers=headers, params=params)
            elif method == "POST":
                response = requests.post(url, json=json, headers=headers, params=params, data=data)
            end_time = time.time()

            log_data = {
                "url":{url},
                "response_code":{response.status_code},
                "time_taken":f"{end_time - start_time:.2f}"
            }
            logger.info(f"{method} {log_data['url']} -- ({log_data['response_code']}) -- {log_data['time_taken']}s")

            return response

        except Exception as e:
            error_data = {
                "url": url,
                "time": dt.datetime.now().strftime(format_string),
                "message": str(e)
            }
            wait_time = random.randint(1,4)
            logger.error(f"{method} {error_data['url']} -- ({error_data['message']}) -- Re-try in {wait_time}s")

            response = None
            time.sleep(wait_time)

        attempts += 1

    return response

# def track_api_calls():
#     """Keep track of/log how many calls to the survey monkey API the app has made in a given day."""
#     ## TO-DO -- SM API includes this information in the response headers

## Remove HTML tags, escape characters from text
def clean_field_text(text):

    unescaped_text = html.unescape(text)
    clean_text = re.sub(r'<.*?>', '', unescaped_text)
    clean_text = re.sub(r'\xa0|\\xa0', ' ', clean_text)

    return clean_text.strip()

## Load JSON -- handles/logs any errors gracefully and returns None:
def load_json(fp:str):
    """Wrapper to load a JSON file and check if it exists"""

    # depending on whether I run these functions in a notebook in notebooks/ or in main.py from the command line.
    if not os.path.isfile(fp):
        fp = os.path.join(os.path.abspath(os.path.pardir), fp)

    try:
        with open(fp, "r") as file:
            json_data = json.load(file)
        return json_data
    except Exception as e:
        logger.error(f"Error loading {fp}: {str(e)}.")
        return None

## Get current timestamp (in str ) in est
def est_now() -> str:
    est_tz = pytz.timezone('US/Eastern')
    utc_now = dt.datetime.utcnow()
    return utc_now.astimezone(est_tz).strftime("%Y-%m-%dT%H:%M:%S+00:00")



##  (TO-DO) -- Database functions in case we ever shift away from the flat JSON row file approach
# def load_to_db():
#     """Load SM responses to DB"""
# def query_db():
#     """Wrapper to query DB"""


## ----------------------------------------------------------------------------- ##
#  Small helper functions specific to the script

def load_config(fp='creds/api-key.yaml'):
    """Load information from config file"""

    # depending on whether I run these functions in a notebook in notebooks/ or in main.py from the command line.
    if not os.path.isfile(fp):
        fp = os.path.join(os.path.abspath(os.path.pardir), fp)

    with open(fp, "r") as file:
        data = yaml.full_load(file)
    return data

def get_email_address(resp:dict) -> str:
    """Get email address from a raw SurveyMonkey survey response (get_sm_survey_respones()).
    Assumes the email address question is the last one in the survey.
    Note that if the respondent ommitted an answer to a question, the SM API omits it from the data it sends you.
    In such cases, the last question included in raw_resp will *not* be the be the email question, but the last question which they answered.
    Returns None if the response does not contain an email address."""

        # Obsolete (for reading from a processed response object):
        # return [q['answers'][0]['text'] for q in raw_resp['questions']
        #                  if int(q['question_number']['sm']) == 82][0]

    try:
        last_question_answer = [q for p in resp['pages'] for q in p['questions']][-1]['answers'][0]
        return last_question_answer['text']
    except Exception:
        return None

def check_email_address(email_address=None, check_deliverability=True) -> tuple:
    """Wrapper to validate email address"""
    if email_address is not None:
        contacted_addresses = load_contacted_email_addresses()
        if email_address in contacted_addresses:
            return False, 'Email Already Contacted'
        else:
            try:
                validate_email(email_address, check_deliverability=check_deliverability)
                return True, "Valid Email"
            except EmailNotValidError as e:
                return False, str(e)
            except Exception as e:
                return False, str(e)
    else:
        return False, "Email Missing"

def load_processed_response_ids() -> list:
    """Load list of already processed response ids from database"""
    response_ids = []
    # with open("data/survey-responses-store.json", "r") as file:
    #     for line in file:
    #         row_data = json.loads(line.strip())
    #         response_ids.append(row_data['id'])

    return  response_ids

def load_contacted_email_addresses():
    """Load list of email addresses which have already been contacted.
    With load_processed_response_ids, prevents re-sending emails to people."""
    ## Ask client if they want to limit multiple responses to the same email address

    return []

## Obsolete given new db file
# def update_contacted_email_addresses(email_address:str) -> None:
#     """Update list of email addresses which have already been contacted. Prevents re-sending emails."""
#     fp = 'contacted_email_addresses.txt'
#     if not os.path.isfile(fp):
#         fp = os.path.join(os.path.abspath(os.path.pardir), fp)

#     with open(fp, 'a') as file:
#         file.write(email_address+'\n')

## ----------------------------------------------------------------------------- ##
# Functions for processing responses #

def get_collector_name(str):
    """Get name of the collector based on the collector ID"""


def check_unexpected_question_ids(sm_survey_response, combined_map) -> set:
    """Check if a survey monkey survey response has unexpected question ids"""
    new_resp_question_ids = set(q['id'] for p in sm_survey_response['pages'] for q in p['questions'])
    skills_matcher_ids = set(combined_map['skills-matcher'].keys())
    non_skills_matcher_ids = set(combined_map['non-skills-matcher'].keys())

    unexpected_ids = new_resp_question_ids.difference(non_skills_matcher_ids.union(skills_matcher_ids))

    return unexpected_ids


def create_cos_request_body(resp:dict) -> tuple:
    """Create a COS request body from a processed SurveyMonkey response dict"""

    cos_request_body = {'SKAValueList':
        [{'ElementId':q['question_id']['cos'],
         'DataValue':q['answers'][0]['id']['cos']}
         for q in resp['questions'] if q['question_type'] == 'skills-matcher']
        }

    return cos_request_body


def post_cos(processed_resp:dict, test_mode=False) -> dict:
    """POST a COS request from a processed SM survey response

    Args:

    processed_resp (dict): A survey monkey survey response dict translated by translate_sm_response()

    test_mode (bool): If True, forgoes calling the COS API and loads a local file with stored COS Responses
        - If the current response does not have a stored COS response in this file, returns {}

    """
    cos_response = {} # Setting default value for if there are any errors

    if test_mode:
        logger.debug("Loading cached COS responses.")
        fp = "data/temp_cos_response_objects.json"
        cos_responses = load_json(fp)
        if processed_resp['response_id'] not in cos_responses.keys():
            logger.warning(f"{processed_resp['response_id']} not in {fp} -- Setting cos_response = {{}}")
        else:
            cos_response = cos_responses[processed_resp['response_id']]
    else:
        try: # Create Request body
            cos_request_body = create_cos_request_body(processed_resp)
        except Exception as e:
            logger.error(f"{processed_resp['response_id']} -- Failed to create COS request body -- {e} -- Setting cos_response = {{}}")

        # POST to COS
        data = load_config()
        url = data['cos']['url']
        headers = data['cos']['headers']
        try:
            cos_response = request(method="POST",
                            url=url,
                            json=cos_request_body,
                            headers=headers)
            if cos_response.status_code != 200:
                logger.error(f"SM: {processed_resp['response_id']} -- POST {url} ({cos_response.status_code}) -- Setting cos_response = {{}}")
                cos_response = {}
            else: # Unpack response
                cos_response = cos_response.json()

        except Exception as e:
            logger.error(f"SM: {processed_resp['response_id']} -- POST {url} (None) -- {e} -- Setting cos_response = {{}}")

    return cos_response


## ----------------------------------------------------------------------------- ##
### Functions for composing and sending emails

## Formatting emails

def create_job_url(job_title:str,onet_code:str ) -> str:
    """Construct the URL to a job description page"""
    base_url = "https://www.careeronestop.org/Toolkit/Careers/Occupations/occupation-profile.aspx?"
    parameters = {
        "keyword": urllib.parse.quote(job_title),
        "location": "US",
        "lang": "en",
        "onetCode": onet_code
    }
    url_params = "&".join([f"{key}={value}" for key, value in parameters.items()])
    url = f'{base_url}{url_params}'
    return url
    # return f'<a href="{url}">{onet_code}</a>'

def load_email_text():
    """Load the text of the email message body"""

    fp = "modules/email_message.txt"
    if not os.path.isfile(fp):
        fp = os.path.join(os.path.abspath(os.path.pardir),fp)

    with open(fp, "r") as file:
        message_text = file.read()

    return message_text.replace('\n', '<br>')

def compose_email(cos_response:dict, max_recommendations=10) -> tuple:
    """
    Compose the HTML-formatted text of an email given a response object from CareerOneStop

    Args:

    cos_response (dict): Response from COS Skills Matcher API

    max_recommendations (int): Maximum number of jobs to include

    Returns:

    email_subject, email_body (tuple[str]): String tuple of email subject and body

    """

    ## Get Job recommendations from Response
    rec_list = []
    try:
        n_jobs_to_include = min(len(cos_response['SKARankList']), max_recommendations)
    except Exception:
        print(cos_response)
    for rec in cos_response['SKARankList'][:n_jobs_to_include]:
        cleaned_rec = {}
        cleaned_rec['Your Match Rank'] = rec['Rank']
        cleaned_rec['Job Title'] = rec['OccupationTitle']
        cleaned_rec['Typical Wages (Annual)'] = f"${rec['AnnualWages']:,.0f}"
        cleaned_rec['Typical Education'] = rec['TypicalEducation']
        # Create url (not embedded)
        cleaned_rec['Link'] = create_job_url(job_title=rec['OccupationTitle'],
                                        onet_code=rec['OnetCode'])
        rec_list.append(cleaned_rec)

    ## Format/Style HTML Table
    table_headers = rec_list[0].keys()
    table_html = "<table>"
    table_html += "<tr>"

    # Header Style
    header_style = "font-weight: bold; font-size: 20px;"
    for header in table_headers:
        table_html += f"<th style='{header_style}'>{header}</th>"
    table_html += "</tr>"

    # Cell Style
    cell_style = "font-weight: normal; font-size: 16px;"
    for rec in rec_list:
        table_html += "<tr>"
        for header in table_headers:
            table_html += f"<td style='{cell_style}'>{rec[header]}</td>"
        table_html += "</tr>"
    table_html += "</table>"

    ## Load introductory message
    message_text = load_email_text()

    ## Compose email body
    section_separator = "<br><hr><br>"
    message_style = "font-weight: bold; font-style: italic; font-size: 16px;"
    email_body = f"<div style=\"{message_style}\">{message_text}{section_separator}</div>{table_html}"

    ## Standard email subject text
    email_subject = "Work4Success: Your Results from the CWC Survey"

    return email_subject, email_body, table_html

def send_email(response_id:str, cos_response:dict, sender:str, app_password:str, recipient:str,
               server='smtp.gmail.com', port=587, test_mode=False) -> bool:
    """Send the email to a respondent's provided email (after it was validated and the request to COS successful)"""

    if not test_mode:

        email_subject, email_body, jobs_table = compose_email(cos_response)

        try:
            msg = MIMEMultipart()
            msg["Subject"] = email_subject
            msg.attach(MIMEText(email_body, 'html'))  # Use 'html' for HTML content or 'plain' for plain text.

            server = smtplib.SMTP(server, port)
            server.starttls()
            server.login(sender, app_password)
            server.sendmail(sender, recipient, msg.as_string())
            server.quit()

            contacted = True  # Email sent successfully
            logger.info(f"SM: {response_id} -- Sent ({recipient})")

        except Exception as e:
            logger.error(f"SM: {response_id} -- Failed send ({recipient}) -- ({str(e)})")
            contacted = False
    else:
        logger.debug(f"SM: {response_id} -- Test Mode -- Skipping send ({recipient})")
        contacted = True

    return contacted

