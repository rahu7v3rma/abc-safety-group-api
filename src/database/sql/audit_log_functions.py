import datetime
import uuid

from src import log
from src.database.sql import acquire_connection, get_connection


async def submit_audit_record(route: str, details: str, user_id: str) -> bool:
    query = """
    INSERT INTO audit_log (
        audit_id,
        route,
        details,
        create_dtm,
        user_id
    ) VALUES ($1, $2, $3, $4, $5);
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                query,
                str(uuid.uuid4()),
                route,
                details,
                datetime.datetime.utcnow(),
                user_id,
            )
        return True
    except Exception:
        log.exception("Failed to insert audit log event")

    return False
