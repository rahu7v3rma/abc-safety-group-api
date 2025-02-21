from typing import Optional, Union

from pydantic import BaseModel


class BaseInput(BaseModel):
    pass


class BaseOutput(BaseModel):
    message: Optional[str]
    payload: Optional[Union[dict, list]]
    success: bool
