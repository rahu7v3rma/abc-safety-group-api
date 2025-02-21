from typing import List, Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseModel, BaseOutput


class Bundle(BaseModel):
    bundlePicture: str  # noqa: N815
    bundleId: str  # noqa: N815
    bundleName: str  # noqa: N815
    active: bool
    complete: bool
    totalClasses: int  # noqa: N815
    courseType: str  # noqa: N815
    startDate: str  # noqa: N815


class BundlePayload(BaseModel):
    bundles: List[Optional[Bundle]]
    pagination: Optional[pagination.PaginationOutput]


class Output(BaseOutput):
    payload: BundlePayload
