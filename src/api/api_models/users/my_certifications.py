from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Certification(BaseModel):
    userId: str  # noqa: N815
    certificateName: str  # noqa: N815
    certificateNumber: str  # noqa: N815
    student: str
    instructor: str
    completionDate: str  # noqa: N815
    expirationDate: Optional[str] = None  # noqa: N815


class CertificationsPayload(BaseModel):
    certifications: List[Optional[Certification]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: CertificationsPayload
