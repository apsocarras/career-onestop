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
from modules.utils import log_azure, load_config
from modules.utils import check_unexpected_question_ids, get_email_address, check_email_address, create_cos_request_body, post_cos
from modules.utils import compose_email, send_email
from modules.funcs import get_sm_survey_responses, combine_qa_keys, translate_sm_response


def main():

    ## GET new survey responses from SurveyMonkey 
    sm_survey_responses = get_sm_survey_responses()

    ## Process these survey responses 
    for resp in sm_survey_responses: 

        # Load translation map 
        combined_map = combine_qa_keys(fetch=False)

        # Check response versus translation map for unexpected question ids in sm_survey_responses 
        unexpected_question_ids = check_unexpected_question_ids(resp, combined_map)
        retries = 0
        while len(unexpected_question_ids) > 0 and retries <= 2: 
            log_azure(f"WARNING: Unexpected question ids in SM response: {resp['id']}: {unexpected_question_ids}. Refreshing question/answer key map.")
            # Update current version of translation map
            combined_map = combine_qa_keys(fetch=True)
            # Check for unexpected ids again
            unexpected_question_ids = check_unexpected_question_ids(resp, combined_map)
            retries += 1
        # If there are still unexpected ids after a refresh, skip this response
        if len(unexpected_question_ids) > 0:
            log_azure(f"WARNING: Unable to reconcile questions from SM response {resp['id']} with COS key. Skipping.")
            ## TO-DO: load response to "problem" table in database
            continue

        else:
            # Add information from combined map 
            resp = translate_sm_response(resp, combined_map) 
            
            # If the survey response has a valid email, create a COS request object and POST to COS Skills Matcher  
            email_address = get_email_address(resp)
            has_valid_email, error_message = check_email_address(email_address)
            cos_response = None
            if has_valid_email:
                cos_request_body = create_cos_request_body(resp)
                cos_response = post_cos(cos_request_body)                    
            else: 
                log_azure(f"INFO: {resp['id']} has invalid email address -- {error_message}. Skipping.")
                ## TO-DO: load response to "problem" table in database

            # Send email if COS response successful
            if cos_response is not None: 

                email_subject, email_body = compose_email(cos_response)
                send_email(subject=email_subject, 
                           message=email_body, 
                           sender=
                           email_address)
                

                



            




            
        

