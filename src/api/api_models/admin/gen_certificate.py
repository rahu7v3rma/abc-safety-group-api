from typing import List, Optional

from pydantic import BaseModel

from src.api.api_models.bases import BaseInput


class Payload(BaseModel):
    students: Optional[List[str]]


class Output(BaseModel):
    payload: Optional[Payload]


class Input(BaseInput):
    courseId: str  # noqa: N815
    userIds: List[str]  # noqa: N815
    uploadCertificates: Optional[bool] = False  # noqa: N815
    notifyUsers: Optional[bool] = True  # noqa: N815
