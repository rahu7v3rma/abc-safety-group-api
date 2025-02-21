import datetime
from typing import List, Optional, Union

from src.api.api_models.bases import BaseModel


class BundleCourse(BaseModel):
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    briefDescription: Optional[str]  # noqa: N815
    startDate: Optional[str]  # noqa: N815


class Bundle(BaseModel):
    bundleId: str  # noqa: N815
    bundlePicture: Optional[str]  # noqa: N815
    bundleName: str  # noqa: N815
    price: Union[int, float]
    active: bool
    maxStudents: int  # noqa: N815
    isFull: bool  # noqa: N815
    waitlist: bool
    waitlistLimit: int  # noqa: N815
    enrollable: bool
    allowCash: bool  # noqa: N815
    complete: bool
    startDate: str  # noqa: N815
    courses: List[Optional[BundleCourse]]
    languages: List[str]
    instructionTypes: List[str]  # noqa: N815
    prerequisites: List[Optional[BundleCourse]]


class Height(BaseModel):
    feet: int
    inches: int


class User(BaseModel):
    userId: str  # noqa: N815
    password: Optional[str] = None
    firstName: str  # noqa: N815
    middleName: Optional[str] = None  # noqa: N815
    lastName: str  # noqa: N815
    suffix: Optional[str] = None
    email: Optional[str] = None
    phoneNumber: Optional[str] = None  # noqa: N815
    dob: str = str(datetime.date.today())
    eyeColor: Optional[str] = None  # noqa: N815
    height: Optional[Height] = None
    gender: Optional[str] = None
    timeZone: Optional[str] = "America/New_York"  # noqa: N815
    headShot: Optional[str] = None  # noqa: N815
    photoId: Optional[str] = None  # noqa: N815
    photoIdPhoto: Optional[str] = None  # noqa: N815
    otherIdPhoto: Optional[str] = None  # noqa: N815
    otherId: Optional[str] = None  # noqa: N815
    active: bool = True
    textNotifications: Optional[bool] = False  # noqa: N815
    emailNotifications: Optional[bool] = True  # noqa: N815
    expirationDate: Union[str, None] = None  # noqa: N815
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[int] = None


class Prerequisite(BaseModel):
    courseId: Optional[str]  # noqa: N815
    courseName: Optional[str]  # noqa: N815


class Course(BaseModel):
    coursePicture: str  # noqa: N815
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    briefDescription: Optional[str]  # noqa: N815
    description: Optional[str]
    price: float
    prerequisites: List[Prerequisite]
    languages: List[str]
    instructionTypes: List[str]  # noqa: N815
    active: bool
    maxStudents: int  # noqa: N815
    isFull: bool  # noqa: N815
    waitlist: bool
    waitlistLimit: int  # noqa: N815
    startDate: str  # noqa: N815
    enrollable: bool
    instructors: List[dict]
    email: str
    phoneNumber: str  # noqa: N815
    allowCash: bool  # noqa: N815
    registrationStatus: Optional[str] = None  # noqa: N815
    # only show if enrolled
    address: Optional[str]
    remoteLink: Optional[str]  # noqa: N815
