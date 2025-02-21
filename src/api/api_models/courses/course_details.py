from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.global_models import Course


class Payload(BaseModel):
    course: Course


class Output(BaseOutput):
    payload: Payload
