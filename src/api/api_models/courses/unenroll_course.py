from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    pass


class Input(BaseInput):
    courseId: str  # noqa: N815
    userId: str  # noqa: N815
