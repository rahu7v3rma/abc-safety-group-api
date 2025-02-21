from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    pass


class Input(BaseInput):
    email: str


class Input2(BaseInput):
    newPassword: str  # noqa: N815
