from typing import Optional, Union

from src import log, redis_client
from src.utils.token import decode_token, generate_token


def create_session(user_id: str, expiry: int = 259200) -> Union[str, None]:
    """Function to create user session in redis

    Args:
        user_id (str): user id of user

    Returns:
        Union[str, None]: returns session id or none
    """
    try:
        token = generate_token(user_id=user_id)
        redis_client.set_key(key=token, token=user_id, ex=expiry)

        return token

    except Exception:
        log.exception(f"Failed to create session for user {user_id}")
    return None


def get_session(session_id: Optional[str] = None) -> Union[str, None]:
    """Function to get user session from redis

    Args:
        session_id (str): session id

    Returns:
        Union[str, None]: returns user id from session or none
    """
    if not session_id:
        return None
    try:
        session = redis_client.get_key(session_id)
        if session:
            decoded_session = decode_token(session_id=session_id)
            if decoded_session:
                return decoded_session["user_id"]
            return None
    except Exception:
        log.exception(f"Failed to get session for session_id {session_id}")
    return None


def delete_session(session_id: str) -> bool:
    """Function to delete user session id from redis

    Args:
        session_id (str): session id

    Returns:
        bool: returns bool true or false if it was successful
    """
    try:
        session = redis_client.get_key(session_id)
        if session:
            redis_client.delete_key(session_id)
            return True
    except Exception:
        log.exception(f"Failed to delete session for session_id {session_id}")
    return False
