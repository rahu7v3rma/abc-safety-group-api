from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput


class Content(BaseModel):
    contentId: str  # noqa: N815
    contentName: str  # noqa: N815
    published: bool


class ContentPayload(BaseModel):
    content: List[Optional[Content]]


class Output(BaseOutput):
    payload: ContentPayload
