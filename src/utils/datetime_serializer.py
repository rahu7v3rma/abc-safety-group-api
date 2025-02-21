from datetime import datetime
from typing import Union


def datetime_serializer(o: datetime) -> Union[str, None]:
    """Function to serialize datetime for json dump

    Args:
        o (datetime): datetime to be converted

    Returns:
        Union[str, None]: datetime conversion
    """
    if isinstance(o, datetime):
        return o.__str__()
