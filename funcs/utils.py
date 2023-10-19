import requests 
import yaml
import json
import datetime as dt
import time
import os
import random
import urllib
from azure.storage.blob import BlobServiceClient, BlobType
from email_validator import validate_email, EmailNotValidError
from bs4 import BeautifulSoup
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText



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
        # log_azure(f"INFO: resp {processed_response['response_id']} is missing email address")
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
        return False, "Email Missing (see get_email())"

# def track_api_calls():
#     """Keep track of/log how many calls to the survey monkey API the app has made in a given day.""" 
#     ## TO-DO -- SM API includes this information in the response headers

## ----------------------------------------------------------------------------- ## 
### Functions for sending and composing emails

## Formatting emails 

def create_url(job_title:str,onet_code:str ) -> str:
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

def compose_email(cos_response:dict) -> tuple[str]:
    """
    Compose the HTML-formatted text of an email given a response object from CareerOneStop
    
    Args: 

    cos_response (dict): Response from COS Skills Matcher API 

    Returns: 

    email_subject, email_body (tuple[str]): String tuple of email subject and body  
    
    """ 
    
    ## Get Job recommendations from Response
    rec_list = []
    for rec in cos_response['SKARankList']: 
        cleaned_rec = {}
        cleaned_rec['Your Match Rank'] = rec['Rank'] 
        cleaned_rec['Job Title'] = rec['OccupationTitle']
        cleaned_rec['Typical Wages (Annual)'] = f"${rec['AnnualWages']:,.0f}"
        cleaned_rec['Typical Education'] = rec['TypicalEducation']
        # Create url (not embedded)
        cleaned_rec['Link'] = create_url(job_title=rec['OccupationTitle'], 
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





# Elastic Email API Approach
# class ApiClient:
#     apiUri = 'https://api.elasticemail.com/v2'

#     def __init__(self, api_key):
#         self.apiKey = api_key

#     def Request(self, method, url, data):
#         data['apikey'] = self.apiKey
#         if method == 'POST':
#             result = requests.post(f'{self.apiUri}{url}', data=data)
#         elif method == 'PUT':
#             result = requests.put(f'{self.apiUri}{url}', data=data)
#         elif method == 'GET':
#             result = requests.get(f'{self.apiUri}{url}', params=data)

#         jsonMy = result.json()

#         if jsonMy['success'] is False:
#             return jsonMy['error']

#         return jsonMy['data']

# def Send(subject, EEfrom, fromName, to, bodyHtml, bodyText, isTransactional, api_key):
#     client = ApiClient(api_key)
#     return client.Request('POST', '/email/send', {
#         'subject': subject,
#         'from': EEfrom,
#         'fromName': fromName,
#         'to': to,
#         'bodyHtml': bodyHtml,
#         'bodyText': bodyText,
#         'isTransactional': isTransactional
#     })



def email_results(processed_sm_response:dict, max_recommendations:10):
    """Email recipients with their Skills Matcher results.""" 
    
    with open('../creds/api-key.yaml', 'r') as file: 
        data = yaml.full_load(file)['elastic-email']['shared-account']

    APP_PASSWORD = data['app-password']
    API_KEY = data['ee-api-key']
    SENDER_EMAIL = data['sender-email']
    RECEIVER_EMAIL = get_email(processed_sm_response)

    # general email settings 
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    EMAIL_SUBJECT = f'Your survey result for {dt.datetime.now().strftime("%B %d, %Y")}'

    # Extract and format data
    cos_response = processed_sm_response['cos_response']
    rec_list = cos_response['SKARankList']
    rename_keys_map = {'Rank': 'Your Match Rank', 
                    'OccupationTitle': 'Occupation Title', 
                    'AnnualWages': 'Average Wages (Annual)', 
                    'TypicalEducation': 'Typical Education'
                    }
    for rec in rec_list[:max_recommendations]:
        # Set occupation title to hyperlink
        rec['OccupationTitle'] = create_hyperlink(rec)
        # Drop redundant field (used to create the hyperlink)
        rec.pop('OnetCode')
        # Format wages 
        rec['AnnualWages'] = f"${rec['AnnualWages']:,.0f}"
        # Rename columns
        for k,v in rename_keys_map.items(): 
            rec[v] = rec.pop(k) # rename the key 
        
    ## Format HTML table 
    column_alignments = {
        "Your Match Rank": "center",
        "Occupation Title": "left",
        "Average Wages (Annual)": "right",
        "Typical Education": "left",
        "Outlook": "left"
    }

    table = tabulate(
        rec_list,
        headers="keys",
        tablefmt="html",
        colalign=[column_alignments[col] for col in column_alignments.keys()]
    )

    ## Styling the table 
    table_headers = column_alignments.keys()
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

    # Message Style
    message_style = "font-weight: normal; font-size: 16px;"

    # Use the table_html in your email body
    message = f'<div style="{message_style}">Your customized top 20 suggestion list is as follows:</div>\n\n{table_html}'

    # # Send the Email
    # result = Send(EMAIL_SUBJECT,
    #             SENDER_EMAIL,
    #             "Tech Impact",
    #             RECEIVER_EMAIL,
    #             f"<h1>{message}</h1>",
    #             f"{message}",
    #             True,
    #             API_KEY)
    # print(result)
    



