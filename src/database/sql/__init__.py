import os
from typing import Union

import asyncpg

from src.utils.log_handler import log

connection_pool = None


async def connect() -> Union[asyncpg.Pool, None]:
    try:
        return await asyncpg.create_pool(
            min_size=1,
            max_size=20,
            command_timeout=60,
            host=os.getenv("POSTGRES_DATABASE_HOST"),
            port=os.getenv("POSTGRES_DATABASE_PORT", 5432),
            user=os.getenv("POSTGRES_DATABASE_USER"),
            password=os.getenv("POSTGRES_DATABASE_PASSWORD"),
            database=os.getenv("POSTGRES_DATABASE_NAME"),
            server_settings={
                "search_path": os.getenv("POSTGRES_DATABSE_SCHEMA"),
            }
            if os.getenv("POSTGRES_DATABSE_SCHEMA")
            else None,
        )
    except Exception:
        raise ConnectionError("Failed to create connection")


async def get_connection() -> Union[asyncpg.Pool, None]:
    """Function to get a connection if not 1 already

    Returns:
        connection: Connection to the database
    """

    global connection_pool
    if not connection_pool:
        log.info("creating connection pool")
        connection_pool = await connect()
    return connection_pool


class acquire_connection:  # noqa: N801
    def __init__(self, pool) -> None:
        self.pool = pool
        self.conn = None

    async def __aenter__(self):  # noqa: ANN204
        self.conn = await self.pool.acquire()
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):  # noqa: ANN204
        await self.pool.release(self.conn)
