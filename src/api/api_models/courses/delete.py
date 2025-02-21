from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseOutput


class Output(BaseOutput):
    pass


class Input(BaseInput):
    courseIds: Optional[List[str]] = None  # noqa: N815
    bundleIds: Optional[List[str]] = None  # noqa: N815
