from typing import Optional, Union

from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src import log
from src.api.api_models import global_models
from src.database.sql.user_functions import check_permissions, get_user
from src.utils.session import get_session


class AuthClient(HTTPBearer):
    """Class to handle authorization functionality"""

    def __init__(
        self,
        auto_error: bool = True,
        use_auth: bool = True,
        permission_nodes: Optional[list] = None,
        auth_required: bool = True,
    ) -> None:
        super(AuthClient, self).__init__(auto_error=auto_error)
        self.use_auth = use_auth
        self.permission_nodes = permission_nodes
        self.auth_required = auth_required

    async def __call__(
        self,
        request: Request,
    ) -> Union[bool, global_models.User, str, None, HTTPException]:
        """Function to route api endpoints through Bearer authentification

        Args:
            request (Request): FastAPI request passed through a function

        Raises:
            HTTPException: If no authorized, raises http exception

        Returns:
            Union[bool, HTTPException]: Bool to depict authorization granted or error for no authorization
        """  # noqa: E501
        if not self.use_auth:
            return True  # returns true if no auth service needed

        credentials: HTTPAuthorizationCredentials = await super(
            AuthClient,
            self,
        ).__call__(request)  # type: ignore
        if self.auth_required:
            if not credentials:
                raise HTTPException(
                    status_code=403,
                    detail="Must provide an authorization token",
                )
            if not credentials.scheme == "Bearer":
                raise HTTPException(
                    status_code=403,
                    detail=f"Invalid authorization scheme {credentials.scheme}",  # noqa: E501
                )

        user = await self.has_access(
            credentials.credentials if credentials else "",
        )

        if isinstance(user, str) and self.auth_required:
            raise HTTPException(status_code=403, detail=user)

        if not self.auth_required and not user:
            return True

        return user

    async def has_access(
        self,
        auth_token: Optional[str] = None,
    ) -> Union[bool, global_models.User, str, None]:
        """Function that is used to validate the token in the case that it requires it

        Args:
            auth_token (str): Bearer token passed through from the api request

        Returns:
            bool: Returns true or false depending on if authorization is granted
        """  # noqa: E501
        if not auth_token and self.auth_required:
            return "Not Authorized"

        if not auth_token and not self.auth_required:
            return True

        user = await self.check_auth(auth_token=auth_token)
        if isinstance(user, str):
            return user
        return user

    async def check_auth(
        self,
        auth_token: Optional[str] = None,
    ) -> Union[bool, global_models.User, str, None]:
        """Function to call auth service if necessary (internal)

        Args:
            auth_token (str): Bearer token passed through from the api request

        Returns:
            bool: Returns true or false depending on if authorization is granted
        """  # noqa: E501
        try:
            user_id = get_session(auth_token)
            if not user_id:
                return "Not Authorized"

            user = await get_user(user_id=user_id)
            if not user:
                return "Not Authorized"

            missing_permissions = None
            if self.permission_nodes and self.auth_required:
                missing_permissions = await check_permissions(
                    user_id=user_id,
                    permission_nodes=self.permission_nodes,
                )

            if not missing_permissions:
                return user

            return f"Missing permission(s) {', '.join(missing_permissions)}"

        except Exception:
            log.exception(f"Failed to check auth for auth token {auth_token}")
