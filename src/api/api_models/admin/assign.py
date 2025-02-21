from typing import List, Optional

from src.api.api_models.bases import BaseInput, BaseOutput


class Input(BaseInput):
    add: Optional[List[str]] = None
    remove: Optional[List[str]] = None


class Output(BaseOutput):
    pass
