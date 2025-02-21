from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput


class Event(BaseModel):
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    startTime: str  # noqa: N815
    duration: int
    seriesNumber: int  # noqa: N815
    complete: bool


class SchedulePayload(BaseModel):
    schedule: List[Optional[Event]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: SchedulePayload


class Input(BaseInput):
    courseName: Optional[str] = None  # noqa: N815
    bundleName: Optional[str] = None  # noqa: N815
