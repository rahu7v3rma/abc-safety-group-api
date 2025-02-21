import asyncio
import datetime
import json
import os
import re
import traceback
import uuid
from typing import Tuple, Union

import redis
import requests
from passlib.hash import pbkdf2_sha256
from pyppeteer import launch
from pyppeteer.errors import NetworkError, TimeoutError

from src.api.api_models import global_models
from src.database.sql.user_functions import (
    create_user,
    delete_user_certificates,
    delete_users,
    get_user,
    manage_user_roles,
)
from src.database.sql.user_functions import update_user as update_lms_user
from src.modules.notifications import (
    certification_failed_users_notification,
    expedited_failed_user_notification,
    student_failed_users_notification,
    training_connect_failure_notification,
)
from src.utils.generate_random_code import (
    generate_random_certificate_number,
    generate_random_code,
)
from src.utils.log_handler import log
from src.utils.validate import validate_email, validate_phone_number


def find_in_select(element: str, find: str) -> str:
    code = f"""() => {{
            const selectElement = document.querySelector("#{element}");
            const options = selectElement.options;
            const optionArray = [];
            for (let i = 0; i < options.length; i++) {{
                const option = options[i];
                optionArray.push({{
                    value: option.value,
                    text: option.text
                }});
            }}
            for (let i = 0; i < optionArray.length; i++) {{
                if (optionArray[i].text === `{find}`) {{
                    selectElement.value = optionArray[i].value;
                    break; // Exit the loop once a match is found
                }}
            }}
            }}"""
    return code


def validate_certificate_user(user: dict) -> dict:
    required_keys = [
        "first_name",
        "last_name",
        "issue_date",
        "expiry_date",
        "course_name",
        "instructor",
        "certificate_id",
        "phone_number",
        "email",
    ]
    for key in required_keys:
        if not user[key]:
            return {
                "status": False,
                "reason": f"User is missing {key}",
                "solution": f"Please provide the {key} for this user.",
            }
        user[key] = str(user[key]).strip()
    user: dict[str, str] = user

    try:
        datetime.datetime.strptime(user["issue_date"], "%Y-%m-%d")
    except Exception:
        return {
            "status": False,
            "reason": "Invalid issue date",
            "solution": "The issue date provided is invalid. The correct format should be YYYY-MM-DD.",
        }

    try:
        datetime.datetime.strptime(user["expiry_date"], "%Y-%m-%d")
    except Exception:
        return {
            "status": False,
            "reason": "Invalid expiry date",
            "solution": "The expiry date provided is invalid. The correct format should be YYYY-MM-DD.",
        }

    user["course_name"] = (
        user["course_name"].replace("&amp;", "").replace("&nbsp;", "")
    )

    user["certificate_id"] = user["certificate_id"].replace(" ", "")

    user["phone_number"] = validate_phone_number(user["phone_number"])
    if not user["phone_number"]:
        return {
            "status": False,
            "reason": "Invalid phone number",
            "solution": "The phone number provided is invalid.",
        }

    user["email"] = validate_email(user["email"])
    if not user["email"]:
        return {
            "status": False,
            "reason": "Invalid email",
            "solution": "The email provided is invalid.",
        }

    return {"status": True, "result": user}


