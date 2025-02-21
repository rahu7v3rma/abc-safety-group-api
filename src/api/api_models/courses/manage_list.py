from typing import Optional

from src.api.api_models import pagination
from src.api.api_models.bases import BaseOutput
from src.api.api_models.courses import bundle, create


class Output(BaseOutput):
    courses: create.General
    bundles: bundle.Input
    pagination: Optional[pagination.PaginationOutput]
