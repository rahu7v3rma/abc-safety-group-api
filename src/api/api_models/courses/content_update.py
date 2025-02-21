from typing import List

from src.api.api_models.bases import BaseInput, BaseOutput


class UpdateInput(BaseInput):
    fileIds: List[str]  # noqa: N815
    publish: bool


class DeleteInput(BaseInput):
    fileIds: List[str]  # noqa: N815


class Output(BaseOutput):
    pass
