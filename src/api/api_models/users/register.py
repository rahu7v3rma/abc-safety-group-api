from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class Role(BaseModel):
    roleId: str  # noqa: N815
    roleName: str  # noqa: N815
    roleDesc: Optional[str]  # noqa: N815


class Permission(BaseModel):
    permissionId: str  # noqa: N815
    permissionNode: str  # noqa: N815
    description: Optional[str]


class Height(BaseModel):
    feet: int = 0
    inches: int = 0


class User(BaseModel):
    firstName: str  # noqa: N815
    middleName: Optional[str] = None  # noqa: N815
    lastName: str  # noqa: N815
    suffix: Optional[str] = None
    email: str
    phoneNumber: str  # noqa: N815
    dob: str
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
    expirationDate: Optional[str] = None  # noqa: N815


class Input(User):
    pass


class Payload(BaseModel):
    user: Optional[User]
    sessionId: Optional[str]  # noqa: N815
    userId: Optional[str]  # noqa: N815
    permissions: List[Optional[Permission]]
    roles: List[Optional[Role]]


class Output(BaseOutput):
    payload: Payload
