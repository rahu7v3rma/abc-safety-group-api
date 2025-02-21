from typing import List

from src.api.api_models.bases import BaseInput, BaseOutput


class Input(BaseInput):
    userIds: List[str]  # noqa: N815


class Output(BaseOutput):
    pass
