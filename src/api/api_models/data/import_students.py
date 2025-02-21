from typing import List, Optional, Union

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput


class Student(BaseModel):
    reason: Optional[str] = None
    failed: Optional[bool] = None
    userId: str  # noqa: N815
    headShot: Optional[str] = None  # noqa: N815
    firstName: Optional[str] = None  # noqa: N815
    middleName: Optional[str] = None  # noqa: N815
    lastName: Optional[str] = None  # noqa: N815
    suffix: Optional[str] = None
    email: Optional[str] = None
    phoneNumber: Optional[str] = None  # noqa: N815
    dob: Optional[str] = None
    eyeColor: Optional[str] = None  # noqa: N815
    houseNumber: Optional[str] = None  # noqa: N815
    streetName: Optional[str] = None  # noqa: N815
    aptSuite: Optional[Union[int, str]] = None  # noqa: N815
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[Union[int, str]] = None
    gender: Optional[str] = None
    height: Optional[str] = None


class Payload(BaseModel):
    fileName: Optional[str] = None  # noqa: N815
    students: Optional[List[Student]]


class Output(BaseOutput):
    payload: Optional[Payload]


class Input(BaseInput):
    fileName: Optional[str] = None  # noqa: N815
    students: List[Student]
    uploadType: Optional[str] = "student"  # noqa: N815
