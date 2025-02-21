import datetime
import json
import logging
import os
import smtplib
import traceback  # Import the traceback module
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class CustomExceptionHandler(logging.Handler):
    def emit(self, record) -> None:
        if record.exc_info:
            current_time = datetime.datetime.utcnow()
            subject = (
                f"{os.getenv('COMPANY_NAME', '')} Exception "
                f"occured email {datetime.datetime.strftime(current_time, '%m/%d/%Y %-I:%M %p')}"  # noqa: E501
            )

            # Format the exception information into a string
            exception_string = "".join(
                traceback.format_exception(*record.exc_info),
            )

            body = json.dumps(
                {
                    "company name": os.getenv("COMPANY_NAME", ""),
                    "company email": os.getenv("COMPANY_EMAIL", ""),
                    "company phone": os.getenv("COMPANY_PHONE", ""),
                    "company url": os.getenv("COMPANY_URL", ""),
                    "error message": record.msg,
                    "file name": record.filename,
                    "line number": record.lineno,
                    "log level": record.levelname,
                    "stack": exception_string,  # Use the formatted exception string  # noqa: E501
                },
                indent=4,
            )
            try:
                if not os.getenv("ENVIRONMENT", "dev").lower() == "prod":
                    # create message
                    message = MIMEMultipart()
                    message["From"] = os.getenv(
                        "COMPANY_EMAIL",
                        "info@doitsolutions.io",
                    )
                    message["To"] = ",".join(
                        [
                            "aosmolovsky@doitsolutions.io",
                            "rmiller@doitsolutions.io",
                        ],
                    )
                    body = MIMEText(body, "plain")
                    message["Subject"] = subject

                    # Open connection
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
                    # send mail
                    session.sendmail(
                        os.getenv("COMPANY_EMAIL", ""),
                        [
                            "aosmolovsky@doitsolutions.io",
                            "rmiller@doitsolutions.io",
                        ],
                        message.as_string(),
                    )
                    # close connection
                    session.quit()

            except Exception:
                print("Failed to send email")  # noqa: T201
        logging.StreamHandler().emit(record)


def get_logger(logger_name: str, log_level: str = "DEBUG") -> logging.Logger:
    """Default logger to set up in code logging

    Args:
        logger_name (str): Name for logger
        log_level (str, optional): Log level for printing to terminal. Defaults to 'DEBUG'.

    Returns:
        logging.Logger: Returns logging object to initialize logger with
    """  # noqa: E501
    logger = logging.getLogger(logger_name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        # '%(asctime)s [%(levelname)s] [%(name)s] %(message)s')
        "%(asctime)s [%(levelname)s] %(message)s",
    )
    handler.setFormatter(formatter)
    # exceptionHandler = CustomExceptionHandler()
    logger.addHandler(handler)
    # logger.addHandler(exceptionHandler)
    logger.setLevel(log_level)
    return logger


log = get_logger(
    logger_name=os.getenv("LOGGER_NAME", "LMS_API"),
    log_level=os.getenv("LOG_LEVEL", "INFO"),
)
