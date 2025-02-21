from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Role(BaseModel):
    roleName: str  # noqa: N815
    roleId: str  # noqa: N815
    description: str  # noqa: N815


class ListPayload(BaseModel):
    roles: List[Optional[Role]]
    pagination: Optional[pagination.PaginationOutput]


class ListOutput(BaseOutput):
    payload: ListPayload
