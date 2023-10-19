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
from azure.storage.blob import BlobServiceClient, BlobType
from email_validator import validate_email, EmailNotValidError
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

#### --- For smaller or more general functions than those in funcs.py --- ####


## -- Cloud storage and logging -- ## 
# This is set currently to Azure but could change 
# We would have more sophisticated logging in production, 
# e.g. use a dedicated logging service or not just uploading to a bucket, 
# use multiple logfiles in a naming system, different logfiles for type of log data,
# logging alerts for certain kinds of log events and messages, etc.

# AZ_CONNECTION_STR = data['az']['connection-str']
# AZ_CONTAINER_NAME = data['az']['container-name']

# blob_service_client = BlobServiceClient.from_connection_string(AZ_CONNECTION_STR)
# container_client = blob_service_client.get_container_client(AZ_CONTAINER_NAME)
log_file = "logfile.txt" 

## Any files in the script which are currently being read locally (from within app environment) might be read from cloud storage instead.
## A cloud copy of each file should be maintained, at least. 

## Logging wrapper 
def log_azure(log_data, log_file=log_file):
    print(log_data)
    return None # dummy function placeholder for testing until logging is configured 
    ## TO-DO: Logger should automatically add timestamp to log_data by default.
    """Log to Azure blob -- appends to logfile if it exists already."""
    # Check if log_file exists in container
    blob_client = container_client.get_blob_client(log_file)
    if not blob_client.exists():
        blob_client.upload_blob(log_data, blob_type=BlobType.AppendBlob)
    else:
        # Append the log data to the existing blob
        blob_properties = blob_client.get_blob_properties()
        offset = blob_properties.size
        blob_client.upload_blob(log_data, blob_type=BlobType.AppendBlob, length=len(log_data), offset=offset)

## ----------------------------------------------------------------------------- ## 
# Generic Utils/Wrappers # 

## GET request wrapper
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
                "time":{dt.datetime.now().strftime(format_string)}, 
                "response_code":{response.status_code}, 
                "time_taken":f"{end_time - start_time:.2f}"
            }
            log_azure(f"INFO: {method} {log_data['url']} -- {log_data['response_code']} -- {log_data['time_taken']} -- {log_data['time']}")

            return response

        except Exception as e:
            error_data = {
                "url": url,
                "time": dt.datetime.now().strftime(format_string),
                "message": str(e)
            }
            wait_time = random.randint(1,4)
            log_azure(f"ERROR: {method} {error_data['url']} -- {error_data['message']} -- {error_data['time']} -- Re-try in {wait_time} seconds.s")

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
def load_json(file_path:str): 
    """Wrapper to load a JSON file and check if it exists"""
    try: 
        with open(file_path, "r") as file: 
            json_data = json.load(file)
        return json_data
    except Exception as e: 
        log_azure(f"ERROR loading {file_path}: {str(e)}.")
        return None    

## Load to DB (TO-DO)
def load_to_db():
    """Load SM responses to DB"""

## Query DB 
def query_db(): 
    """Wrapper to query DB"""


## ----------------------------------------------------------------------------- ## 
#  Small helper functions specific to the script 

def load_config(fp='../creds/api-key.yaml'): 
    """Load information from config file"""
    with open(fp, "r") as file:
        data = yaml.full_load(file)
    return data 

def get_email_address(processed_response:dict) -> str:
    """Get email address from SurveyMonkey survey response. Assumes email is last question in the survey. Returns None if email is not provided."""
    try: 
        email_address = processed_response['questions'][-1]['answers'][0]['text']
        return email_address
    except Exception as e:
        return None
    
def check_email_address(email_address=None, check_deliverability=True) -> tuple[bool,str]:
    """Wrapper to validate email address"""
    if email_address is not None:
        try: 
            validate_email(email_address, check_deliverability=check_deliverability)
            return True, "Valid Email"
        except EmailNotValidError as e: 
            return False, str(e)
    else:
        return False, "Email Missing"
    

def load_processed_response_ids():
    """Load list of already processed response ids from database"""
    return ['placeholder_dummy_value'] # TO-DO

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

    cos_request_body = {'SKAValueList':[{'ElementId':q['question_id']['cos'],
                                         'DataValue':q['answers'][0]['id']['cos']}]
                        for q in resp['questions'] if q['question_type'] == 'skills-matcher'}

    return cos_request_body


def post_cos(cos_request_body:dict) -> dict: 
    """POST a COS request body from create_cos_request_body()"""
    
    # Load data for making POST requests 
    data = load_config()
    
    cos_response = request(method="POST", 
                        url=data['cos']['url'],
                        json=cos_request_body, 
                        headers=data['cos']['url'])
    
    # Attempt to extract JSON Response Data 
    try: 
        cos_response = cos_response.json()
    except: 
        log_azure(f"WARNING: {cos_response['response_id']}, failed to unpack COS API response JSON ({cos_response.status_code}). Leaving as 'None'.")
        cos_response = None       

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

def compose_email(cos_response:dict, max_recommendations=10) -> tuple[str]:
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
    n_jobs_to_include = min(len(cos_response['SKARankList']), max_recommendations) 
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
    with open("../funcs/email_message_text.txt", "r") as file: 
        message_text = file.read()
    message_text = message_text.replace('\n', '<br>')

    ## Compose email body 
    section_separator = "<br><hr><br>"
    message_style = "font-weight: bold; font-style: italic; font-size: 16px;"
    email_body = f"<div style=\"{message_style}\">{message_text}{section_separator}</div>{table_html}"

    ## Standard email subject text 
    email_subject = "Work4Success: Your Results from the CWC Survey"

    return email_subject, email_body

def send_email(subject, message, sender, app_password, recipient, server='smtp.gmail.com', port=587):
    """Send the email to a respondent's provided email (after it was validated and the request to COS successful)"""
    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg.attach(MIMEText(message, 'html'))  # Use 'html' for HTML content or 'plain' for plain text.

    server = smtplib.SMTP(server, port)
    server.starttls()
    server.login(sender, app_password)
    server.sendmail(sender, recipient, msg.as_string())
    server.quit()


