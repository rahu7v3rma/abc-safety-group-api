import os

import requests

from src.utils.log_handler import log


def send_text(recipient: str, message: str) -> bool:
    if not os.getenv("USE_TEXT", "false").lower() == "true":
        return True

    account_id = os.getenv("8X8_ACCOUNT_ID", None)
    if not account_id:
        log.error("8X8_ACCOUNT_ID missing from environment")
        return True

    auth_token = os.getenv("8X8_AUTH_TOKEN", None)
    if not auth_token:
        log.error("8X8_AUTH_TOKEN missing from environment")
        return True

    response = requests.post(
        f"https://sms.8x8.com/api/v1/subaccounts/{account_id}/messages",
        json={
            "encoding": "AUTO",
            "track": None,
            "source": os.getenv("COMPANY_NAME", "Learning Management System"),
            "text": message,
            "destination": recipient,
        },
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "Authorization": f"Bearer {auth_token}",
        },
    )

    if not response.status_code == 200:
        log.error(response.json())
        return False

    return True
