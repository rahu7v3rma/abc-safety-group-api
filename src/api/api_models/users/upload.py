from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class Payload(BaseModel):
    failed: Optional[bool]
    reason: Optional[str]
    userId: Optional[str]  # noqa: N815
    headShot: Optional[str]  # noqa: N815
    photoIdPhoto: Optional[str]  # noqa: N815
    otherIdPhoto: Optional[str]  # noqa: N815


class BulkPayload(BaseModel):
    headShots: Optional[List[Payload]]  # noqa: N815


class BulkOutput(BaseOutput):
    payload: Optional[List[BulkPayload]]


class Output(BaseOutput):
    payload: Optional[Payload]
