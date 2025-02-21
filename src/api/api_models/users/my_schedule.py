from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Schedule(BaseModel):
    courseId: str  # noqa: N815
    seriesNumber: int  # noqa: N815
    courseName: str  # noqa: N815
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815
    duration: float
    complete: bool
    address: Optional[str] = None
    remoteLink: Optional[str] = None  # noqa: N815


class SchedulePayload(BaseModel):
    schedule: List[Optional[Schedule]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: SchedulePayload
