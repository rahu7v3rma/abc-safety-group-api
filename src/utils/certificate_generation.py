import base64
import json
import os
import re
import tempfile
import traceback
from datetime import datetime
from typing import Optional, Tuple, Union

import asyncpg
from dateutil.relativedelta import relativedelta
from pyppeteer import launch

from src import log, training_connect
from src.api.api_models import global_models
from src.database.sql import acquire_connection, get_connection
from src.database.sql.user_functions import (
    get_or_create_user,
    get_user,
)
from src.modules.notifications import generate_certificate_notification
from src.utils.datetime_serializer import datetime_serializer
from src.utils.generate_random_code import generate_random_certificate_number


def read_and_encode_image(file_path) -> str:
    with open(file_path, "rb") as image_file:
        image_data = image_file.read()

    base64_image = base64.b64encode(image_data).decode()
    return base64_image


async def html_to_png(html_content, output_path) -> Union[str, bytes]:
    try:
        browser = await launch(
            executablePath="/usr/bin/google-chrome-stable",
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-software-rasterizer",
                "--single-process",
                "--disable-dev-shm-usage",
                "--no-zygote",
            ],
        )
        page = await browser.newPage()
        await page.setViewport({"width": 1300, "height": 1000})
        pattern = r'src="([a-z0-9/._]+)"'

        def replace_src(match) -> str:
            src = match.group(1)
            src_path = f"/source/src/content/certificates{src[1:]}"

            base64_image = read_and_encode_image(src_path)

            return f'src="data:image/jpeg;base64,{base64_image}"'

        modified_html = re.sub(pattern, replace_src, html_content)

        await page.setContent(modified_html)
        await page.addStyleTag(
            path="/source/src/content/certificates/styles/output.css",
        )
        await page.waitFor(500)
        screenshot = await page.screenshot()
        await browser.close()

        return screenshot

    except Exception as e:
        raise e


async def generate_certificate_func(
    student_full_name: str,
    instructor_full_name: str,
    certificate_name: str,
    completion_date: datetime,
    expiration_date: datetime,
    certificate_number: str,
    email: Optional[str] = None,
    phone_number: Optional[str] = None,
    template: Optional[str] = None,
    save: bool = True,
) -> Union[Tuple[Union[str, bytes], Union[str, bytes]], str, bytes]:
    try:
        if not template:
            template = "/source/src/content/certificates/index.html"

        with open(template, "r") as file:  # noqa: ASYNC101
            generation_template = file.read()
            file.close()

        formatted_completion_date = completion_date.strftime("%Y-%m-%d")

        html_content = generation_template.replace(
            "{student_full_name}",
            student_full_name,
        )
        html_content = html_content.replace(
            "{instructor_full_name}",
            instructor_full_name,
        )
        html_content = html_content.replace(
            "{certificate_name}",
            certificate_name,
        )
        html_content = html_content.replace(
            "{completion_date}",
            formatted_completion_date,
        )
        html_content = html_content.replace(
            "{certificate_number}",
            certificate_number,
        )

        output_path = f"/source/src/content/user_certificates/{student_full_name.replace(' ', '_')}_{certificate_name}.png"  # noqa: E501

        try:
            output = await html_to_png(html_content, output_path)
        except Exception as e:
            raise e

        if save:
            if not email and not phone_number:
                return (
                    output,
                    "Unable to find user in Learning Management System without an email or phone number provided.",  # noqa: E501
                )
            log.debug("saving user certificate")
            saved = await save_user_certificate(
                certificate_number=certificate_number,
                completion_date=completion_date,
                expiration_date=expiration_date,
                email=email,
                phone_number=phone_number,
                certificate_name=certificate_name,
                instructor_full_name=instructor_full_name,
            )
            if not saved or isinstance(saved, str):
                return (
                    output,
                    (
                        "Unable to find user in Learning Management System with email: "  # noqa: E501
                        f"{email} or phone number: {phone_number} for certificate relation."  # noqa: E501
                        if not saved
                        else saved
                    ),
                )

            if isinstance(saved, str):
                return (output, saved)
        return output
    except Exception as e:
        raise e


