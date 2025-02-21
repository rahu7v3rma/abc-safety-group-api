from typing import List, Optional, Union

from src.api.api_models.bases import BaseInput, BaseModel


class Payload(BaseModel):
    courseId: str  # noqa: N815


class Output(BaseModel):
    payload: Optional[Payload]


class Address(BaseModel):
    address: str
    city: str
    state: str
    zipcode: int


class Height(BaseModel):
    feet: int
    inches: int


class General(BaseModel):
    courseName: str  # noqa: N815
    briefDescription: Optional[str]  # noqa: N815
    description: Optional[str]
    requirements: Optional[List[str]] = []
    languages: List[str] = ["English"]
    instructors: Optional[List[str]] = []
    price: float
    instructionTypes: List[str] = []  # noqa: N815
    remoteLink: Optional[str] = None  # noqa: N815
    phoneNumber: str  # noqa: N815
    email: str
    address: Optional[str] = None
    duration: int = 60
    maxStudents: Optional[int] = 20  # noqa: N815
    enrollable: Optional[bool] = False
    waitlist: bool = True
    waitlistLimit: Optional[int] = 20  # noqa: N815
    prerequisites: Optional[List[str]] = None
    allowCash: bool = False  # noqa: N815
    courseCode: Optional[str] = None  # noqa: N815


class Frequency(BaseModel):
    frequency: Optional[int] = None
    days: Optional[List[Union[str, int]]] = None
    months: Optional[List[str]] = None
    dates: Optional[List[str]] = None


class ClassFrequency(BaseModel):
    days: Optional[Frequency] = None
    weeks: Optional[Frequency] = None
    months: Optional[Frequency] = None
    years: Optional[Frequency] = None


class Series(BaseModel):
    firstClassDtm: str  # noqa: N815
    classesInSeries: int  # noqa: N815
    classFrequency: ClassFrequency  # noqa: N815


class Content(BaseModel):
    contentName: str  # noqa: N815
    content: str


class Expiration(BaseModel):
    years: Optional[int] = 0
    months: Optional[int] = 0


class Certificate(BaseModel):
    certificateName: Optional[str] = None  # noqa: N815
    expiration: Optional[Expiration] = None
    certificate: Optional[bool] = True


class Input(BaseInput):
    general: General
    series: Series
    quizzes: Optional[List[str]] = None
    surveys: Optional[List[str]] = None
    certification: Certificate
    active: bool = False
