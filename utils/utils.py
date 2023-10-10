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

## GET request wrapper
def request(method:str, url:str, headers:dict, json=None, max_attempts=2):
    """Wrapper for request with logging and retries."""

    attempts = 0
    while attempts < max_attempts: 
        try:
            start_time = time.time()
            if method == "GET":
                response = requests.get(url, headers=headers)
            elif method == "POST":
                response = requests.post(url, json=json, headers=headers)
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
