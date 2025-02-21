from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.global_models import User


class Role(BaseModel):
    roleId: str  # noqa: N815
    roleName: str  # noqa: N815
    roleDesc: Optional[str]  # noqa: N815


class Permission(BaseModel):
    permissionId: str  # noqa: N815
    permissionNode: str  # noqa: N815
    description: Optional[str]


class MePayload(BaseModel):
    user: User
    roles: List[Role]
    permissions: List[Optional[Permission]]


class Output(BaseOutput):
    payload: MePayload
