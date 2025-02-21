from typing import Optional

from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    success: bool


class Input(BaseInput):
    userId: str  # noqa: N815
    registrationStatus: Optional[str] = None  # noqa: N815
    paid: Optional[bool] = None
    notes: Optional[str] = None
    usingCash: Optional[bool] = None  # noqa: N815
