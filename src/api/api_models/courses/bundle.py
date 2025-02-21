from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput
from src.api.api_models.global_models import Bundle


class Input(BaseInput):
    bundleName: str  # noqa: N815
    active: bool = False
    maxStudents: Optional[int] = 20  # noqa: N815
    waitlist: bool = False
    price: float
    allowCash: bool  # noqa: N815
    courseIds: List[str]  # noqa: N815
    # prerequisits: Optional[List[str]] = None
    # description: Optional[str]
    # briefDescription: Optional[str]


class Student(BaseModel):
    userId: str  # noqa: N815
    headShot: Optional[str]  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    phoneNumber: Optional[str]  # noqa: N815
    email: Optional[str]
    dob: Optional[str]
    paid: bool
    usingCash: bool  # noqa: N815
    registrationStatus: str  # noqa: N815
    notes: Optional[str]
    transaction: Optional[str]


class StudentPayload(BaseModel):
    students: List[Optional[Student]]


class StudentOutput(BaseModel):
    payload: StudentPayload


class Schedule(BaseModel):
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815
    duration: Optional[int]
    seriesNumber: int  # noqa: N815
    complete: bool


class Payload(BaseModel):
    bundle: Bundle
    schedule: List[Optional[Schedule]]
    enrolled: bool


class Output(BaseOutput):
    payload: Optional[Payload]
