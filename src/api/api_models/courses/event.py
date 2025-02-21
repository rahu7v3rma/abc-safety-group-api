from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class Instructor(BaseModel):
    userId: str  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815


class Details(BaseModel):
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    complete: bool  # noqa: N815
    seriesNumber: int  # noqa: N815
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815
    remoteLink: Optional[str]  # noqa: N815
    address: Optional[str]
    duration: int
    instructors: List[Optional[Instructor]]
    signedIn: Optional[bool] = False  # noqa: N815
    absent: Optional[bool] = False


class Payload(BaseModel):
    details: Details


class Output(BaseOutput):
    payload: Payload