async def generate_certificate(
    user: global_models.User,
    course: dict,
    certificate: Optional[dict] = None,
    certificate_number: Optional[str] = None,
    notify_users: Optional[bool] = True,
    upload_certificates: Optional[bool] = False,
    save: Optional[bool] = True,
) -> bool:
    if not certificate_number:
        certificate_number = generate_random_certificate_number(
            length=15,
            course_code=course.get("courseCode", None),
        )

    completion_date = datetime.utcnow()
    expiration_date = None
    certificate_name = ""
    certificate_name += course["courseName"]
    if course.get("courseCode"):
        certificate_name += f", {course['courseCode']}"

    formatted_values = {
        "student_full_name": f"{user.firstName} {user.lastName}",
        "instructor_full_name": (
            f"{course['instructors'][0]['firstName']} {course['instructors'][0]['lastName']}"  # noqa: E501
            if course["instructors"]
            else os.getenv("COMPANY_NAME")
        ),
        "instructor_id": course["instructors"][0]["userId"]
        if course["instructors"]
        else "d8adb06f-1db0-43be-8823-bd26460408fb",
        "certificate_name": certificate_name,
        "completion_date": completion_date,
    }

    certificate_id = None
    if certificate:
        if certificate["certificateId"]:
            certificate_id = certificate["certificateId"]
        if certificate["certificateName"]:
            certificate_name = certificate["certificateName"]

        if certificate["certificateLength"]:
            certificate_length = json.loads(certificate["certificateLength"])
            if certificate_length["years"]:
                expiration_date = completion_date + relativedelta(
                    years=certificate_length["years"],
                )
            if certificate_length["months"]:
                if expiration_date:
                    expiration_date = expiration_date + relativedelta(
                        months=certificate_length["months"],
                    )
                else:
                    expiration_date = completion_date + relativedelta(
                        months=certificate_length["months"],
                    )

        formatted_values.update(
            {
                "instructor_full_name": (
                    f"{course['instructors'][0]['firstName']} {course['instructors'][0]['lastName']}"  # noqa: E501
                    if course["instructors"]
                    else os.getenv("COMPANY_NAME")
                ),
                "certificate_name": certificate_name,
                "expiration_date": expiration_date,
            },
        )

    try:
        generated_certificate = await generate_certificate_func(
            student_full_name=formatted_values.get("student_full_name", ""),
            instructor_full_name=formatted_values.get(
                "instructor_full_name",
                "",
            ),
            certificate_name=formatted_values.get("certificate_name", ""),
            completion_date=formatted_values.get("completion_date", ""),
            certificate_number=certificate_number,
            expiration_date=formatted_values.get("expiration_date", ""),
            save=False,
        )
        if not generated_certificate:
            return False

    except Exception:
        log.exception("An exception occured while generating the certificate")
        return False

    # save certificate to user
    saved = await save_user_certificate(
        certificate_number=certificate_number,
        instructor_id=formatted_values["instructor_id"],
        completion_date=completion_date,
        course_id=course["courseId"],
        user=user,
        certificate_id=certificate_id,
        expiration_date=expiration_date,
    )

    if not saved:
        return False

    if upload_certificates:
        training_connect_upload = [
            {
                "our_student": False,
                "certificate_id": certificate_number,
                "course_name": course["courseName"],
                "issue_date": datetime.strftime(completion_date, "%Y-%m-%d"),
                "expiry_date": datetime.strftime(expiration_date, "%Y-%m-%d")
                if expiration_date
                else None,
                "first_name": user.firstName,
                "last_name": user.lastName,
                "date_of_birth": user.dob,
                "instructor": f"{course['instructors'][0]['firstName']} {course['instructors'][0]['lastName']}",  # noqa: E501
                "email": user.email,
                "phone_number": user.phoneNumber,
                "upload_info": {
                    "uploader": os.getenv(
                        "COMPANY_EMAIL",
                        "rmiller@doitsolutions.io",
                    ),
                    "position": 1,
                    "max": 1,
                    "upload_type": "certificate",
                    "save": False,
                    "only_lms": False,
                },
            },
        ]
        if (
            os.getenv("TRAINING_CONNECT_CERTIFICATES", "false").lower()
            == "true"
        ):
            json_data = json.dumps(
                training_connect_upload,
                default=datetime_serializer,
            )

            published = await training_connect.redis_rpush(json_data)
            if not published:
                raise Exception("Failed to post data to redis")

    if notify_users:
        generate_certificate_notification(
            user=user,
            course=course,
            certificate=generated_certificate,  # type: ignore
        )

    return True


