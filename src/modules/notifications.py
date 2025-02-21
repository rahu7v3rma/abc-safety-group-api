import io
import json
import os
import time
from typing import List, Optional, Union
from zipfile import ZipFile

from fastapi import UploadFile

from src.api.api_models.global_models import User
from src.utils.generate_random_code import generate_random_code
from src.utils.log_handler import log
from src.utils.mailer import send_email
from src.utils.text_messaging import send_text


def load_template(location: str) -> Union[dict, None]:
    data = None
    try:
        with open(location, "r") as file:
            data = json.load(file)
    except Exception:
        log.exception("failed to load template")
    return data


def certification_failed_users_notification(
    email: str,
    failed_users: list,
    temp_files: list,
    file_name: str,
) -> bool:
    try:
        found_template = load_template(
            "/source/src/content/templates/training_connect/certificate_failed_users.json",
        )
        if not found_template:
            raise Exception("Failed to load template")

        failed_users_list = "<ul>"
        for u in failed_users:
            course_name = (
                str(u["user"]["course_name"])
                .replace("&amp;", "")
                .replace("&nbsp;", "")
            )
            failed_users_list += (
                f"<li>Student: [{u['user']['first_name']} {u['user']['last_name']}]<ul>"  # noqa E501
                f"<li>Certificate Name: [{course_name}]</li>"
                f"<li>Issue: {u['reason']}</li>"
                f"<li>Next Steps: {u['solution']}</li></ul></li>"
            )
        failed_users_list += "</ul>"

        zip_buffer = io.BytesIO()

        with ZipFile(zip_buffer, "w") as zipf:
            for i, file in enumerate(temp_files):
                full_name = (
                    str(file["user"]["first_name"])
                    + " "
                    + str(file["user"]["last_name"])
                )
                random = generate_random_code(4)
                zipf.writestr(f"{full_name}_{random}.png", file["tempfile"])

        template = {
            "subject": found_template["email"]["subject"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
            ),
            "body": found_template["email"]["body"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
                company_phone=os.getenv("COMPANY_PHONE", "1234"),
                company_url=os.getenv("COMPANY_URL", "doitsolutions.io"),
                company_email=os.getenv(
                    "COMPANY_EMAIL",
                    "rmiller.doitsolutions.io",
                ),
                email=email,
                failed_users=failed_users_list,
                failed_amount=str(len(failed_users)),
                failed_users_text="Failed Users:" if temp_files else "",
                file_name=file_name,
            ),
        }

        if temp_files:
            template["attachments"] = [zip_buffer]

        tries = 0
        while True:
            try:
                e = send_email(receiver=[email], email_content=template)

                if e:
                    break
            except Exception:
                log.error(f"Attempting to resend email to {email}")
                if tries >= 3:
                    log.exception(
                        f"Failed to send email to user email {email}",
                    )
                    return False
            tries += 1
            time.sleep(3)
        return True
    except Exception:
        log.exception(f"Failed to send failed users to {email}")
    return False


def expedited_failed_user_notification(
    email: str,
    content: Optional[dict] = {},
) -> bool:
    try:
        if not isinstance(content, dict):
            content = {}

        if content:
            found_template = load_template(
                "/source/src/content/templates/training_connect/expedited_failed_with_user.json",
            )
        else:
            found_template = load_template(
                "/source/src/content/templates/training_connect/expedited_failed.json",
            )

        if not found_template:
            raise Exception("Failed to load template")

        template = {
            "subject": found_template["email"]["subject"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
            ),
            "body": found_template["email"]["body"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
                company_phone=os.getenv("COMPANY_PHONE", "1234"),
                company_url=os.getenv("COMPANY_URL", "doitsolutions.io"),
                company_email=os.getenv(
                    "COMPANY_EMAIL",
                    "rmiller.doitsolutions.io",
                ),
                email=content.get("email"),
                phone_number=content.get("phone_number"),
                first_name=content.get("first_name"),
                last_name=content.get("last_name"),
                reason=content.get("reason"),
                solution=content.get("solution"),
            ),
        }

        tries = 0
        while True:
            try:
                e = send_email(receiver=[email], email_content=template)

                if e:
                    break
            except Exception:
                log.error(f"Attempting to resend email to {email}")
                if tries >= 3:
                    log.exception(
                        f"Failed to send email to user email {email}",
                    )
                    return False
            tries += 1
            time.sleep(3)
        return True
    except Exception:
        log.exception(f"Failed to send failed users to {email}")
    return False


