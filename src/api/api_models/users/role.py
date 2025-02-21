from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.pagination import PaginationOutput


class User(BaseModel):
    userId: str  # noqa: N815
    headShot: str  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    email: str
    phoneNumber: str  # noqa: N815
    dob: str


class Payload(BaseModel):
    users: Optional[List[User]] = []
    pagination: PaginationOutput


class Output(BaseOutput):
    payload: Payload
