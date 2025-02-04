# FILE: /my-python-project/my-python-project/src/date_detection.py

import re
from datetime import datetime

def detect_dates(text):
    """
    Detects dates in the given text using regular expressions.

    Args:
        text (str): The text to search for dates.

    Returns:
        list: A list of detected date strings.
    """
    date_patterns = [
        r'\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b',  # DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        r'\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b',  # YYYY/MM/DD or YYYY-MM-DD or YYYY.MM.DD
        r'\b\d{1,2} \w+ \d{2,4}\b',              # DD Month YYYY
        r'\b\w+ \d{1,2}, \d{4}\b'                # Month DD, YYYY
    ]
    
    dates = []
    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        dates.extend(matches)
    
    return dates

def validate_date_format(date_string):
    """
    Validates the format of a date string.

    Args:
        date_string (str): The date string to validate.

    Returns:
        bool: True if the date format is valid, False otherwise.
    """
    for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y.%m.%d"]:
        try:
            datetime.strptime(date_string, fmt)
            return True
        except ValueError:
            continue
    return False