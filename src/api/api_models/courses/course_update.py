from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class UpdateCourseInput(BaseModel):
    courseId: str  # noqa: N815
    courseName: Optional[str] = None  # noqa: N815
    briefDescription: Optional[str] = None  # noqa: N815
    description: Optional[str] = None
    languages: Optional[List[str]] = None
    instructors: Optional[List[str]] = None
    price: Optional[float] = None
    instructionTypes: Optional[List[str]] = None  # noqa: N815
    remoteLink: Optional[str] = None  # noqa: N815
    phoneNumber: Optional[str] = None  # noqa: N815
    email: Optional[str] = None
    address: Optional[str] = None
    maxStudents: Optional[int] = None  # noqa: N815
    isFull: Optional[bool] = None  # noqa: N815
    enrollable: Optional[bool] = None
    waitlist: Optional[bool] = None
    waitlistLimit: Optional[int] = None  # noqa: N815
    prerequisites: Optional[List[str]] = None
    allowCash: Optional[bool] = None  # noqa: N815
    active: Optional[bool] = None
    courseCode: Optional[str] = None  # noqa: N815


class Output(BaseOutput):
    pass
