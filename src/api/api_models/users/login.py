from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput
from src.api.api_models.global_models import User


class Role(BaseModel):
    roleId: str  # noqa: N815
    roleName: str  # noqa: N815
    roleDesc: Optional[str]  # noqa: N815


class Permission(BaseModel):
    permissionId: str  # noqa: N815
    permissionNode: str  # noqa: N815
    description: Optional[str]  # noqa: N815


class loginPayload(BaseModel):  # noqa: N801
    user: User
    sessionId: str  # noqa: N815
    permissions: List[Optional[Permission]]
    roles: List[Optional[Role]]


class Output(BaseOutput):
    payload: loginPayload


class Input(BaseInput):
    email: str
    password: str
