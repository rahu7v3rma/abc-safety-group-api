import os
from typing import Optional, Union

import redis


class RedisClient:
    """Class to handle redis connections"""

    def __init__(self, db: int = 0) -> None:
        self.db = db
        self.redis_client = None
        self.connect(db=db)

    def refresh_connection(self) -> Union[redis.Redis, None]:
        try:
            if self.redis_client:
                self.redis_client.close()

            self.connect(db=self.db)
        except Exception as e:
            print(f"An exception occured {e}")  # noqa: T201
            raise ConnectionResetError("Failed to reset connection")

    def connect(self, db: int = 0) -> Union[redis.Redis, None]:
        """Function to get redis connection

        Args:
            db (int, optional): database of redis. Defaults to 0.

        Raises:
            ConnectionError: Connection error

        Returns:
            Union[redis.Redis, None]: Redis connection or None
        """
        try:
            self.redis_client = redis.Redis.from_url(
                f"{os.getenv('REDIS_URI', None)}/{db}",
            )
        except Exception:
            raise ConnectionError("Failed to establish connection to redis")

    def ping(self) -> bool:
        """Function to ping redis connection

        Returns:
            bool: Boolean for success
        """
        try:
            if self.redis_client and self.redis_client.ping():
                return True
        except Exception as e:
            print(f"an exception occured {e}")  # noqa: T201

        self.refresh_connection()
        return False

    def publish(self, channel: str, data: str) -> bool:
        """Function to publish a message to redis

        Args:
            channel (str): Redis channel
            data (str): Data to publish

        Returns:
            bool: bool for success
        """
        if not channel:
            print("No channel present for redis")  # noqa: T201
            return False

        if not data:
            print("No data present for redis")  # noqa: T201
            return False

        if not self.ping() or not self.redis_client:
            self.refresh_connection()

        try:
            number = self.redis_client.publish(channel, data)  # type: ignore
        except Exception as e:
            print(  # noqa: T201
                f"An exception occured while publishing to redis, exception {e}",  # noqa: E501
            )
            self.refresh_connection()
            return False

        if not number:
            print("No number present from redis")  # noqa: T201
            self.refresh_connection()
            return False

        return True

    def set_key(
        self,
        key: str,
        token: Optional[str] = None,
        ex: int = 86400,
    ) -> Union[str, None]:
        """Function to set a key in redis

        Args:
            key str: key of redis.
            token (str, optional): value to set in redis. Defaults to None.
            ex (int, optional): expiry of redis. Defaults to None.

        Returns:
            Union[str, None]: Returns either a key or none
        """
        if not key:
            return None

        if not ex:
            ex = 86400

        if not self.ping() or not self.redis_client:
            self.refresh_connection()

        self.redis_client.set(key, str(token), ex)  # type: ignore

        return key

    def get_key(self, redis_key: str) -> Union[str, None]:
        """Function to get key from redis

        Args:
            redis_key str: key from redis to get.

        Returns:
            Union[str, None]: Returns either a redis value or none
        """

        if not self.ping():
            self.refresh_connection()

        token = self.redis_client.get(redis_key)  # type: ignore
        if token:
            return token.decode()  # type: ignore

        return None

    def delete_key(self, redis_key: str) -> Union[int, None]:
        """Function to delete a redis key

        Args:
            redis_key str: key of redis to delete.

        Returns:
            Union[int, None]: Returns amount deleted or none
        """
        if not redis_key:
            return None

        if not self.ping() or not self.redis_client:
            self.refresh_connection()

        deleted = self.redis_client.delete(redis_key)  # type: ignore
        return deleted  # type: ignore