def student_failed_users_notification(
    email: str,
    failed_users: list,
    file_name: Optional[str] = None,
) -> bool:
    try:
        found_template = load_template(
            "/source/src/content/templates/training_connect/student_failed_users.json",
        )
        if not found_template:
            raise Exception("Failed to load template")

        failed_users_list = "<ul>"
        for u in failed_users:
            failed_users_list += (
                f"<li>Student Name: [{u['user'].get('first_name', 'First name not provided')} {u['user'].get('last_name', 'Last name not provided')}]<ul>"  # noqa E501
                f"<li>Issue: {u['reason']}</li>"
                f"<li>Next Steps: {u['solution']}</li></ul></li>"
            )
        failed_users_list += "</ul>"

        template = {
            "subject": found_template["email"]["subject"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
            ),
            "body": found_template["email"]["body"].format(
                company_name=os.getenv(
                    "COMPANY_NAME",
                    "Learning Management System",
                ),
                company_phone=os.getenv("COMPANY_PHONE", "1234"),
                company_url=os.getenv("COMPANY_URL", "doitsolutions.io"),
                company_email=os.getenv(
                    "COMPANY_EMAIL",
                    "rmiller.doitsolutions.io",
                ),
                email=email,
                failed_users=failed_users_list,
                failed_amount=str(len(failed_users)),
                file_name=file_name
                if file_name
                else "'no file name provided'",
                failed_users_text="Failed Users:" if failed_users_list else "",
            ),
        }

        tries = 0
        while True:
            try:
                e = send_email(receiver=[email], email_content=template)

                if e:
                    break
            except Exception:
                log.error(f"Attempting to resend email to {email}")
                if tries >= 3:
                    log.exception(
                        f"Failed to send email to user email {email}",
                    )
                    return False
            tries += 1
            time.sleep(3)
        return True
    except Exception:
        log.exception(f"Failed to send failed users to {email}")
    return False


def password_reset_notification(user: User, code: str) -> bool:
    try:
        found_template = load_template(
            "/source/src/content/templates/password_reset/password_reset.json",
        )
        if not found_template:
            raise Exception("Failed to load template")
        if (
            user.textNotifications
            and user.phoneNumber
            and found_template.get("text")
        ):
            text_message = found_template["text"].format(
                name=user.firstName,
                reset_link=(
                    f"{os.getenv('COMPANY_URL', 'doitsolutions.io')}"
                    f"/forgot-password?code={code}"
                ),
            )
            retries = 0
            while retries <= 3:
                if send_text(recipient=user.phoneNumber, message=text_message):
                    break
                retries += 1
        if (
            user.emailNotifications
            and user.email
            and found_template.get("email")
        ):
            template = {
                "subject": found_template["email"]["subject"].format(
                    company_name=os.getenv(
                        "COMPANY_NAME",
                        "Learning Management System",
                    ),
                ),
                "body": found_template["email"]["body"].format(
                    company_name=os.getenv(
                        "COMPANY_NAME",
                        "Learning Management System",
                    ),
                    name=user.firstName,
                    company_phone=os.getenv("COMPANY_PHONE", "1234"),
                    company_url=os.getenv("COMPANY_URL", "doitsolutions.io"),
                    company_email=os.getenv(
                        "COMPANY_EMAIL",
                        "rmiller.doitsolutions.io",
                    ),
                    reset_link=(
                        f"{os.getenv('COMPANY_URL', 'doitsolutions.io')}"  # noqa: E501
                        f"/forgot-password?code={code}"
                    ),
                ),
            }
            tries = 0
            while True:
                try:
                    email = send_email(
                        receiver=[user.email],
                        email_content=template,
                    )
                    if email:
                        break
                except Exception:
                    log.error(f"Attempting to resend email to {user.email}")
                    if tries >= 3:
                        log.exception(
                            f"Failed to send email to user email {user.email}",
                        )
                        return False
                tries += 1
                time.sleep(3)
        return True
    except Exception:
        log.exception(f"Failed to send a password reset to user {user}")
    return False


