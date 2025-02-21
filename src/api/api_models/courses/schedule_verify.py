from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput


class Input(BaseInput):
    courseIds: List[str]  # noqa: N815


class Schedule(BaseModel):
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815
    courseName: str  # noqa: N815
    courseId: str  # noqa: N815


class Payload(BaseModel):
    schedule: List[Optional[Schedule]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: Optional[Payload]
