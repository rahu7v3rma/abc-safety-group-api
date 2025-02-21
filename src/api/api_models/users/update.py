from typing import Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput
from src.api.api_models.global_models import User


class Height(BaseModel):
    feet: int = 0
    inches: int = 0


class Input(BaseInput):
    firstName: Optional[str] = None  # noqa: N815
    middleName: Optional[str] = None  # noqa: N815
    lastName: Optional[str] = None  # noqa: N815
    suffix: Optional[str] = None
    email: Optional[str] = None
    phoneNumber: Optional[str] = None  # noqa: N815
    dob: Optional[str] = None
    password: Optional[str] = None
    timeZone: Optional[str] = "America/New_York"  # noqa: N815
    photoId: Optional[str] = None  # noqa: N815
    otherId: Optional[str] = None  # noqa: N815
    textNotifications: Optional[bool] = False  # noqa: N815
    emailNotifications: Optional[bool] = True  # noqa: N815
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[int] = None
    height: Optional[Height] = None
    gender: Optional[str] = None
    eyeColor: Optional[str] = None  # noqa: N815
    headShot: Optional[str] = None  # noqa: N815
    otherIdPhoto: Optional[str] = None  # noqa: N815
    photoIdPhoto: Optional[str] = None  # noqa: N815
    expirationDate: Optional[str] = None  # noqa: N815


class Payload(BaseModel):
    user: User


class Output(BaseOutput):
    payload: Payload
