from typing import List

from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    pass


class Input(BaseInput):
    certificateNumbers: List[str]  # noqa: N815
