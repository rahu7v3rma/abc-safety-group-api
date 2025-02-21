from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput
from src.api.api_models.pagination import PaginationOutput


class Certificate(BaseModel):
    userId: str  # noqa: N815
    headShot: str  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    certificateNumber: str  # noqa: N815
    certificateName: str  # noqa: N815
    completionDate: Optional[str]  # noqa: N815
    expirationDate: Optional[str]  # noqa: N815
    instructor: str


class Payload(BaseModel):
    certificates: Optional[List[Certificate]] = []
    pagination: PaginationOutput


class Output(BaseOutput):
    payload: Payload


class Search(BaseInput):
    firstName: Optional[str] = None  # noqa: N815
    lastName: Optional[str] = None  # noqa: N815
    email: Optional[str] = None
    phoneNumber: Optional[str] = None  # noqa: N815
    certificateNumber: Optional[str] = None  # noqa: N815