async def save_user_certificate(
    certificate_number: str,
    completion_date: datetime,
    instructor_id: Optional[str] = None,
    expiration_date: Optional[datetime] = None,
    course_id: Optional[str] = None,
    email: Optional[str] = None,
    phone_number: Optional[str] = None,
    user: Optional[global_models.User] = None,
    certificate_id: Optional[str] = None,
    certificate_name: Optional[str] = None,
    instructor_full_name: Optional[str] = None,
) -> Union[bool, str]:
    # do sql query for import into certificate table here
    if email and not user:
        user = await get_user(email=email)
    if phone_number and not user:
        user = await get_user(phoneNumber=phone_number)

    if not user:
        log.error(
            f"User not found for save_user_certificate {email=}, {phone_number=}",
        )
        return False

    params = [
        user.userId,
        certificate_id,
        course_id,
        completion_date,
        expiration_date,
        instructor_id,
        certificate_number,
        certificate_name,
        instructor_full_name,
    ]

    query = """
        INSERT INTO user_certificates (
            user_id,
            certificate_id,
            course_id,
            completion_date,
            expiration_date,
            instructor_id,
            certificate_number,
            certificate_name,
            instructor_name
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9
        );
    """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                query,
                *params,
            )
        return True

    except asyncpg.exceptions.UniqueViolationError as err:
        key = (
            err.args[0]
            .split('duplicate key value violates unique constraint "')[1]
            .split('"')[0]
        )
        if key == "user_certificates_pkey":
            return "Certificate Number already in use"

        return f"Certificate {certificate_id} for a user already exists in LMS"
    except Exception as exception:
        log.exception(
            f"An error occurred while creating a certificate for {user.userId if user else email} with {exception=}",  # noqa: E501
        )
        traceback.print_exc()

    log.error(f"end of save_user_certificate {email=}, {phone_number=}")
    return False


async def tc_save_certificate(
    user: dict,
) -> dict:
    try:
        db_user = await get_or_create_user(user)
        if not db_user.get("status"):
            return {
                "status": False,
                "reason": db_user.get("reason"),
                "solution": db_user.get("solution"),
                "system": db_user.get("system"),
            }

        if db_user.get("type") == "created":
            published = await training_connect.redis_publish(
                db_user.get("result"),
            )
            if not published.get("status"):
                raise Exception("Failed to publish data to training connect")

        insert_certificate = await save_user_certificate(
            certificate_number=user["certificate_id"],
            completion_date=datetime.strptime(user["issue_date"], "%Y-%m-%d"),
            expiration_date=datetime.strptime(user["expiry_date"], "%Y-%m-%d"),
            certificate_name=user["course_name"],
            instructor_full_name=user["instructor"],
            user=db_user.get("result"),
        )
        if isinstance(insert_certificate, str):
            return {
                "status": False,
                "reason": (
                    f"Unable to save the certificate due to [{insert_certificate}]"
                ),
                "solution": ("Please try again with different information.",),
            }
        if not insert_certificate:
            raise Exception("Failed to save certificate")

        return {"status": True}
    except Exception as exception:
        log.exception(
            f"An error occurred while executing tc_save_user_certificate {user} with {exception=}",  # noqa: E501
        )
        traceback.print_exc()

    return {
        "status": False,
        "reason": "An error occurred while saving certificate",
        "solution": "Contact support for assistance",
        "system": f"Failed to save certificate for {user=}, more in logs",
    }


async def tc_generate_certificate(user: dict) -> dict:
    try:
        template = "/source/src/content/certificates/index.html"

        with open(template, "r") as file:  # noqa: ASYNC101
            generation_template = file.read()
            file.close()

        html_content = generation_template.replace(
            "{student_full_name}",
            user["first_name"] + " " + user["last_name"],
        )
        html_content = html_content.replace(
            "{instructor_full_name}",
            user["instructor"],
        )
        html_content = html_content.replace(
            "{certificate_name}",
            user["course_name"],
        )
        html_content = html_content.replace(
            "{completion_date}",
            user["issue_date"],
        )
        html_content = html_content.replace(
            "{certificate_number}",
            user["certificate_id"],
        )

        output_path = f"/source/src/content/user_certificates/{user['first_name']}_{user['last_name']}_{user['course_name']}.png".replace(
            " ",
            "_",
        )

        output = await html_to_png(html_content, output_path)

        with tempfile.NamedTemporaryFile(
            suffix=".png",
            delete=False,
        ) as file:
            f_name = file.name
            file.write(output)  # type: ignore

        return {"status": True, "result": f_name}
    except Exception as exception:
        log.exception(
            f"error generating certificate with {exception=} for {user=}",
        )
        traceback.print_exc()

    return {
        "status": False,
        "reason": "An error occurred while generating the certificate",
        "solution": "Contact support for assistance",
        "system": f"Failed to generate certificate for {user=}, more in logs",
    }
