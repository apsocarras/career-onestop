import logging

LOG_FILE = "logs/log_file.txt"


## Actual Logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

## For writing formatting text to the logfile for enhanced human readability
def log_format(text:str):
    """Writes any string to the log file and console without additional logger formatting."""
    with open(LOG_FILE, "a") as file:
        file.write(str(text) + "\n")
    print(str(text) + "\n")