class TrainingConnect:
    def __init__(self) -> None:
        self.page = None
        self.browser = None
        self.redis = None

        self.logged_in = False
        self.match_user_url = ""
        self.email = ""
        self.users = []
        self.tmpfiles = []
        self.pattern = re.compile(r"(\d+)\s+(.+)")

        self.queue_running = False
        self.queue_lock = asyncio.Lock()
        self.queue = []
        self.system_errors = []

        self.redis_list_key = "training_connect"
        self.redis_list = []

    async def redis_connection(
        self,
        retries: int = 0,
    ) -> Union[redis.Redis, None]:
        if retries >= 5:
            log.error("Max retries for redis connection reached")
            return None
        try:
            connection = redis.asyncio.from_url(
                f"{os.getenv('REDIS_URI', None)}/{2}",
            )

            await asyncio.sleep(5)
            if not connection:
                raise ConnectionError
        except Exception:
            log.exception("Exception occurred while connecting to redis")
            return await self.redis_connection(retries=retries + 1)

        return connection

    async def generate_cert(
        self,
        user,
        failed: bool,
    ) -> Union[
        Tuple[Union[str, bytes], Union[str, bytes]],
        str,
        bytes,
        None,
    ]:
        cert_id = (
            user["certificate_id"]
            if user.get("certificate_id")
            else generate_random_certificate_number(
                length=10,
            )
        )
        try:
            try:
                issue_date = datetime.datetime.strptime(
                    user["issue_date"].split(" ")[0],
                    "%Y-%m-%d",
                )
            except Exception:
                if not failed:
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "The issue date provided "
                            f"({user['issue_date']}) is invalid."
                            "The correct format should be YYYY-MM-DD."
                        ),
                        upload_type="certificate",
                        solution=(
                            "Please correct the date format and "
                            "resubmit the affected certificate."
                        ),
                    )
                return
            try:
                expiry_date = datetime.datetime.strptime(
                    user["expiry_date"].split(" ")[0],
                    "%Y-%m-%d",
                )
            except Exception:
                if not failed:
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "The expiry date provided "
                            f"({user['expiry_date']}) is invalid. "
                            "It should be formatted as YYYY-MM-DD."
                        ),
                        upload_type="certificate",
                        solution=(
                            "Please update the expiry date accordingly and "
                            "resubmit the certificate."
                        ),
                    )
                return

            phone_number = validate_phone_number(
                phone_number=user.get("phone_number"),
            )
            if not phone_number:
                if not failed:
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            f"The phone number provided ({phone_number}) "
                            "is invalid."
                        ),
                        upload_type="certificate",
                        solution=(
                            "Please provide a valid phone number and "
                            "resubmit the certificate."
                        ),
                    )
                return

            found_user = await get_user(
                email=user.get("email"),
                phoneNumber=phone_number,
            )
            if not found_user:
                new_user = {
                    "user_id": str(uuid.uuid4()),
                    "first_name": user["first_name"],
                    "last_name": user["last_name"],
                    "email": validate_email(user.get("email")),
                    "phone_number": phone_number,
                    "password": pbkdf2_sha256.hash(generate_random_code(12)),
                    "time_zone": "America/New_York",
                    "create_dtm": datetime.datetime.utcnow(),
                    "modify_dtm": datetime.datetime.utcnow(),
                    "active": True,
                    "text_notif": True if phone_number else False,
                    "email_notif": True if user.get("email") else False,
                    "expiration_date": None,
                }
                created = await create_user(newUser=new_user)
                if created:
                    await manage_user_roles(
                        roles=["student"],
                        user_id=new_user["user_id"],
                        action="add",
                    )
                    json_data = [
                        {
                            "user_id": new_user["user_id"],
                            "first_name": new_user["first_name"],
                            "last_name": new_user["last_name"],
                            "phone_number": new_user["phone_number"],
                            "email": new_user["email"],
                            "upload_info": {
                                "uploader": os.getenv(
                                    "COMPANY_EMAIL",
                                    "rmiller@doitsolutions.io",
                                ),
                                "upload_type": "update_user",
                                "position": 1,
                                "max": 1,
                                "only_lms": False,
                            },
                        },
                    ]
                    json_data = json.dumps(json_data)

                    published = await self.redis_rpush(json_data)

                    if not published:
                        raise Exception("Failed to post data to redis")
                elif isinstance(created, str):
                    if not failed:
                        await self.add_failed(
                            failed_user=user,
                            reason=(
                                f"Unable to create a user while uploading "
                                f"the certificate due to [{created}]."
                            ),
                            upload_type="certificate",
                            solution=(
                                "Please check the user information for "
                                "duplicates or errors and attempt to resubmit."
                            ),
                        )
                    log.error("Failed to create user")

            save_cert = False
            if not failed and user["upload_info"].get("save", True):
                save_cert = True

            from src.utils.certificate_generation import (
                generate_certificate_func,
            )

            cert = await generate_certificate_func(
                student_full_name=str(
                    user["first_name"] + " " + user["last_name"],
                ),
                instructor_full_name=str(user["instructor"]),
                certificate_name=str(user["course_name"]),
                completion_date=issue_date,
                expiration_date=expiry_date,
                certificate_number=str(cert_id),
                email=user.get("email"),
                phone_number=phone_number,
                save=save_cert,
            )
            if not cert:
                return None

            if isinstance(cert, tuple):
                self.tmpfiles.append(
                    {"tempfile": cert[0], "failed": failed, "user": user},
                )
            else:
                self.tmpfiles.append(
                    {"tempfile": cert, "failed": failed, "user": user},
                )
            return cert
        except Exception as e:
            log.error(
                "Something went wrong when trying to generate the users certificate.",  # noqa: E501
            )
            self.system_errors.append(
                {"reason": "Failed to generate certificate", "stack": str(e)},
            )
            return None

    async def add_failed(
        self,
        failed_user: dict,
        reason: str,
        upload_type: str,
        solution: str = "",
    ) -> None:
        log.debug(f"add_failed_{reason=}")
        if upload_type == "certificate":
            log.debug("Deleting certificates from lms, an error occurred")
            await delete_user_certificates(
                certificate_numbers=[failed_user.get("certificate_id")],
            )

        if upload_type == "student":
            log.debug("Deleting student from lms, an error occurred")
            await delete_users(user_ids=[failed_user["user_id"]])
        self.users.append(
            {
                "user": failed_user,
                "failed": True,
                "reason": reason,
                "solution": solution,
            },
        )
        try:
            log.info(str(failed_user["first_name"] + " added to failed"))
        except Exception:
            log.exception(
                "An error occurred while adding user to failed for training connect",  # noqa: E501
            )

    async def create_student(self, user: dict, upload_type: str) -> None:
        if not self.page:
            return
        try:
            if not user.get("phone_number"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "phone number".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the phone number for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("height"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "height".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the height for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("eye_color"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "eye color".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the eye color for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("gender"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "gender".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the gender for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("house_number"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "house number".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the house number for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("street_name"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "street name".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the street name for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("city"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "city".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the city for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("state"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "state".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the state for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("zipcode"):
                await self.add_failed(
                    failed_user=user,
                    reason='It appears we are missing the "zip code".',
                    upload_type=upload_type,
                    solution=(
                        "Please specify the zip code for this student and "
                        "resubmit the information."
                    ),
                )
                return

            if not user.get("head_shot"):
                user["head_shot"] = "default_headshot.jpg"

            found_dob = user["dob"]
            try:
                user["dob"] = datetime.datetime.strptime(
                    found_dob,
                    "%Y-%m-%d %H:%M:%S",
                )
                dob = user["dob"].strftime("%Y-%m-%d")
            except Exception:
                try:
                    user["dob"] = datetime.datetime.strptime(
                        found_dob,
                        "%m/%d/%Y",
                    )
                    dob = user["dob"].strftime("%Y-%m-%d")
                except Exception:
                    log.error(f"Failed to convert dob {user['dob']}")
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "It appears there was an issue converting "
                            'the "date of birth" provided.'
                        ),
                        upload_type=upload_type,
                        solution=(
                            "We would appreciate it "
                            "if you could verify the format"
                            "and resubmit the information."
                        ),
                    )
                    return

            await self.page.goto(
                "https://dob-trainingconnect.cityofnewyork.us/Students/Create?providerId=36cd1e6e-62b5-4770-ad4f-08d97ed9594c",
            )
            await self.page.waitForSelector(".col-auto")
            await self.page.type("#FirstName", str(user["first_name"]))

            if user.get("middle_name"):
                await self.page.type("#MiddleName", str(user["middle_name"]))

            await self.page.type("#LastName", str(user["last_name"]))

            if user.get("suffix"):
                await self.page.type("#Suffix", str(user["suffix"]))

            await self.page.evaluate(
                f"""() => {{
                    const dateInput = document.querySelector("#DateOfBirth");
                    dateInput.value = "{dob}";
                }}""",
                dob,
            )

            file_input = await self.page.querySelector("input[type=file]")
            if file_input:
                await file_input.uploadFile(
                    f'/source/src/content/user/{user["head_shot"]}',
                )

            # START - filling address inputs
            await self.page.type(
                "input#AddressNumber",  # type = text, required = True
                str(user["house_number"]),  # label = House Number
            )
            await self.page.type(
                "input#AddressName",  # type = text, required = True
                str(user["street_name"]),  # label = Street Name
            )
            await self.page.type(
                "input#City",  # type = text, required = True
                str(user["city"]),  # label = City
            )
            await self.page.type(
                "input#State-selectized",  # type = text, required = True
                str(user["state"]),  # label = State
            )
            # if state select dropdown includes user["state"]
            is_state_visible = await self.page.evaluate(
                """() => {
                    const element = document.querySelector('.selectize-dropdown.single.searchable');
                    const style = window.getComputedStyle(element);
                    return style.getPropertyValue('display') !== 'none';
                }""",  # noqa: E501
            )
            if not is_state_visible:
                log.error(
                    "failing this user because no state matched therefore address will not match",  # noqa: E501
                )
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "It appears there was an issue "
                        'with the "state" provided.'
                    ),
                    upload_type=upload_type,
                    solution=(
                        "We would appreciate it "
                        "if you could verify the state "
                        "and resubmit the information."
                    ),
                )
                return
            # selecting matched option with user["state"] from state select dropdown # noqa: E501
            await self.page.keyboard.press("Enter")
            await self.page.type(
                "input#ZipCode",  # type = text, required = True
                str(user["zipcode"]),  # label = Zip Code
            )
            # END - filling address inputs

            if user.get("email"):
                await self.page.type("#Email", str(user["email"]))

            await self.page.type("#Phone", str(user["phone_number"]))

            await self.page.evaluate(
                find_in_select("Height", str(user["height"])),
            )
            await self.page.evaluate(
                find_in_select("Gender", str(user["gender"])),
            )
            await self.page.evaluate(
                find_in_select("EyeColor", str(user["eye_color"])),
            )

            # create the student
            await self.page.click('input[type="submit"]')

            # probably get the text of the dangers, which will say what is missing  # noqa: E501
            # and use it for errors in failed
            await self.page.waitFor(5000)

            try:
                dangers = await self.page.evaluate(
                    """() => {
                    let elements = document.querySelectorAll(".text-danger.field-validation-error");
                    let innerHTMLArray = [];

                    elements.forEach(function(element) {
                        let innerHTML = element.innerHTML;
                        innerHTMLArray.push(innerHTML);
                    });

                    return innerHTMLArray;
                    }""",  # noqa: E501
                )
            except Exception:
                log.debug("No dangers found")
                dangers = None

            if dangers:
                log.debug(f"dangers found: {dangers}")
                # user not created
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "We encountered some platform-specific errors: "
                        f"[{', '.join(dangers)}]. Please address these issues "
                        "and resubmit the data. "
                        "Issue to be fixed by our Programming Team: "
                        "There is a technical error that needs rectification "
                        "from our programming team to "
                        "ensure seamless data integration."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "Our developers are already on it and "
                        "we aim to resolve this promptly. "
                        "We will keep you updated on the progress and "
                        "let you know once the issue has been resolved."
                    ),
                )
            else:
                # user created
                log.info("student created")
        except Exception as e:
            log.error("an exception occurred while creating user")
            self.system_errors.append(
                {"reason": "Failed to create student", "stack": str(e)},
            )
            await self.add_failed(
                failed_user=user,
                reason="An error occurred while creating the user profile.",
                upload_type=upload_type,
                solution=(
                    "Please review the data for any potential issues and "
                    "resubmit."
                ),
            )

    async def add_certificate(
        self,
        user_input: dict,
        page_url: str,
        upload_type: str,
        only_lms: bool,
    ) -> None:
        log.info(f"add_certificate_{user_input}")
        if not self.page:
            return
        try:
            user = validate_certificate_user(user_input)
            log.info(f"validate_certificate_{user=}")
            if not user.get("status"):
                await self.add_failed(
                    failed_user=user_input,
                    reason=user["reason"],
                    upload_type=upload_type,
                    solution=user["solution"],
                )
                return
            user = user.get("result")

            from src.utils.certificate_generation import tc_save_certificate

            saved = await tc_save_certificate(user)
            log.info(f"save_certificate_{saved=}")
            if not saved.get("status"):
                await self.add_failed(
                    failed_user=user,
                    reason=saved["reason"],
                    upload_type=upload_type,
                    solution=saved["solution"],
                )
                if saved.get("system"):
                    self.system_errors.append(
                        {"reason": saved["system"]},
                    )

            if only_lms:
                return

            await self.page.goto(page_url)

            await self.page.waitForXPath(
                '//a[contains(@href,"StudentCertificates/Create")]',
            )

            add_certification_button = await self.page.Jx(
                '//a[contains(@href,"StudentCertificates/Create")]',
            )

            await add_certification_button[0].click()

            await self.page.waitForSelector(
                "input[type='submit'][value='Create New Certificate']",
            )

            await self.page.waitForSelector("input#CourseId-selectized")
            await self.page.click("input#CourseId-selectized")

            await self.page.waitForXPath(
                f"""//form//div[contains(@class,"option")][contains(text(),"{user['course_name']}")]""",
            )
            course_option = await self.page.Jx(
                f"""//form//div[contains(@class,"option")][contains(text(),"{user['course_name']}")]""",
            )
            if not course_option:
                await self.add_failed(
                    failed_user=user,
                    reason="The course name provided does not match our records.",
                    upload_type=upload_type,
                    solution="Please correct the course name and resubmit the certificate.",
                )
                return
            await course_option[0].click()

            await self.page.waitForSelector(
                "input#CertificateNumber",
            )
            await self.page.type(
                "input#CertificateNumber",
                user["certificate_id"],
            )

            await self.page.waitForSelector(
                "input[name='IssueOrRefreshedOnDate']",
            )
            await self.page.Jeval(
                "input[name='IssueOrRefreshedOnDate']",
                f'''e=>e.value="{user['issue_date']}"''',
            )

            await self.page.waitForSelector(
                "input[name='ExpirationDate']",
            )
            await self.page.Jeval(
                "input[name='ExpirationDate']",
                f'''e=>e.value="{user['expiry_date']}"''',
            )

            await self.page.waitForSelector(
                "#TrainerName",
            )
            await self.page.type("#TrainerName", user["instructor"])

            from src.utils.certificate_generation import (
                tc_generate_certificate,
            )

            cert = await tc_generate_certificate(user)
            cert_path = cert.get("result")
            log.info(f"generated_certificate_{cert_path=}")
            if not cert.get("status"):
                await self.add_failed(
                    failed_user=user,
                    reason=cert.get("reason"),
                    upload_type=upload_type,
                    solution=cert.get("solution"),
                )
                if cert.get("system"):
                    self.system_errors.append(
                        {"reason": cert.get("system")},
                    )
                return

            await self.page.waitForSelector(
                "input[name='FormPhotoFile']",
            )
            file_input = await self.page.querySelector(
                "input[name='FormPhotoFile']",
            )
            if file_input:
                await file_input.uploadFile(cert_path)
            await self.page.waitFor(1000)

            await self.page.waitForSelector(
                "input[type='submit'][value='Create New Certificate']",
            )
            await self.page.click(
                "input[type='submit'][value='Create New Certificate']",
            )
            await self.page.waitFor(1000)

            await self.page.waitForXPath(
                '//*[contains(text(),"successfully created")]'
            )

            log.info(
                f"Successfully added certificate for {user.get('first_name')} {user.get('last_name')}",  # noqa: E501
            )

            os.remove(cert_path)
        except Exception as exception:
            log.exception(
                f"something went wrong when trying to add the users certificate with {exception=}",  # noqa: E501
            )
            traceback.print_exc()
            self.system_errors.append(
                {
                    "reason": f"Failed to add certificate for {user=} with {exception=}, more in logs.",
                    "stack": str(exception),
                },
            )
            await self.add_failed(
                failed_user=user,
                reason=(
                    "There was an error generating the user's certificate. "
                    "Issue to be fixed by our Programming Team: "
                    "There is a technical error that needs rectification "
                    "from our programming team to "
                    "ensure seamless data integration."
                ),
                upload_type=upload_type,
                solution=(
                    "Our developers are already on it and "
                    "we aim to resolve this promptly. "
                    "We will keep you updated on the progress and "
                    "let you know once the issue has been resolved."
                ),
            )
            return

    async def goto_user_profile(self, user_profile_url) -> None:
        if not self.page:
            return
        await self.page.goto(user_profile_url)
        return

    async def add_to_course_provider(self, page_url) -> None:
        if not self.page:
            return
        # go to users profile to start the updating of the user
        await self.goto_user_profile(page_url)
        await self.page.waitForSelector("input[type=submit]")

        # log.info("would attempt to click add to course provider now")
        # this will add the user to the course provider,
        # disabled in case of testing
        await self.page.click("input[type=submit]")
        return

    async def update_user(
        self,
        user: dict,
        page_url: str,
        upload_type: str,
        only_lms: bool,
    ) -> None:
        if not self.page:
            return
        # go to users profile to start the updating of the user
        await self.goto_user_profile(page_url)

        # if the course provider button is there,
        # run the function add to course provider on the link the
        # function returns and it will click to add the user
        course_provider_link = await self.page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('a.h6.sc-link'));
                    return buttons.filter(button => button.textContent.includes('Add To Course Provider')).map(button => button.href)[0];
                }""")  # noqa: E501

        if course_provider_link:
            await self.add_to_course_provider(course_provider_link)

        # if the certificate id sent from the excel is not none,
        # start adding the certificate
        await self.add_certificate(
            user,
            page_url,
            upload_type=upload_type,
            only_lms=only_lms,
        )

        # resets the match user so it can proceed onto the next one freely,
        # all runs asyncronously so it doesnt hit this til after
        # self.match_user_url = ""

    async def run_database_update(self, user_id, data) -> None:
        if not self.page:
            return
        try:
            self.match_user_url = self.page.url
            headshot = data["head_shot"] if data["head_shot"] else None
            del data["head_shot"]

            if headshot:
                img_data = requests.get(headshot).content  # noqa: ASYNC100
                location = f"{(uuid.uuid4())}.jpeg"

                with open(  # noqa: ASYNC101
                    f"/source/src/content/users/{location}",
                    "wb",
                ) as handler:
                    handler.write(img_data)

                data["head_shot"] = location

            updated = await update_lms_user(user_id=user_id, **data)

            if not updated:
                raise Exception("Failed to update user in the database")
        except Exception as e:
            try:
                notification_content = {
                    "reason": "Unable to update user in the database",
                    "solution": (
                        "Additional information is required to proceed. "
                        "Please upload this user manually."
                    ),
                }
                try:
                    user = await get_user(user_id=user_id)
                    user_json = user.dict()
                    if isinstance(user_json, dict):
                        notification_content.update(user_json)
                except:  # noqa: E722
                    ...
                expedited_failed_user_notification(
                    email=self.email,
                    content=notification_content,
                )
            except Exception as e:
                log.error(
                    "an error occurred while sending failed notification",
                )
                self.system_errors.append(
                    {
                        "reason": "An error occurred while sending notification",  # noqa: E501
                        "stack": str(e),
                    },
                )
            log.error(
                "Something went wrong when trying to update the user in the database",  # noqa: E501
            )
            self.system_errors.append(
                {
                    "reason": "An error occurred while running database update",  # noqa: E501
                    "stack": str(e),
                },
            )

    async def check_match(
        self,
        user,
        user_url,
        amount,
        index,
        upload_type: str,
        only_lms: bool,
    ) -> None:
        if not self.page:
            return
        # visit users profile url to start validation
        log.debug("Going to user profile")
        await self.goto_user_profile(user_url)
        await self.page.waitForSelector(
            ".sc-field-value",
            visible=True,
            timeout=10000,
        )
        await self.page.waitFor(5000)

        image = str(
            await self.page.evaluate(
                'document.querySelector(".sc-header-photo.mx-auto.mx-md-0.d-block.d-md-flex").src',
            ),
        )
        # this is what actually gets all the elements /field values which
        # allows for us to get the values and check for matches
        field_values_elements = await self.page.querySelectorAll(
            ".sc-field-value",
        )

        field_values = []

        for field_value_element in field_values_elements:
            field_value = await self.page.evaluate(
                "(element) => element.textContent",
                field_value_element,
            )
            field_value = field_value.strip()
            field_values.append(field_value)

        # 5, 6, 7 are the phone, email and birthdate listed on a users profile,
        # these are used to get the value of them
        # and then compare them to the actual users info below
        match_field_values_indexes = {5: "phone", 6: "email", 7: "birthDate"}

        matches = 0

        if "MissingPerson" in image:
            image = None

        height = 0
        if field_values[2]:
            try:
                # Split the string on the apostrophe to separate
                # feet and inches
                parts = field_values[2].split("' ")
                feet = int(parts[0])  # Convert the feet part to an integer
                # Remove the inch symbol and convert to an integer
                inches = int(parts[1].replace('"', ""))
                # Calculate total inches
                height = feet * 12 + inches
            except Exception:
                log.info("Failed to convert height")

        dob = None
        if field_values[7]:
            try:
                dob = datetime.datetime.strptime(field_values[7], "%m/%d/%Y")
            except Exception:
                try:
                    dob = datetime.datetime.strptime(
                        field_values[7],
                        "%m-%d-%Y",
                    )
                except Exception:
                    log.exception(f"Failed to convert DOB {field_values[7]}")

        url_data = {
            "head_shot": image,
            "photo_id": field_values[0],
            "eye_color": field_values[1],
            "height": height,
            "gender": field_values[4],
            "phone_number": field_values[5],
            "email": field_values[6],
            "dob": dob,
            "address": field_values[8],
        }

        pattern = re.compile(
            r"(?P<address>.*),\s*(?P<city>[^\d]+)\s*(?P<state>[A-Za-z]+)\s*(?P<zipcode>\d+)",
        )

        match = pattern.match(url_data["address"])
        if match:
            url_data["address"] = match.group("address")  # type: ignore
            url_data["city"] = match.group("city")
            url_data["state"] = match.group("state")
            url_data["zipcode"] = match.group("zipcode")

        for field_value_index, field_value in enumerate(field_values):
            if matches >= 2:
                break

            if field_value_index not in match_field_values_indexes:
                continue

            match_field_key = match_field_values_indexes[field_value_index]
            # this will check if the fields above values are equal to the users

            try:
                if match_field_key == "phone" and user.get("phone_number"):
                    phone = (
                        field_value.replace("-", "")
                        .replace(" ", "")
                        .replace("(", "")
                        .replace(")", "")
                    )
                    user_phone = int(
                        re.sub(r"\D", "", str(user["phone_number"])),
                    )

                    if str(phone) == str(user_phone):
                        matches += 1

                if match_field_key == "email" and user.get("email"):
                    email = field_value.lower()
                    user_email = user["email"].lower()

                    if str(email) == str(user_email):
                        matches += 1

                if match_field_key == "birthDate" and user.get(
                    "date_of_birth",
                ):
                    birth_date = datetime.datetime.strptime(
                        field_value,
                        "%m/%d/%Y",
                    )
                    birth_date = birth_date.strftime("%Y-%m-%d")

                    try:
                        user_birth_date = datetime.datetime.strptime(
                            user["date_of_birth"],
                            "%Y-%m-%d %H:%M:%S",
                        )
                    except ValueError:
                        user_birth_date = datetime.datetime.strptime(
                            user["date_of_birth"],
                            "%m/%d/%Y",
                        )
                    user_birth_date = user_birth_date.strftime("%Y-%m-%d")

                    if str(birth_date) == str(user_birth_date):
                        matches += 1
            except Exception as e:
                log.exception("something went wrong while checking matches")
                self.system_errors.append(
                    {
                        "reason": "Failed to check matches for user.",
                        "stack": str(e),
                    },
                )
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "An error occurred during the "
                        "profile matching process."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "We request that you manually review and "
                        "provide the correct information."
                        "Our developers have been notified of this issue and "
                        "will be in contact with you via email "
                        "in order to resolve any other issues."
                    ),
                )
                return

        # currently functionality states if TWO matches are found
        # on a users profile, attempt to update, otherwise
        # check if the amount of users found on STUDENT LOOKUP is
        # equal to one, if so it only requires ONE match on the users profile
        if matches >= 2:
            self.match_user_url = self.page.url
            if upload_type == "update_user":
                await self.run_database_update(
                    user_id=user["user_id"],
                    data=url_data,
                )
            if upload_type == "certificate":
                await self.update_user(
                    user,
                    self.match_user_url,
                    upload_type=upload_type,
                    only_lms=only_lms,
                )
            if upload_type in ["student", "upload_user"]:
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "It appears the user already exists in our system."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "Please verify "
                        "if the data might have been uploaded previously."
                    ),
                )
            return

        if amount == 1 and matches >= 1:
            self.match_user_url = self.page.url
            if upload_type == "update_user":
                await self.run_database_update(
                    user_id=user["user_id"],
                    data=url_data,
                )
            if upload_type == "certificate":
                await self.update_user(
                    user,
                    self.match_user_url,
                    upload_type=upload_type,
                    only_lms=only_lms,
                )
            if upload_type in ["student", "upload_user"]:
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "It appears the user already exists in our system."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "Please verify "
                        "if the data might have been uploaded previously."
                    ),
                )
            return

        if (
            index == amount - 1
            and not self.match_user_url
            and upload_type == "certificate"
        ):
            log.error("not enough matches found on users profile")
            await self.add_failed(
                failed_user=user,
                reason=(
                    "Email, phone number, or birthdate "
                    "did not match our records."
                ),
                upload_type=upload_type,
                solution=(
                    "Please confirm these details "
                    "and resubmit them accurately."
                ),
            )

        return

    async def do_lookup(
        self,
        user: dict,
        upload_type: str,
        only_lms: bool = False,
        retries: int = 0,
    ) -> None:
        if retries > 0:
            log.debug(f"retrying do_lookup,  attempt:{retries}")

        if not self.page:
            return
        if not user.get("first_name"):
            await self.add_failed(
                failed_user=user,
                reason=(
                    "Registration entry is incomplete without a first name."
                ),
                upload_type=upload_type,
                solution=(
                    "Please provide this critical information and resubmit."
                ),
            )
            return

        if not user.get("last_name"):
            await self.add_failed(
                failed_user=user,
                reason=(
                    "A last name is required for the registration process."
                ),
                upload_type=upload_type,
                solution=(
                    "Kindly update this information "
                    "at your earliest convenience."
                ),
            )
            return

        log.debug(
            f"log 1: looking up {user['first_name']} {user['last_name']}",
        )
        log.debug(f"upload type is {upload_type}")

        if upload_type in ["student", "update_user", "upload_user"] or (
            not user.get("osha_id")
            and not user.get("sstid")
            and not user.get("our_student")
        ):
            log.debug(
                "user has no sst or osha and is not tagged as 'our_student'",
            )
            reason = ""
            try:
                await self.page.goto(
                    "https://dob-trainingconnect.cityofnewyork.us/CourseProviders/StudentLookup/36cd1e6e-62b5-4770-ad4f-08d97ed9594c?type=StudentName",  # noqa: E501
                )

                await self.page.evaluate(
                    f"document.getElementById('StudentName').value = \"{user['first_name'].strip()} {user['last_name'].strip()}\"",  # noqa: E501
                )
                await self.page.click("input[type='submit']")
                try:
                    log.debug("looking for students")
                    await self.page.waitForSelector(
                        "a[role='button']",
                        timeout=10000,
                    )

                    view_buttons = await self.page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll("a[role='button']"));
                        return buttons.filter(button => button.textContent.includes('View')).map(button => button.href);
                    }""")  # noqa: E501
                    view_buttons = list(view_buttons)
                    log.debug("amount of students found")
                    log.debug(len(view_buttons))

                except Exception:
                    log.info("no users found")
                    view_buttons = []

                if len(view_buttons) >= 10:
                    # do we want different functionality for this if the
                    # upload type is expedited?
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "Registration was deferred due to "
                            "excessive user profiles requiring verification."
                        ),
                        upload_type=upload_type,
                        solution=(
                            "Additional information is required to proceed. "
                            "Please upload this user manually."
                        ),
                    )
                    return

                for idx, user_profile in enumerate(view_buttons):
                    if not self.match_user_url:
                        log.debug("checking user")
                        await self.check_match(
                            user=user,
                            user_url=user_profile,
                            amount=len(view_buttons),
                            index=idx,
                            upload_type=upload_type,
                            only_lms=only_lms,
                        )

                if not self.match_user_url:
                    log.debug("no match found for user")

                if (
                    upload_type in ["student", "upload_user"]
                    and not self.match_user_url
                ):
                    log.info("creating student")
                    await self.create_student(
                        user=user,
                        upload_type=upload_type,
                    )
                    return

                if not self.match_user_url and upload_type not in [
                    "student",
                    "upload_user",
                ]:
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "No corresponding user information "
                            "was found in Training Connect."
                        ),
                        upload_type=upload_type,
                        solution=(
                            "Please verify "
                            "the accuracy of the submission and try again."
                        ),
                    )

            except (KeyError, TimeoutError) as e:
                log.error(
                    "Selector element was not found on page meaning the user had zero results",  # noqa: E501
                )
                reason = "An error occurred while adding certificate, please manually upload."  # noqa: E501
                if upload_type in ["student", "upload_user"]:
                    reason = "An error occurred while creating student, please manually upload."  # noqa: E501
                    self.system_errors.append(
                        {
                            "reason": "Failed to create student",
                            "stack": str(e),
                        },
                    )
                else:
                    self.system_errors.append(
                        {
                            "reason": "Failed to upload certificate to student",  # noqa: E501
                            "stack": str(e),
                        },
                    )

            except Exception as e:
                log.error("an exception occurred")
                self.system_errors.append(
                    {
                        "reason": "An exception occurred while doing lookup for training connect",  # noqa: E501
                        "stack": str(e),
                    },
                )
                await self.add_failed(
                    failed_user=user,
                    reason=reason
                    or (
                        "The specific issue could not be determined."
                        "Please contact our support team for "
                        "detailed assistance via email."
                    ),
                    upload_type=upload_type,
                )

        if user.get("sstid"):
            log.debug(f"user has sstID: {user.get('sstid')}")
            try:
                await self.page.goto(
                    "https://dob-trainingconnect.cityofnewyork.us/CourseProviders/StudentLookup/36cd1e6e-62b5-4770-ad4f-08d97ed9594c?type=CardId",
                )

                await self.page.evaluate(
                    f"document.getElementById('CardId').value = \"{user['sstid']}\"",  # noqa: E501
                )
                await self.page.click("input[type='submit']")
                await self.page.waitForSelector(
                    "a[role='button']",
                    timeout=10000,
                )

                url = await self.page.evaluate(
                    "document.querySelector(`a[role='button']`).href",
                )

                await self.update_user(
                    user,
                    url,
                    upload_type=upload_type,
                    only_lms=only_lms,
                )
            except (KeyError, TimeoutError):
                log.error(
                    "Selector element was not found on page meaning the user had zero results",  # noqa: E501
                )
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "A lookup error occurred for this user's information."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "We ask that you manually verify and update the data. "
                        "Please email our development team "
                        "to investigate further this issue. "
                        "In the meantime, please upload this profile manually."
                    ),
                )

            except Exception as e:
                log.error("an exception occurred")
                self.system_errors.append(
                    {
                        "reason": "An exception occurred while doing lookup for training connect",  # noqa: E501
                        "stack": str(e),
                    },
                )
                await self.add_failed(
                    failed_user=user,
                    reason=reason
                    or (
                        "The specific issue could not be determined. "
                        "Please contact our support team for "
                        "detailed assistance via email."
                    ),
                    upload_type=upload_type,
                )

        if user.get("osha_id"):
            log.info(f"user has osha_id {user.get('osha_id')}")
            try:
                await self.page.goto(
                    "https://dob-trainingconnect.cityofnewyork.us/CourseProviders/StudentLookup/36cd1e6e-62b5-4770-ad4f-08d97ed9594c?type=OshaId",
                )

                await self.page.evaluate(
                    f"document.getElementById('OshaId').value = '{user['osha_id']}'",  # noqa: E501
                )
                await self.page.click("input[type='submit']")
                await self.page.waitForSelector(
                    "a[role='button']",
                    timeout=10000,
                )

                url = await self.page.evaluate(
                    "document.querySelector(`a[role='button']`).href",
                )

                await self.update_user(
                    user,
                    url,
                    upload_type=upload_type,
                    only_lms=only_lms,
                )
            except (KeyError, TimeoutError):
                log.error(
                    "Selector element was not found on page meaning the user had zero results",  # noqa: E501
                )
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "No corresponding user information "
                        "was found in Training Connect."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "Please verify the accuracy of the submission and "
                        "try again."
                    ),
                )
            except Exception as e:
                log.error("an exception occurred")
                self.system_errors.append(
                    {
                        "reason": "An exception occurred while doing lookup for training connect",  # noqa: E501
                        "stack": str(e),
                    },
                )
                await self.add_failed(
                    failed_user=user,
                    reason=reason
                    or (
                        "A lookup error occurred for this user's information. "
                        "We ask that you manually verify and update the data. "
                        "Please email our development team "
                        "to investigate further this issue. "
                        "In the meantime, please upload this profile manually."
                    ),
                    upload_type=upload_type,
                )

        if user.get("our_student"):
            log.debug("user is tagged as our student")
            try:
                first_name = user["first_name"].strip()
                last_name = user["last_name"].strip()

                await self.page.goto(
                    f"https://dob-trainingconnect.cityofnewyork.us/CourseProviders/Dashboard/36cd1e6e-62b5-4770-ad4f-08d97ed9594c?Filter={first_name}+{last_name}",
                )

                table_body = await self.page.waitForSelector(
                    "table tbody",
                    visible=True,
                )

                table_body_rows = await table_body.querySelectorAll("tr")

                amount_of_users = len(table_body_rows)

                if amount_of_users == 0:
                    log.info("No user found in Training Connect.")

                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "No corresponding user information "
                            "was found in Training Connect."
                        ),
                        upload_type=upload_type,
                        solution=(
                            "Please verify the accuracy of the submission and "
                            "try again."
                        ),
                    )

                if 1 <= amount_of_users <= 10:
                    # go through each user and validate them here
                    view_buttons = await self.page.evaluate("""() => {
                        const buttons = Array.from(document.querySelectorAll('a.btn.btn-light'));
                        return buttons.filter(button => button.textContent.includes('View')).map(button => button.href);
                    }""")  # noqa: E501

                    for idx, user_profile in enumerate(view_buttons):
                        if not self.match_user_url:
                            await self.check_match(
                                user=user,
                                user_url=user_profile,
                                amount=amount_of_users,
                                index=idx,
                                upload_type=upload_type,
                                only_lms=only_lms,
                            )
                    self.match_user_url = ""
                elif amount_of_users > 10:
                    await self.add_failed(
                        failed_user=user,
                        reason=(
                            "Registration was deferred due to "
                            "excessive user profiles requiring verification."
                        ),
                        upload_type=upload_type,
                        solution=(
                            "Additional information is required to proceed. "
                            "Please upload this user manually."
                        ),
                    )
                    log.info("added to failed array")
            except (NetworkError, TimeoutError):
                if retries == 0:
                    return await self.do_lookup(
                        user=user,
                        upload_type=upload_type,
                        only_lms=only_lms,
                        retries=retries + 1,
                    )
                log.error(
                    "Selector element was not found on page meaning the user had zero results",  # noqa: E501
                )
                await self.add_failed(
                    failed_user=user,
                    reason=(
                        "No corresponding user information "
                        "was found in Training Connect."
                    ),
                    upload_type=upload_type,
                    solution=(
                        "Please verify the accuracy of the submission and "
                        "try again."
                    ),
                )
            except Exception as e:
                log.error("an exception occurred")
                self.system_errors.append(
                    {
                        "reason": "An exception occurred while doing lookup for training connect",  # noqa: E501
                        "stack": str(e),
                    },
                )
                await self.add_failed(
                    failed_user=user,
                    reason=reason
                    or (
                        "A lookup error occurred for this user's information. "
                        "We ask that you manually verify and update the data. "
                        "Please email our development team "
                        "to investigate further this issue. "
                        "In the meantime, please upload this profile manually."
                    ),
                    upload_type=upload_type,
                )

        self.match_user_url = ""
        return

    async def create_browser_and_login(self, retries: int = 0):  # noqa: ANN201
        if retries >= 5:
            log.error("Failed all retries to log in")
            self.system_errors.append(
                {
                    "reason": "Failed to log in to training connect",
                    "stack": "create_browser_and_login max retries reached line 842",  # noqa: E501
                },
            )
            return False

        if self.page:
            await self.page.close()

        if self.browser:
            await self.browser.close()

        self.page = None
        self.browser = None
        self.logged_in = False

        try:
            log.info("starting browser and logging in...")
            self.browser = await launch(
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

            self.page = await self.browser.newPage()

            await asyncio.gather(self.login())
            return True
        except Exception:
            log.error("THERE WAS AN ERROR, RELOGGING IN")
            await asyncio.sleep(5)
            return await self.create_browser_and_login(retries=retries + 1)

    async def run_queue_item(self, user_json: dict, retries: int = 1) -> None:
        if retries >= 5:
            log.error("Max retries for queue item reached")
            self.system_errors.append(
                {
                    "reason": "Failed to load user json",
                    "stack": "run_queue_item max retries reached line 858",
                },
            )
            await self.add_failed(
                failed_user=user_json,
                reason=(
                    "Multiple attempts to verify "
                    "this user's details have been unsuccessful."
                ),
                upload_type=user_json["upload_info"]["upload_type"]
                if user_json.get("upload_info")
                else "unable to get upload type",
                solution=(
                    "Please email our development team "
                    "to investigate further this issue. "
                    "In the meantime, please upload this profile manually."
                ),
            )
            return

        try:
            upload_info = user_json["upload_info"]
            upload_type = user_json["upload_info"]["upload_type"]
            only_lms = user_json["upload_info"].get("only_lms", False)
            log.debug(user_json)
            log.debug(
                str(upload_info["position"]) + " " + str(upload_info["max"]),
            )

            if upload_info["position"] == 1:
                self.email = upload_info["uploader"]

            if not self.logged_in:
                log.debug("Not logged in, logging in")
                logged_in = await self.create_browser_and_login()
                if not logged_in:
                    await self.run_queue_item(user_json, retries=retries + 1)

        except Exception as e:
            log.error("Failed json loading user")
            self.system_errors.append(
                {"reason": "Failed to load user json", "stack": str(e)},
            )
            return

        if user_json:
            try:
                log.debug("Attempting look up")
                await self.do_lookup(
                    user=user_json,
                    upload_type=upload_type,
                    only_lms=only_lms,
                )
            except Exception:
                log.error(
                    "An exception occurred while doing lookup... retrying",
                )

                if self.page:
                    await self.page.close()

                if self.browser:
                    await self.browser.close()

                self.page = None
                self.browser = None
                self.logged_in = False

                await self.run_queue_item(user_json, retries=retries + 1)

        if upload_info["position"] == upload_info["max"]:
            log.info("cleaning up for next queue...")

            failed_users = [user for user in self.users if user.get("failed")]
            if upload_type == "certificate":
                failed_tmps = [tmp for tmp in self.tmpfiles if tmp["failed"]]
                try:
                    certification_failed_users_notification(
                        self.email,
                        failed_users,
                        failed_tmps,
                        upload_info["file_name"],  # type: ignore
                    )
                except Exception as e:
                    log.error(
                        "an error occurred while sending failed notification",
                    )
                    self.system_errors.append(
                        {
                            "reason": "Final retry reached while doing lookup",
                            "stack": str(e),
                        },
                    )
            if upload_type in ["student", "upload_user"]:
                try:
                    student_failed_users_notification(
                        self.email,
                        failed_users,
                        upload_info.get("file_name"),
                    )
                except Exception as e:
                    log.error(
                        "an error occurred while sending failed notification",
                    )
                    self.system_errors.append(
                        {
                            "reason": "An error occurred while sending notification",  # noqa: E501
                            "stack": str(e),
                        },
                    )
            if upload_type == "update_user" and not self.match_user_url:
                try:
                    notification_content = {
                        "reason": (
                            "No corresponding user information "
                            "was found in Training Connect."
                        ),
                        "solution": (
                            "Please verify "
                            "the accuracy of the submission and try again."
                        ),
                    }
                    if isinstance(user_json, dict):
                        notification_content.update(user_json)
                    expedited_failed_user_notification(
                        email=self.email,
                        content=notification_content,
                    )
                except Exception as e:
                    log.error(
                        "an error occurred while sending failed notification",
                    )
                    self.system_errors.append(
                        {
                            "reason": "An error occurred while sending notification",  # noqa: E501
                            "stack": str(e),
                        },
                    )

            self.email = ""
            self.match_user_url = ""

            self.users.clear()
            self.tmpfiles.clear()
            if self.page:
                await self.page.close()
            if self.browser:
                await self.browser.close()
            self.page = None
            self.browser = None
            self.logged_in = False
        await asyncio.sleep(3)
        return

    async def run_queue_task(self, uploads: str) -> None:
        if not uploads:
            return

        try:
            users = json.loads(uploads)
        except Exception:
            log.exception("Failed json loading users")

        for user_json in users:
            await self.run_queue_item(user_json=user_json)

        if self.system_errors:
            training_connect_failure_notification(
                body=json.dumps(self.system_errors),
            )
            self.system_errors = []

    async def handle_queue(self) -> None:
        while True:
            await asyncio.sleep(1)
            if self.queue_running:
                continue

            async with self.queue_lock:
                uploads = await self.redis_lpop()

                if not uploads:
                    self.queue_running = False
                    continue

                log.info("Queue Items found")
                self.queue_running = True
                await self.run_queue_task(uploads)
                self.queue_running = False

    async def start_queue(self) -> None:
        self.redis = await self.redis_connection()
        if not self.redis:
            self.system_errors.append(
                {
                    "reason": "Fatal error connecting to redis",
                    "stack": "start_queue redis connection max retries reached line 1021",  # noqa: E501
                },
            )
            if self.system_errors:
                training_connect_failure_notification(
                    body=json.dumps(self.system_errors),
                )
            self.system_errors = []
            return
        # pubsub = await self.redis.start_subscribe()
        # await pubsub.subscribe(
        #     [os.getenv("TRAINING_CONNECT_QUEUE", "training_connect_queue")],
        # )

        # while True:
        #     message = await pubsub.next_published()
        #     user = message.value
        #     async with self.queue_lock:
        #         self.queue.append(user)

    async def login(self) -> Union[bool, None]:
        if not self.page:
            return
        # go to the sign in link
        await self.page.goto(
            "https://dob-trainingconnect.cityofnewyork.us/Saml/InitiateSingleSignOn",
        )
        try:
            await self.page.waitForSelector(
                'input[name="username"]',
                visible=True,
                timeout=30000,
            )
        except Exception:
            log.exception("Failed to find login selector")
            return False

        logged_in = await self.page.querySelector(
            ".alert.alert-success.alert-dismissible.fade.show",
        )

        if logged_in:
            log.debug("already logged in")
            self.logged_in = True
            return True

        # after done waiting for username input to appear, enter information
        await self.page.type(
            'input[name="username"]',
            os.getenv("TRAINING_CONNECT_EMAIL", ""),
        )
        await self.page.type(
            'input[name="password"]',
            os.getenv("TRAINING_CONNECT_PASSWORD", ""),
        )
        await self.page.click('input[type="submit"]')

        # wait for logged in selector to be present and then validate
        # if it says logged in,
        # if so start analyzation of users
        await self.page.waitForSelector(
            ".alert.alert-success.alert-dismissible.fade.show",
            visible=True,
        )
        result = await self.page.evaluate(
            'document.body.innerText.includes("logged in")',
        )

        if not result:
            log.debug("not logged in")
            return False

        log.debug("logged in")
        self.logged_in = True
        return True

    async def redis_publish(self, user: global_models.User) -> dict:
        try:
            json_data = [
                {
                    "user_id": user.userId,
                    "first_name": user.firstName,
                    "last_name": user.lastName,
                    "phone_number": user.phoneNumber,
                    "email": user.email,
                    "upload_info": {
                        "uploader": os.getenv(
                            "COMPANY_EMAIL",
                            "rmiller@doitsolutions.io",
                        ),
                        "upload_type": "student",
                        "position": 1,
                        "max": 1,
                        "only_lms": False,
                    },
                },
            ]
            json_data = json.dumps(json_data)

            published = await self.redis_rpush(json_data)
            if not published:
                raise Exception(
                    "Failed to push data to training connect redis",
                )

            return {"status": True, "published": json_data}
        except Exception as exception:
            log.exception(
                f"Failed to publish to redis with {exception=} for {user.dict()=}",
            )
            traceback.print_exc()

        return {
            "status": False,
            "reason": "Failed to publish to training connect redis",
            "solution": "Contact support for assistance",
            "system": f"Failed to publish to training connect redis for {user.dict()=}, more in logs",
        }

    async def redis_check(self) -> bool:
        try:
            if not (self.redis and await self.redis.ping()):
                self.redis = await self.redis_connection()

            return self.redis and await self.redis.ping()
        except Exception as ex:
            log.exception(f"redis connection issues, exception={str(ex)}")
            return False

    async def redis_rpush(self, data: str, retries: int = 1) -> bool:
        if not await self.redis_check():
            return False

        try:
            await self.redis.rpush(self.redis_list_key, data)
            return True
        except Exception as ex:
            if retries:
                return await self.redis_rpush(data, retries=0)
            log.exception(
                f"redis rpush issues, data={data} exception={str(ex)}",
            )
            return False

    async def redis_lpop(self, retries: int = 1) -> Union[str, None]:
        if not await self.redis_check():
            return None

        try:
            uploads = await self.redis.lpop(self.redis_list_key)  # type: ignore
            if uploads:
                return uploads.decode("utf-8")  # type: ignore
            return None
        except Exception as ex:
            if retries:
                return await self.redis_lpop(retries=0)
            log.exception(f"redis lpop issues, exception={str(ex)}")
            return None

    async def start_system(self) -> None:
        # launch the browser
        log.info("starting training connect....")

        await asyncio.gather(self.start_queue(), self.handle_queue())
