from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Input(BaseModel):
    firstName: Optional[str] = None  # noqa: N815
    lastName: Optional[str] = None  # noqa: N815
    phoneNumber: Optional[str] = None  # noqa: N815
    email: Optional[str] = None
    _id: Optional[str] = None
    # instructorFirstName: Optional[str] = None
    # instructorLastName: Optional[str] = None
    # startTime: Optional[str] = None
    # courseName: Optional[str] = None


class User(BaseModel):
    userId: str  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    dob: str
    email: str
    phoneNumber: str  # noqa: N815
    headShot: str  # noqa: N815


class StudentsPayload(BaseModel):
    students: List[Optional[User]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: StudentsPayload
