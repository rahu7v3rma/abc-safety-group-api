import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from icalendar import Alarm, Calendar, Event

from src.utils.log_handler import log


def build_email(
    sender: str,
    receiver: list,
    subject: str,
    body: str,
    body_type: str = "plain",
    attachments: Optional[list] = None,
    cc: Optional[List[str]] = None,
) -> MIMEMultipart:
    """Function to build an email

    Args:
        sender (str): Email of who is sending the email
        receiver (str): Email fo who is receiving the email
        subject (str): Subject of the email
        body (str): Body of the email
        body_type (str, optional): Whether its HTML or Plain text. Defaults to 'plain'.
        attachments (list, optional): Any attachments to the image. Defaults to None.

    Returns:
        MIMEMultipart: The email built out
    """  # noqa: E501

    message = MIMEMultipart()
    message["From"] = sender
    message["To"] = ",".join(receiver)
    if cc:
        message["Cc"] = ",".join(cc)

    message["Subject"] = subject

    if body_type.lower() == "html":
        body = MIMEText(body, "html")  # type: ignore

    if body_type.lower() == "plain":
        body = MIMEText(body, "plain")  # type: ignore

    message.attach(body)

    if not attachments:
        return message

    for idx, attachment in enumerate(attachments):
        payload = MIMEBase("application", "octet-stream")
        try:
            payload.set_payload(open(attachment, "rb").read())
            file_name = os.path.basename(attachment)
            payload.add_header(
                "Content-Disposition",
                f"attachment; filename=attachment-{file_name}",
            )
        except Exception:
            try:
                payload.set_payload(attachment.getvalue())
                file_name = "certificates.zip"
                payload.add_header(
                    "Content-Disposition",
                    f"attachment; filename={file_name}",
                )
            except Exception:
                log.exception("an exception occured")
        encoders.encode_base64(payload)
        message.attach(payload)
    return message


def get_session() -> smtplib.SMTP:
    """Funciton to get SMTP session

    Returns:
        smtplib.SMTP: Session to be used in other functions
    """

    session = smtplib.SMTP(
        host=os.getenv("SMTP_URL", ""),
        port=int(os.getenv("SMTP_PORT", 587)),
    )
    session.starttls()
    session.login(
        os.getenv("SMTP_USERNAME", ""),
        os.getenv("SMTP_PASSWORD", ""),
    )
    session.ehlo(os.getenv("SMTP_DOMAIN", ""))
    return session


def send_email(
    receiver: List[str],
    email_content: dict,
    sender: Optional[str] = None,
    cc: Optional[List[str]] = None,
) -> bool:
    """function to send email

    Args:
        sender (str, optional): email of whoever is sending the email. Defaults to None.
        receiver (str, optional): email of whoever is meant to receive the email. Defaults to None.
        email_content (dict, optional): content of the email, attachments, etc.. Defaults to None.

    Returns:
        bool: true if sent successfully, false if failed
    """  # noqa: E501

    if not os.getenv("USE_EMAIL", "false").lower() == "true":
        return True

    if not sender:
        sender = os.getenv("SMTP_USERNAME", "")

    if not receiver:
        return False

    if not email_content:
        return False

    subject = email_content["subject"]
    body = email_content["body"]
    attachments = email_content.get("attachments")

    message = build_email(
        sender=sender,
        receiver=receiver,
        subject=subject,
        body=body,
        body_type="html",
        attachments=attachments,
        cc=cc,
    )

    session = get_session()
    session.sendmail(sender, receiver, message.as_string())
    session.quit()

    return True


def class_calendar_invite(
    class_time: dict,
    course: dict,
    user: Optional[dict] = None,
    cancel: bool = False,
) -> str:
    """Function to create a calendar invite

    Args:
        class_time (dict): dict of class's components
        course (dict): dict of course's components
        user (dict): dict of users's components
        cancel (bool, optional): bool to depict whether or not the event is to be canceled. Defaults to False.

    Returns:
        str: returns file path to invite
    """  # noqa: E501
    cal = Calendar()
    cal.add("method", "CANCEL" if cancel else "REQUEST")

    event = Event()
    # Add basic components
    event.add(
        "summary",
        f"{course['courseName']} Class #{class_time['series_number']}",
    )

    location = ""
    if course["remoteLink"]:
        location += f"Remote Meeting Link:\n{course['remoteLink']}\n"
    if course["address"]:
        location += f"Address:\n{course['address']}"
    event.add(
        "description",
        f"Topic: {'Canceled' if cancel else 'Scheduled'} calendar invite for "
        f"{course['courseName']}\nTime: {class_time['start_dtm'].strftime('%m/%d/%Y %-I:%M %p')} "  # noqa: E501
        f"Eastern Time (US and Canada)\n{location}",
    )
    if user:
        event.add("attendee", user["email"])

    event.add("organizer", course["email"])
    event.add("status", "confirmed")
    event.add("category", "Event")

    # Add locations
    for instruction_type in course["instructionTypes"]:
        if instruction_type.lower() == "remote":
            event.add("location", course["remoteLink"])
            event.add("url", course["remoteLink"])
        if instruction_type.lower() == "in-person":
            event.add("location", course["address"])

    # Add dates
    event.add("dtstart", class_time["start_dtm"])
    event.add("dtend", class_time["end_dtm"])

    # Add a reminder a 3 days before the event
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", "Reminder")
    alarm.add("TRIGGER;RELATED=START", "-P{0}D".format(3))
    event.add_component(alarm)

    # Add a reminder a 3 hours before the event starts
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", "Reminder")
    alarm.add("TRIGGER;RELATED=START", "-P{0}H".format(3))
    event.add_component(alarm)

    # Add a reminder a 1 hours before the event starts
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", "Reminder")
    alarm.add("TRIGGER;RELATED=START", "-P{0}H".format(1))
    event.add_component(alarm)

    cal.add_component(event)

    reminder_location = f'/source/src/content/reminders/{course["courseName"]}-{class_time["series_number"]}.ics'  # noqa: E501
    with open(reminder_location, "wb") as f:
        f.write(cal.to_ical())

    return reminder_location
