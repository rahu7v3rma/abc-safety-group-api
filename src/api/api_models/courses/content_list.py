from typing import List, Optional

from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.pagination import PaginationOutput


class Content(BaseModel):
    contentId: str  # noqa: N815
    contentName: str  # noqa: N815
    published: Optional[bool]


class ContentPayload(BaseModel):
    content: List[Optional[Content]]
    pagination: Optional[PaginationOutput]


class Output(BaseOutput):
    payload: ContentPayload
