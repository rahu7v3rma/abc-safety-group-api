from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput


class Output(BaseOutput):
    pass


class InstructorInput(BaseInput):
    instructors: List[str]


class StudentPayload(BaseModel):
    userId: str  # noqa: N815
    registrationStatus: str  # noqa: N815
    denialReason: Optional[str] = None  # noqa: N815
    userPaid: Optional[bool] = False  # noqa: N815
    usingCash: Optional[bool] = False  # noqa: N815
    notes: Optional[str] = None


class SelfRegistration(BaseModel):
    transactionId: Optional[str] = None  # noqa: N815
    userPaid: bool = False  # noqa: N815
    usingCash: bool = False  # noqa: N815


class StudentCourseInput(BaseInput):
    students: List[StudentPayload]


class StudentBundleInput(BaseInput):
    students: List[StudentPayload]
