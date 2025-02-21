import os
import random
import string
from typing import Optional


def generate_random_code(length: int = 10) -> str:
    """Function to generate random string

    Args:
        length (int, optional): Length or string to generate. Defaults to 10.

    Returns:
        str: Returns random string on n length
    """
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def generate_random_certificate_number(
    length: int = 10,
    course_code: Optional[str] = None,
) -> str:
    """Function to generate random certificate number

    Args:
        length (int, optional):  Length or string to generate. Defaults to 10.
        course_code (Optional[str], optional): Course code of course if provided. Defaults to None.

    Returns:
        str: Returns certificate number
    """  # noqa: E501
    joined = []
    provider_id = os.getenv("COURSE_PROVIDER_ID", "")
    if provider_id:
        joined.append(provider_id)
    if course_code:
        joined.append(course_code)

    characters = string.ascii_letters + string.digits
    chars = "".join([random.choice(characters) for _ in range(length)])
    if chars:
        joined.append(chars)

    return "".join(joined)
