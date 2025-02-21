from src.api.api_models.bases import BaseInput, BaseOutput


class Input(BaseInput):
    courseId: str  # noqa: N815
    bundle: bool = False
    contentType: str  # noqa: N815
    contentId: str  # noqa: N815


class Output(BaseOutput):
    pass
