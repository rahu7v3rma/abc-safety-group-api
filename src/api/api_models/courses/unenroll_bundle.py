from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    pass


class Input(BaseInput):
    bundleId: str  # noqa: N815
    userId: str  # noqa: N815
