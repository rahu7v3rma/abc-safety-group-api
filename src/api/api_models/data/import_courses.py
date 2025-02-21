from typing import List, Optional, Union

from src.api.api_models.bases import BaseModel, BaseOutput


class CourseOutput(BaseModel):
    courseName: Optional[str] = None  # noqa: N815
    reason: Optional[str] = None


class SeriesOutput(BaseModel):
    courseName: Optional[str] = None  # noqa: N815
    reason: Optional[str] = None


class BundleOutput(BaseModel):
    bundleName: str  # noqa: N815
    courseName: Optional[str] = None  # noqa: N815
    reason: Optional[str] = None


class Payload(BaseModel):
    succeeded: int
    bundles: Optional[List[BundleOutput]] = None
    courses: Optional[List[CourseOutput]] = None
    series: Optional[List[SeriesOutput]] = None


class Output(BaseOutput):
    payload: Optional[Payload] = None


class Schedule(BaseModel):
    date: str
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815


class Course(BaseModel):
    courseName: str  # noqa: N815
    description: Optional[str] = None
    language: str
    schedule: List[Schedule]
    onlineClassLink: Optional[str] = None  # noqa: N815
    password: Optional[Union[str, int]] = None
    street: Optional[str] = None
    rmFl: Optional[Union[str, int]] = None  # noqa: N815
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[int] = None
    instructorNames: Optional[List[str]] = None  # noqa: N815
    price: Optional[Union[int, float]] = 0
    code: Optional[Union[str, int]] = None


class BundleContent(BaseModel):
    name: str
    price: Union[int, float]
    description: Optional[str] = None


class Bundle(BaseModel):
    bundle: BundleContent
    courses: List[Course]


class Input(BaseModel):
    courses: Optional[List[Course]] = None
    bundles: Optional[List[Bundle]] = None
    series: Optional[List[Course]] = None
