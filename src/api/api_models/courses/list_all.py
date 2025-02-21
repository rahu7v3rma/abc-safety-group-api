from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.pagination import PaginationOutput


class Model(BaseModel):
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
    found: List[Optional[Model]]
    pagination: PaginationOutput


class Output(BaseOutput):
    payload: Payload
