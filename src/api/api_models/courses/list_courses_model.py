from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Course(BaseModel):
    coursePicture: str  # noqa: N815
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    startDate: str  # noqa: N815
    briefDescription: Optional[str] = None  # noqa: N815
    totalClasses: int  # noqa: N815
    courseType: str  # noqa: N815
    active: Optional[bool]
    complete: Optional[bool]


class CoursesPayload(BaseModel):
    courses: List[Optional[Course]]
    pagination: Optional[pagination.PaginationOutput]


class CoursesOutput(BaseOutput):
    payload: CoursesPayload
