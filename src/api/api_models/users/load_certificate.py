from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class Certificate(BaseModel):
    userId: str  # noqa: N815
    certificateName: str  # noqa: N815
    certificateNumber: str  # noqa: N815
    completionDate: str  # noqa: N815
    expirationDate: str  # noqa: N815
    student: str
    instructor: str


class Payload(BaseModel):
    certificates: Optional[List[Certificate]] = []


class Output(BaseOutput):
    payload: Payload
