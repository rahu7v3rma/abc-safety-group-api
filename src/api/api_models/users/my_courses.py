from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Course(BaseModel):
    coursePicture: str  # noqa: N815
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    briefDescription: str  # noqa: N815
    totalClasses: int  # noqa: N815
    courseType: str  # noqa: N815
    complete: Optional[bool]


class CoursePayload(BaseModel):
    courses: List[Optional[Course]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: CoursePayload
