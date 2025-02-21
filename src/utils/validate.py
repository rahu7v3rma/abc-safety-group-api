import re
from typing import Union

from src.utils.log_handler import log


def validate_email(email: str) -> Union[str, None]:
    """Function to validate an email

    Args:
        email (str): Email to be validated

    Returns:
        Union[str, None]: Returns None or the email if it is valid
    """
    if not email:
        return None

    regex = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b"
    try:
        if not re.fullmatch(regex, email):
            return None
        return email
    except Exception:
        log.exception("Failed to validate email")

    return None


def validate_phone_number(phone_number: str) -> Union[str, None]:
    """Function to validate a phone number

    Args:
        phone_number (str): phone number to be validated

    Returns:
        Union[str, None]: returns either the valid phone number or none
    """
    checked_phone_number = None

    if not phone_number:
        return None

    if not isinstance(phone_number, str):
        phone_number = str(phone_number)

    # Remove non-numeric characters
    phone_number = re.sub(r"\D", "", phone_number)

    try:
        checked_phone_number = str(int(phone_number))
    except ValueError:
        log.exception("Failed to convert phone number")
        return None
    return checked_phone_number