def training_connect_failure_notification(body: str) -> bool:
    try:
        found_template = load_template(
            "/source/src/content/templates/training_connect/training_connect_error.json",
        )
        if not found_template:
            raise Exception("Failed to load template")

        body = found_template["email"]["body"].format(error_message=body)

        template = {
            "subject": found_template["email"]["subject"],
            "body": body,
        }

        receivers = [
            "rmiller@doitsolutions.io",
            "aosmolovsky@doitsolutions.io",
        ]

        tries = 0
        while True:
            try:
                email = send_email(
                    receiver=receivers,
                    email_content=template,
                )
                if email:
                    break
            except Exception:
                log.error(f"Attempting to resend email to {receivers}")
                if tries >= 3:
                    log.exception(
                        "Failed to send email for training connect error",
                    )
                    return False
            tries += 1
            time.sleep(3)
        return True
    except Exception:
        log.exception("Failed to send email for training connect error")
    return False


def send_bug_report_notification(
    user: User,
    subject: str,
    body: str,
    attachments: List[UploadFile],
) -> bool:
    try:
        template = {
            "subject": f"Bug report submitted by {user.firstName} {user.lastName} for company {os.getenv('COMPANY_NAME', 'No company name found')}",  # noqa: E501
            "body": f"""
                <p><strong>Company Information</strong>:</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Name</strong>: {os.getenv('COMPANY_NAME', 'No company name found')}</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Phone Number</strong>: {os.getenv('COMPANY_PHONE', 'N/A')}</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Email</strong>: {os.getenv('COMPANY_EMAIL', 'N/A')}</p>
                <p>&nbsp;</p>
                <p><strong>Contact Information</strong>:</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Name</strong>: {user.firstName} {user.lastName}</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Phone Number</strong>: {user.phoneNumber or ''}</p>
                <p>&nbsp; &nbsp; &nbsp;<strong>Email</strong>: {user.email or ''}</p>
                <p>&nbsp;</p>
                <p><strong>subject</strong>:</p>
                <p>{subject}</p>
                <p><strong>body</strong>:</p>
                <p>{body}</p>
            """,  # noqa: E501
            "attachments": attachments,
        }

        tries = 0
        while True:
            try:
                email = send_email(
                    receiver=["aosmolovsky@doitsolutions.io"],
                    email_content=template,
                    cc=[user.email] if user.email else None,
                )
                if email:
                    for attachment in attachments:
                        os.remove(attachment)  # type: ignore
                    break
            except Exception:
                log.error(
                    "Attempting to resend email to 'asmolovsky@doitsolutions.io'",  # noqa: E501
                )
                if tries >= 3:
                    log.exception(
                        "Failed to send email for training connect error",
                    )
                    return False
            tries += 1
            time.sleep(3)
        return True
    except Exception:
        log.exception("Failed to send email for training connect error")
    return False


def generate_certificate_notification(
    user: User,
    course: dict,
    certificate: bytes,
) -> bool:
    try:
        found_template = load_template(
            "/source/src/content/templates/certificates/generated_certificates.json",
        )
        if not found_template:
            raise Exception("Failed to load template")
        if (
            user.textNotifications
            and user.phoneNumber
            and found_template.get("text")
        ):
            text_message = found_template["text"].format(
                name=user.firstName,
                course_name=course["courseName"],
                company_phone=os.getenv("COMPANY_PHONE", "1234"),
            )
            if text_message:
                retries = 0
                while retries <= 3:
                    if send_text(
                        recipient=user.phoneNumber,
                        message=text_message,
                    ):
                        break
                    retries += 1
        if (
            user.emailNotifications
            and user.email
            and found_template.get("email")
        ):
            zip_buffer = io.BytesIO()

            with ZipFile(zip_buffer, "w") as zipf:
                zipf.writestr(f'{course["courseName"]}.png', certificate)
            template = {
                "subject": found_template["email"]["subject"].format(
                    course_name=course["courseName"],
                ),
                "body": found_template["email"]["body"].format(
                    company_name=os.getenv(
                        "COMPANY_NAME",
                        "Learning Management System",
                    ),
                    name=user.firstName,
                    course_name=course["courseName"],
                    company_phone=os.getenv("COMPANY_PHONE", "1234"),
                    company_email=os.getenv(
                        "COMPANY_EMAIL",
                        "rmiller.doitsolutions.io",
                    ),
                ),
                "attachments": [zip_buffer],
            }

            tries = 0
            while True:
                try:
                    email = send_email(
                        receiver=[user.email],
                        email_content=template,
                    )
                    if email:
                        break
                except Exception:
                    log.error(f"Attempting to resend email to {user.email}")
                    if tries >= 3:
                        log.exception(
                            f"Failed to send email to user email {user.email}",
                        )
                        return False
                    tries += 1
                    time.sleep(3)
        return True
    except Exception:
        log.exception(
            f"Failed to notify enrollment status update for user {user}",
        )
    return False
