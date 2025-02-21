from typing import Optional

from src.api.api_models.bases import BaseInput, BaseOutput


class Input(BaseInput):
    id: Optional[str]
    contentType: str = "headShot" or "sstId"  # noqa: N815


class Output(BaseOutput):
    pass
