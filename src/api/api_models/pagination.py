from typing import Optional

from pydantic import BaseModel


class PaginationOutput(BaseModel):
    curPage: Optional[int]  # noqa: N815
    totalPages: Optional[int]  # noqa: N815
    pageSize: Optional[int]  # noqa: N815
    totalCount: Optional[int]  # noqa: N815
