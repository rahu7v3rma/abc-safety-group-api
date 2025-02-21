import datetime
from typing import Optional

import pytz

from src.utils.log_handler import log


def convert_date(unix_time) -> str:
    """Function to convert date to string

    Args:
        unix_time (_type_): Timestamp in miliseconds

    Returns:
        str: Datetime converted to string in format yyyy-mm-dd
    """
    timestamp_milliseconds = unix_time

    timestamp_seconds = timestamp_milliseconds / 1000
    date_object = datetime.datetime.fromtimestamp(timestamp_seconds)

    formatted_date = date_object.strftime("%Y-%m-%d")

    return formatted_date


def convert_tz(
    original_time: datetime.datetime,
    tz: Optional[str] = "America/New_York",
) -> datetime.datetime:
    """Function to convert date to output timezone

    Args:
        original_time (datetime.datetime): Initial time
        tz (Optional[str], optional): timezone to be converted to. Defaults to "America/New_York".

    Returns:
        datetime.datetime: Out time with timezone conversion
    """  # noqa: E501
    if tz is None:
        tz = "America/New_York"  # Use the default timezone if none is provided
    try:
        if (
            original_time.tzinfo is None
            or original_time.tzinfo.utcoffset(original_time) is None
        ):
            original_time = original_time.replace(tzinfo=pytz.UTC)

        user_tz = pytz.timezone(tz)
        new_time = original_time.astimezone(user_tz)
        return new_time
    except Exception:
        # Log the exception along with the time and timezone details
        log.exception(
            "Failed to convert timezone for time "
            f'{original_time.strftime("%m/%d/%Y %-I:%M %p")} with timezone {tz}',  # noqa: E501
        )
    return original_time
