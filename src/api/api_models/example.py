from src.api.api_models.bases import BaseInput, BaseModel, BaseOutput


class Input(BaseInput):
    name: str


class PayloadContent(BaseModel):
    name: str


class Output(BaseOutput):
    payload: PayloadContent
