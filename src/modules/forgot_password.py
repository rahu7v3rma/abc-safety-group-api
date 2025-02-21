import os
from typing import Tuple, Union

from jose import jwt

from src import log, redis_client


def create_reset(
    email: str,
    user_id: str,
    ex: int,
) -> Union[Tuple[Union[str, None], str], None]:
    """Function to create reset code

    Args:
        email (str): email of the user being reset
        user_id (str): user id for the user being reset
        ex (int): expiration time in seconds

    Returns:
        str: returns redis key
    """
    try:
        try:
            jw = jwt.encode(
                claims={
                    "email": email,
                },
                key=os.getenv("JWT_SECRET", ""),
                algorithm="HS256",
            )
        except Exception:
            log.exception(f"Failed to create JWT for user {user_id}")
            return

        return redis_client.set_key(f"forgot_{email}", jw, ex), jw
    except Exception:
        log.exception(f"Failed to create reset code for user {user_id}")


def get_reset(email: str) -> Union[str, None]:
    """Function to get reset code from redis

    Args:
        email (str): Email of user to get the belonging key to

    Returns:
        str: Key from redis
    """
    try:
        return redis_client.get_key(f"forgot_{email}")
    except Exception:
        log.exception(f"No reset code found for {email}")


def read_jwt(token: str):  # noqa: ANN201
    """Function to decode a JWT Token

    Args:
        token (str): Token to be decoded

    Returns:
        str: A decoded JWT in str format
    """
    try:
        return jwt.decode(
            token=token,
            key=os.getenv("JWT_SECRET", ""),
            algorithms=["HS256"],
        )
    except Exception:
        log.exception(
            f"Failed to decode JWT Token during password reset. {token}",
        )


def remove_reset(email: str) -> Union[int, None]:
    """Function to remove reset from redis

    Args:
        email (str): Email of user to remove redis key from

    Returns:
        Union: Returns amount deleted
    """
    try:
        return redis_client.delete_key(f"forgot_{email}")
    except Exception:
        log.exception(f"Failed to remove key from redis for {email}")
