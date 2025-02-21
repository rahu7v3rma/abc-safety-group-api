from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Bundle(BaseModel):
    bundlePicture: str  # noqa: N815
    bundleId: str  # noqa: N815
    bundleName: str  # noqa: N815
    active: bool
    complete: bool
    totalClasses: int  # noqa: N815
    courseType: str  # noqa: N815


class Course(BaseModel):
    coursePicture: str  # noqa: N815
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    briefDescription: str  # noqa: N815
    totalClasses: int  # noqa: N815
    courseType: str  # noqa: N815
    active: Optional[bool]
    complete: Optional[bool]


class BundlePayload(BaseModel):
    bundels: List[Optional[Bundle]]
    pagination: Optional[pagination.PaginationOutput]


class BundleOutput(BaseOutput):
    payload: BundlePayload


class CoursesPayload(BaseModel):
    courses: List[Optional[Course]]
    pagination: Optional[pagination.PaginationOutput]


class CourseOutput(BaseOutput):
    payload: CoursesPayload


class Input(BaseModel):
    pass
