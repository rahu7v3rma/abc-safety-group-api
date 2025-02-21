import datetime
import os
from typing import Union

from jose import jwt


def generate_token(user_id: str) -> str:
    """Function to generate a session id from a user_id, creates a jwt token

    Args:
        user_id (str): user id of the user

    Returns:
        str: returns jwt token
    """
    jwt_token = jwt.encode(
        claims={
            "user_id": user_id,
            "createdAt": str(datetime.datetime.utcnow()),
        },
        key=os.getenv("JWT_SECRET", "secret"),
        algorithm="HS256",
    )

    return jwt_token


def decode_token(session_id: str) -> Union[dict, None]:
    """Function to decode session id of user

    Args:
        sessionId (str): session id from user session

    Returns:
        str: returns a dict of {user_id: str}
    """
    user = jwt.decode(
        token=session_id,
        key=os.getenv("JWT_SECRET", "secret"),
        algorithms=["HS256"],
    )

    return user
