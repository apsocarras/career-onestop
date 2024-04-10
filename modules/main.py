import json

from .logger import logger, log_format
from .utils import load_config, est_now
from .utils import check_unexpected_question_ids, get_email_address, check_email_address, post_cos, send_email
from .funcs import get_sm_survey_responses, combine_qa_keys, translate_sm_response

def main():

    TEST_MODE = True # For purposes of testing without making any API calls
    CONFIG = load_config()
    SENDER_EMAIL = CONFIG['email']['shared-dil-account']['sender-email']
    APP_PASSWORD = CONFIG['email']['shared-dil-account']['app-password']

    DIVIDER = "\n" + '--------' * 15 + "\n"
    if TEST_MODE:
        log_format(DIVIDER)
        logger.debug("Running main.py in Test Mode")
    log_format(DIVIDER)

    ## GET new survey responses from SurveyMonkey
    sm_survey_responses = get_sm_survey_responses(test_mode=TEST_MODE)

    ## Process and store these survey responses
    failures = [] # for responses which the app fails to process
    successes = []
    with open("data/survey-responses.json", "a") as output_file:

        for resp in sm_survey_responses:

            logger.info(f"Processing SM Response #{resp['id']}")
            # Load translation map
            combined_map = combine_qa_keys(fetch=False)

            # Check response versus translation map for unexpected question ids in sm_survey_responses
            unexpected_question_ids = check_unexpected_question_ids(resp, combined_map)
            retries = 0
            while len(unexpected_question_ids) > 0 and retries <= 2:
                logger.warning(f"SM: {resp['id']} -- {len(unexpected_question_ids)} unexpected question ids: {unexpected_question_ids} -- Refreshing question/answer key map.")
                # Update current version of translation map
                combined_map = combine_qa_keys(fetch=True)
                # Check for unexpected ids again
                unexpected_question_ids = check_unexpected_question_ids(resp, combined_map)
                retries += 1

            # If there are still unexpected ids after retrying
            if len(unexpected_question_ids) > 0:
                (f"WARNING: Unable to reconcile questions from SM response {resp['id']} with COS key. Skipping.")
                ## TO-DO: load response to "problem" table in database
                # For now, save response to a separate .json row file

                fail_dict = {'id':resp['id'],
                             'date_added':est_now(),
                             'error_type':'unexpected_question_ids',
                             'data':{
                                 'raw':resp,
                                 'unexpected_questions':[unexpected_question_ids]
                                 }
                            }

                # Append to the problem responses file
                failures.append(fail_dict)

            # Process survey response
            else:
                processed_resp = translate_sm_response(resp, combined_map)
                email_address = get_email_address(resp)
                has_valid_email, error_message = check_email_address(email_address)

                # POST to COS and email recommended jobs
                contact_result = False
                rec_jobs = []
                if has_valid_email:
                    valid_status = "y"
                    cos_response = post_cos(processed_resp, test_mode=TEST_MODE)

                    # Email if POST successful
                    if cos_response != {}:

                        rec_jobs = [job['OccupationTitle'] for job in cos_response['SKARankList']]
                        logger.info(f"SM: {processed_resp['response_id']} -- {len(rec_jobs)} recommended jobs.")

                        contact_result = send_email(test_mode=TEST_MODE,
                                    response_id=processed_resp['response_id'],
                                    cos_response=cos_response,
                                    sender=SENDER_EMAIL,
                                    app_password=APP_PASSWORD,
                                    recipient=email_address)
                else:
                    valid_status = error_message
                    logger.warning(f"SM: {processed_resp['response_id']} has invalid email address ({email_address}) -- {error_message}. Skipping send.")

                ## Create and append response record to db file
                update_dict = {
                    "id": resp['id'],
                    "date_added": est_now(),
                    "raw": resp,
                    "processed":processed_resp,
                    "jobs":{"n":len(rec_jobs),"top":[]},
                    "email": {"address": email_address,
                              "valid_status":valid_status,
                              "contacted":contact_result},
                }
                if len(rec_jobs) > 0:
                    update_dict['jobs']['top'] = rec_jobs[:min(len(rec_jobs),10)]

                logger.info([{k:v} for k,v in update_dict.items() if k not in ('raw','processed')])
                output_file.write(json.dumps(update_dict) + '\n')

                log_format(DIVIDER)

    # Returning results for testing
    data = json.dumps({"successes":successes,"failures":failures})

    return data, 200

if __name__ == "__main__":
    main()









