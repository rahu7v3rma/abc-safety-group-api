from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.global_models import Bundle


class Payload(BaseModel):
    bundle: Bundle


class Output(BaseOutput):
    payload: Payload
