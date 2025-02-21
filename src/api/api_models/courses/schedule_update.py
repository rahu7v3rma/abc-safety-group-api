from src.api.api_models.bases import BaseInput, BaseOutput


class Input(BaseInput):
    startTime: str  # noqa: N815
    endTime: str  # noqa: N815


class Output(BaseOutput):
    pass
