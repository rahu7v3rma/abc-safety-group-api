from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput
from src.api.api_models.pagination import PaginationOutput


class Course(BaseModel):
    courseId: str  # noqa: N815
    coursePicture: Optional[str]  # noqa: N815
    courseName: str  # noqa: N815
    startDate: Optional[str]  # noqa: N815
    briefDescription: Optional[str]  # noqa: N815
    totalClasses: Optional[int]  # noqa: N815
    courseType: str  # noqa: N815
    active: bool
    complete: bool


class Bundle(BaseModel):
    bundleId: str  # noqa: N815
    bundlePicture: Optional[str]  # noqa: N815
    bundleName: str  # noqa: N815
    startDate: Optional[str]  # noqa: N815
    totalClasses: Optional[int]  # noqa: N815
    courseType: str  # noqa: N815
    active: bool
    complete: bool


class Found(BaseModel):
    id: str
    picture: Optional[str]
    name: str
    type: str
    startDate: Optional[str]  # noqa: N815
    totalClasses: Optional[int]  # noqa: N815
    active: bool
    complete: bool
    briefDescription: Optional[str]  # noqa: N815


class Payload(BaseModel):
    pagination: PaginationOutput
    bundles: Optional[List[Bundle]]
    courses: Optional[List[Course]]
    found: Optional[List[Found]]


class Output(BaseOutput):
    payload: Optional[Payload]


class Input(BaseInput):
    courseName: Optional[str] = None  # noqa: N815
    courseBundle: Optional[str] = None  # noqa: N815
    name: Optional[str] = None
