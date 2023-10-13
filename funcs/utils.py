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
# Generic Utils # 

## GET request wrapper
def request(method:str, url:str, headers:dict, data=None, json=None, params=None, max_retries=2):
    """Wrapper for request with logging and retries."""

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
                "time":{dt.datetime.now()}, 
                "response_code":{response.status_code}, 
                "time_taken":f"{end_time - start_time:.2f}"
            }
            log_azure(f"INFO: {method} {log_data['url']} -- {log_data['response_code']} -- {log_data['time_taken']} -- {log_data['time']}")

            return response

        except Exception as e:
            error_data = {
                "url": url,
                "time": dt.datetime.now(),
                "message": str(e)
            }
            wait_time = random.randint(1,4)
            log_azure(f"ERROR: {method} {error_data['url']} -- {error_data['message']} -- {error_data['time']} -- Re-try in {wait_time} seconds.s")

            if attempts == 2: 
                raise Exception(e)

            response = None
            time.sleep(wait_time)
        
        attempts += 1

    return response 

## Remove HTML tags, escape characters from text 
def clean_field_text(text):
    # Parse the HTML using BeautifulSoup
    soup = BeautifulSoup(text, 'html.parser')
    
    # Extract the text without HTML tags
    clean_text = soup.get_text()
    
    # Remove unicode escape characters 
    clean_text = clean_text.replace(u'\\xa0', u' ')

    # Strip whitespaec
    clean_text = clean_text.strip()
    
    return clean_text

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

def load_config(): 
    """Load information from config file"""
    with open("api-key.yaml", "r") as file:
        data = yaml.full_load(file)
    return data 

def has_valid_email(sm_survey_response:dict, check_deliverability=False) -> bool: 
    """Check if SM survey response includes a valid email address in the email question.
    Use to skip a response in process_sm_responses().

    Args: 

    sm_survey_response (dict): The Survey Response object from Survey monkey 

    email_question_id (str): The question id for the email question in the SM answer key. 

    """
    # Identify the question_id of the email question in the answer key  
    email_question_id = '145869785' # [q['question_id'] for q in combined_map['non-skills-matcher'] 
                                    # if 'email' in q['question_text'].lower()][0]
    
    # Check if sm_response contains the email question (if any question is ommitted, the respondent left it blank)      
    questions = [q for p in sm_survey_response['pages'] for q in p['questions']]
    if not any(q['id'] == email_question_id for q in questions): 
        return False 
    
    # Validate email if one was provided 
    email_address = [q for q in questions if q['id'] == email_question_id][0]['answers'][0]['text']
    try:
        validate_email(email_address, check_deliverability=check_deliverability)
        return True
    except EmailNotValidError as e:
        log_azure(f"WARNING: {sm_survey_response['id']} contains invalid email address: {email_address} -- {str(e)}. Skipping.")
        ## TO-DO: Add further processing logic and logs based on error message -- e.g. 'The email address contains invalid characters before the @-sign'  
        return False 

def track_api_calls():
    """Keep track of/log how many calls to the survey monkey API the app has made in a given day.""" 
    ## TO-DO -- SM API includes this information in the response headers
