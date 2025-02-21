from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseOutput


class UpdateBundleInput(BaseInput):
    bundleId: str  # noqa: N815
    bundleName: Optional[str] = None  # noqa: N815
    active: Optional[bool] = None
    maxStudents: Optional[int] = None  # noqa: N815
    waitlist: Optional[bool] = None
    price: Optional[float] = None
    allowCash: Optional[bool] = None  # noqa: N815
    courseIds: Optional[List[str]] = None  # noqa: N815
    isFull: Optional[bool] = None  # noqa: N815


class Output(BaseOutput):
    pass
