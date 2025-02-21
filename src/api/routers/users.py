import datetime
import uuid
from io import BytesIO
from typing import List, Union

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse, JSONResponse
from passlib.hash import pbkdf2_sha256

from src import img_handler, log
from src.api.api_models import global_models, pagination
from src.api.api_models.users import (
    forgot,
    list_certificates,
    load_certificate,
    login,
    logout,
    lookup,
    me,
    my_certifications,
    register,
    role,
    update,
    upload,
)
from src.api.lib.auth.auth import AuthClient
from src.api.lib.base_responses import (
    server_error,
    successful_response,
    user_error,
)
from src.database.sql.audit_log_functions import submit_audit_record
from src.database.sql.user_functions import (
    create_user,
    get_certificates,
    get_user,
    get_user_certifications,
    get_user_class,
    get_user_roles,
    get_user_roles_and_permissions,
    get_user_type,
    manage_user_roles,
    search_certificates,
    update_user,
    upload_user_pictures,
)
from src.modules.forgot_password import (
    create_reset,
    get_reset,
    read_jwt,
    remove_reset,
)
from src.modules.notifications import (
    password_reset_notification,
)
from src.modules.save_content import save_content
from src.utils.camel_case import camel_case
from src.utils.image import is_valid_image, resize_image
from src.utils.session import create_session, delete_session, get_session
from src.utils.validate import validate_email, validate_phone_number

router = APIRouter(
    prefix="/users",
    tags=["Users"],
    responses={404: {"description": "Details not found"}},
)


@router.post(
    "/login",
    description="Route to login",
    response_model=login.Output,
)
async def login_route(content: login.Input) -> JSONResponse:
    try:
        if not content.email:
            return user_error(
                message="Email must be provided",
            )

        if not content.password:
            return user_error(
                message="Password must be provided",
            )

        user = await get_user(email=content.email)
        if not user:
            return user_error(
                message="User does not exist with this email",
            )

        if not user.active:
            return user_error(
                message=(
                    "Account no longer active, please contact administrator."
                ),
            )

        if user.expirationDate:
            expiration_date = datetime.datetime.strptime(
                user.expirationDate,
                "%m/%d/%Y",
            )
            if datetime.datetime.utcnow() >= expiration_date:
                await update_user(
                    user_id=user.userId,
                    active=False,
                )
                return user_error(
                    message="User account deactivated, please contact admin.",
                )

        if not pbkdf2_sha256.verify(content.password, user.password):  # type: ignore
            return user_error(
                message="Password does not match",
            )

        session_id = create_session(user.userId)

        user.password = None
        # set image handler for allowing image viewing
        img_handler.set_key(key=user.userId, token=session_id, ex=259200)
        roles, permissions = await get_user_roles_and_permissions(
            user_id=user.userId,
        )
        return successful_response(
            payload={
                "user": user.dict(),
                "roles": roles,
                "permissions": permissions,
                "sessionId": session_id,
            },
        )
    except Exception:
        log.exception(
            f"An error occured while logging in user {content.email}",
        )
        return server_error(
            message="Failed to login user",
        )


@router.post(
    "/logout",
    description="Route to logout",
    response_model=logout.Output,
)
async def logout_route(
    request: Request,
    user: global_models.User = Depends(AuthClient(use_auth=True)),
) -> JSONResponse:
    try:
        session_id = request.headers.get("authorization")
        if not session_id:
            return user_error(
                message="No Authorization header present",
            )

        session = get_session(session_id.replace("Bearer ", ""))

        if not session:
            return user_error(
                message="No session found",
            )

        delete_session(session)
        # delete image handler for allowing image viewing
        img_handler.delete_key(redis_key=user.userId)
        return successful_response()
    except Exception:
        log.exception(
            f"An error occured while logging out session {session_id}",
        )
        return server_error(
            message="Failed to log out user",
        )


@router.get(
    "/me",
    description="Route to get logged in user info",
    response_model=me.Output,
)
async def me_route(
    request: Request,
    user: global_models.User = Depends(AuthClient(use_auth=True)),
) -> JSONResponse:
    try:
        if not user.userId:
            return server_error(
                message="No session found",
            )

        session_id = request.headers.get("authorization")
        session_id = get_session(session_id.replace("Bearer ", ""))  # type: ignore

        user = await get_user(user_id=user.userId)  # type: ignore
        if not user:
            return user_error(
                message="No user found for that session",
            )

        if user.expirationDate and user.active:
            expiration_date = datetime.datetime.strptime(
                user.expirationDate,
                "%m/%d/%Y",
            )
            if datetime.datetime.utcnow() >= expiration_date:
                await update_user(
                    user_id=user.userId,
                    active=False,
                )

                if not session_id:
                    return user_error(
                        message="No Authorization header present",
                    )

                if not session_id:
                    return user_error(
                        message="No session found",
                    )

                delete_session(session_id)
                # delete image handler for allowing image viewing
                img_handler.delete_key(redis_key=user.userId)

                return user_error(
                    message="User account deactivated, please contact admin.",
                )
        roles, permissions = await get_user_roles_and_permissions(
            user_id=user.userId,
        )
        user.password = None

        if session_id:
            try:
                img_handler.set_key(
                    key=user.userId,
                    token=session_id,
                    ex=259200,
                )
            except Exception:
                log.exception("Failed to set new image handler key")

        return successful_response(
            payload={
                "user": user.dict(),
                "roles": roles,
                "permissions": permissions,
            },
        )
    except Exception:
        log.exception(
            f"An error occured while getting user data for {user.userId}",
        )
        return server_error(
            message="Failed to get user data",
        )


@router.get(
    "/profile/{userId}",
    description="Route to get a users profile",
    response_model=me.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.profile",
                ],
            ),
        ),
    ],
)
async def users_profile(userId: str) -> JSONResponse:  # noqa: N803
    try:
        user = await get_user(user_id=userId)
        if not user:
            return server_error(
                message="No user found for that session",
            )

        user_roles = await get_user_roles(user_id=user.userId)
        user.password = None

        return successful_response(
            payload={
                "user": user.dict(),
                "roles": user_roles,
            },
        )
    except Exception:
        log.exception(
            f"An error occured while getting user profile for {userId}",
        )
        return server_error(
            message="Failed to get user data",
        )


@router.post(
    "/search/student",
    description="Route look up users based off of student role",
    response_model=lookup.Output,
)
async def user_students_lookup(
    user: lookup.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    request_user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.search_students",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_type(
            user=user,
            roleName="student",
            page=page,
            pageSize=pageSize,
        )  # type: ignore

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to search all student")
        return server_error(
            message="Failed to search all student",
        )


@router.post(
    "/search/instructor",
    description="Route look up users based off of instructor role",
    response_model=lookup.Output,
)
async def user_instructor_lookup(
    user: lookup.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    request_user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.search_instructors",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_type(
            user=user,
            roleName="instructor",
            page=page,
            pageSize=pageSize,
        )  # type: ignore

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to search all instructors")
        return server_error(
            message="Failed to search all instructors",
        )


@router.post(
    "/search/admin",
    description="Route look up users based off of admin role",
    response_model=lookup.Output,
)
async def user_admin_lookup(
    user: lookup.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    request_user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.search_admin",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_type(
            user=user,
            roleName="admin",
            page=page,
            pageSize=pageSize,
        )  # type: ignore

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to search all admins")
        return server_error(
            message="Failed to search all admins",
        )


@router.post(
    "/search/all",
    description="Route look up users based off all roles",
    response_model=lookup.Output,
)
async def user_all_lookup(
    user: lookup.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    request_user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.search_all",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_type(
            user=user,
            roleName="all",
            page=page,
            pageSize=pageSize,
        )  # type: ignore

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to search all users")
        return server_error(
            message="Failed to search all users",
        )


@router.post(
    "/forgot-password",
    description="Route to generate token for password reset",
    response_model=forgot.Output,
)
async def forgot_password(content: forgot.Input) -> JSONResponse:
    try:
        user = await get_user(email=content.email)
        if not user:
            return user_error(
                message="User does not exist with this email",
            )

        try:
            create_reset(content.email, user.userId, 600)
            code = get_reset(content.email)

            if not code:
                return user_error(
                    message=(
                        "Something went wrong when trying to get a reset code"
                    ),
                )

            password_reset_notification(user, code)
        except Exception:
            log.exception(
                f"An error occured while sending an email to {content.email}",
            )
            return server_error(
                message="Failed to send email to user",
            )

        return successful_response()
    except Exception:
        log.exception(
            f"An error occured while sending a forgot password for user {user.userId}",  # noqa: E501 # type: ignore
        )
        return server_error(
            message="Failed to send password reset",
        )


@router.post(
    "/forgot-password/{token}",
    description="Route to submit password reset",
    response_model=forgot.Output,
)
async def forgot_password_jwt(
    token: str,
    content: forgot.Input2,
) -> JSONResponse:
    email = read_jwt(token)
    if not email or not email["email"]:
        log.exception("JWT is not set or has nothing inside of it", email)
        return server_error(message="Something went wrong")

    if not content.newPassword:
        return user_error(message="Must be given a new password")

    new_pass = pbkdf2_sha256.hash(content.newPassword)

    if not new_pass:
        log.exception("Something went wrong when trying to hash the password")
        return server_error(message="Something went wrong")

    if not get_reset(email["email"]):
        return user_error(message="No reset code found")

    try:
        user = await get_user(email=email["email"])
        await update_user(user_id=user.userId, password=new_pass)  # type: ignore
        remove_reset(email["email"])
        return successful_response()
    except Exception:
        log.exception(
            "Something went wrong when trying to update the users password",
        )
        return server_error(message="Failed to update user")


@router.get(
    "/certificates/list",
    description="Route to get list certificates",
    response_model=list_certificates.Output,
)
async def certificate_list_route(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    newest: bool = False,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.list_certificates",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        certifications, total_pages, total_count = await get_certificates(
            user=user,
            page=page,
            pageSize=pageSize,
            newest=newest,
        )

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(certifications),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "certificates": certifications,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception("Failed to get user certificates")
        return server_error(message="Failed to get user certificates")


@router.post(
    "/certificates/search",
    description="Route to search certificates by user",
    response_model=list_certificates.Output,
)
async def certificate_search_route(
    content: list_certificates.Search,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.search_certificates",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        certifications, total_pages, total_count = await search_certificates(
            first_name=content.firstName,  # type: ignore
            last_name=content.lastName,  # type: ignore
            email=content.email,  # type: ignore
            phone_number=content.phoneNumber,  # type: ignore
            certificate_number=content.certificateNumber,  # type: ignore
            page=page,
            pageSize=pageSize,
            user=user,
        )

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(certifications),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "certificates": certifications,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception("Failed to get user certificates")
        return server_error(message="Failed to get user certificates")


@router.get(
    "/certificates/load/{userId}/{certificateNumber}",
    description="Route to load a specific users specific certificate",
    response_model=load_certificate.Output,
    response_model_exclude_unset=True,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.load_certificates",
                ],
            ),
        ),
    ],
)
async def load_user_certificate_route(
    userId: str,  # noqa: N803
    certificateNumber: str,  # noqa: N803
) -> JSONResponse:
    try:
        user = await get_user(user_id=userId)
        if not user:
            return user_error(message="User not found")
        certifications, _, _ = await get_user_certifications(
            user=user,
            certificate_number=certificateNumber,
        )
        if not certifications:
            return server_error(message="Failed to get certificates")

        return successful_response(
            payload={
                "certificate": certifications[0],
            },
        )

    except Exception:
        log.exception("Failed to get certifications")
        return server_error(
            message="Failed to get certificates",
        )


@router.get(
    "/certificates/{userId}",
    description="Route to get another users certificates",
    response_model=my_certifications.Output,
)
async def get_certificates_by_userid(
    userId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.profile",
            ],
        ),
    ),
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        user = await get_user(user_id=userId)  # type: ignore
        if not user:
            return user_error(message="User not found")
        (
            certifications,
            total_pages,
            total_count,
        ) = await get_user_certifications(
            user=user,
            page=page,
            pageSize=pageSize,
        )

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(certifications),
            totalCount=total_count,
        )

        return successful_response(
            payload={
                "certificates": certifications,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception(
            f"Failed to get list of certifications for userId {user.userId}",
        )
        return server_error(
            message="Failed to get certifications for user",
        )


@router.post(
    "/update/me",
    description="Route to update self account",
    response_model=update.Output,
)
async def update_me_route(
    content: update.Input,
    user: global_models.User = Depends(AuthClient(use_auth=True)),
) -> JSONResponse:
    try:
        email = None
        if content.email:
            email = validate_email(content.email)
            if not email:
                return user_error(message="Must supply a valid email")

        phone_number = None
        if content.phoneNumber:
            phone_number = validate_phone_number(content.phoneNumber)
            if not phone_number:
                return user_error(message="Must supply a valid phone number")

        updated_user = {
            "first_name": content.firstName,
            "middle_name": content.middleName,
            "last_name": content.lastName,
            "suffix": content.suffix,
            "email": email,
            "phone_number": phone_number,
            "dob": datetime.datetime.strptime(content.dob, "%m/%d/%Y"),  # type: ignore
            "eye_color": content.eyeColor,
            "height": (content.height.feet * 12 + content.height.inches)
            if content.height
            else None,
            "gender": content.gender,
            "photo_id": content.photoId,
            "other_id": content.photoId,
            "time_zone": content.timeZone,
            "create_dtm": datetime.datetime.utcnow(),
            "modify_dtm": datetime.datetime.utcnow(),
            "text_notif": content.textNotifications,
            "email_notif": content.emailNotifications,
            "address": content.address,
            "city": content.city,
            "state": content.state,
            "zipcode": content.zipcode,
            "head_shot": content.headShot,
            "photo_id_photo": content.photoIdPhoto,
            "other_id_photo": content.otherIdPhoto,
        }
        if content.password:
            updated_user.update(
                {"password": pbkdf2_sha256.hash(content.password)},
            )

        updating = await update_user(user_id=user.userId, **updated_user)
        if not updating:
            return server_error(
                message="Something went wrong when updating the user",
            )

        updated = await get_user(user_id=user.userId)
        updated = updated.dict()  # type: ignore

        try:
            del updated["password"]
        except KeyError:
            pass
        # As of right now this is just returning True or false, will likely
        # need to change to
        # return the actual user object after being updated
        return successful_response(
            payload={
                "user": updated,
            },
        )
    except Exception:
        log.exception("Failed to update user")
        return server_error(
            message="Failed to update user",
        )


@router.get(
    "/student",
    description="Route to get all students",
    response_model=role.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.list_students",
                ],
            ),
        ),
    ],
)
async def get_students_route(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_class(
            role="student",
            page=page,
            pageSize=pageSize,
        )  # type: ignore
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get students")
        return server_error(
            message="Failed to get students",
        )


@router.get(
    "/instructor",
    description="Route to get all instructors",
    response_model=role.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.list_instructors",
                ],
            ),
        ),
    ],
)
async def get_instructors_route(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_class(
            role="instructor",
            page=page,
            pageSize=pageSize,
        )  # type: ignore
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get instructors")
        return server_error(
            message="Failed to get instructors",
        )


@router.get(
    "/admin",
    description="Route to get all admins",
    response_model=role.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.list_admins",
                ],
            ),
        ),
    ],
)
async def get_admins_route(page: int = 1, pageSize: int = 20) -> JSONResponse:  # noqa: N803
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_class(
            role="admin",
            page=page,
            pageSize=pageSize,
        )  # type: ignore
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get admins")
        return server_error(
            message="Failed to get admins",
        )


@router.get(
    "/all",
    description="Route to get all users",
    response_model=role.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "users.*",
                    "users.list_all",
                ],
            ),
        ),
    ],
)
async def get_all_users_route(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        users, total_pages, total_count = await get_user_class(
            role="all",
            page=page,
            pageSize=pageSize,
        )  # type: ignore
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(users),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "users": users,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get all")
        return server_error(
            message="Failed to get all",
        )


@router.get(
    "/content/load/{fileId}",
    description="Route to load content",
    response_model=None,
)
async def load_content(
    fileId: str,  # noqa: N803
    uid: str,
    size: int = 1024,
) -> Union[JSONResponse, FileResponse, Response]:
    try:
        if not img_handler.get_key(redis_key=uid):
            return user_error(
                status_code=403,
                message="Unauthorized",
            )
        file_location = rf"/source/src/content/users/{fileId}"

        if size and is_valid_image(file_location):
            image = resize_image(file_location, size)
            if not image:
                return server_error(
                    message="Something went wrong resizing the image",
                )

            if isinstance(image, str):
                return user_error(
                    message=image,
                )
            output_buffer = BytesIO()
            if image.mode in ["RGBA", "P"]:
                image = image.convert("RGB")
            image.save(output_buffer, format="JPEG", quality=95)
            output_buffer.seek(0)

            return Response(
                content=output_buffer.getvalue(),
                media_type="image/jpeg",
            )
        else:
            return FileResponse(file_location)
    except FileNotFoundError:
        return server_error(
            message="File not found",
        )

    except Exception:
        log.exception(
            "Something went wrong when trying to "
            "retrive the image for a course",
        )
        return server_error(
            message="Something went wrong when retrieving the image.",
        )


@router.post(
    "/register/{role}",
    description="Route to register a role type",
    response_model=register.Output,
    response_model_exclude_unset=True,
)
async def register_role_route(
    role: str,
    content: register.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "users.register_users",
            ],
        ),
    ),
) -> JSONResponse:
    if not role:
        return user_error(message="Must supply a role")

    user_id = str(uuid.uuid4())
    try:
        user_roles = await get_user_roles(user.userId)
        if not user_roles:
            return user_error(message="User requesting doesnt have any roles")

        roles = []
        for name in user_roles:
            roles.append(name["roleName"])

        if "superuser" not in roles and role in ["admin", "superuser"]:
            return user_error(
                message=(
                    f"Cannot make an account for {role} with "
                    f"these roles {roles}"
                ),
            )

        email = None
        if content.email:
            email = validate_email(content.email)
            if not email:
                return user_error(message="Must supply a valid email")

        phone_number = None
        if content.phoneNumber:
            phone_number = validate_phone_number(content.phoneNumber)
            if not phone_number:
                return user_error(message="Must supply a valid phone number")

        # Check if user exists
        if await get_user(email=content.email):
            return user_error(
                message="Email address already exists",
            )

        if not content.emailNotifications:
            content.emailNotifications = True

        if not content.textNotifications:
            content.textNotifications = False

        new_user = {
            "user_id": user_id,
            "first_name": content.firstName,
            "middle_name": content.middleName,
            "last_name": content.lastName,
            "suffix": content.suffix,
            "email": email,
            "phone_number": phone_number,
            "dob": datetime.datetime.strptime(content.dob, "%m/%d/%Y"),
            "eye_color": content.eyeColor,
            "height": (content.height.feet * 12 + content.height.inches)
            if content.height
            else None,
            "gender": content.gender,
            "head_shot": None,
            "photo_id": None,
            "other_id": None,
            "photo_id_photo": None,
            "other_id_photo": None,
            "password": pbkdf2_sha256.hash(content.password),  # type: ignore
            "time_zone": content.timeZone,
            "create_dtm": datetime.datetime.utcnow(),
            "modify_dtm": datetime.datetime.utcnow(),
            "active": True,
            "text_notif": content.textNotifications,
            "email_notif": content.emailNotifications,
            "expiration_date": datetime.datetime.strptime(
                content.expirationDate,
                "%m/%d/%Y",
            )
            if content.expirationDate
            else None,
            "address": content.address,
            "city": content.city,
            "state": content.state,
            "zipcode": content.zipcode,
        }

        created_user = await create_user(newUser=new_user)
        if isinstance(created_user, str):
            return user_error(
                message=f"{created_user} is already taken",
            )

        if not created_user:
            raise SystemError("Failed to create user")

        if not await manage_user_roles(
            roles=[role],
            user_id=user_id,
            action="add",
        ):
            return server_error(
                message="Failed to assign roles to user",
            )

        if new_user.get("height"):
            new_user["height"] = content.height.dict()  # type: ignore
        if new_user.get("dob"):
            new_user["dob"] = str(new_user["dob"])
        new_user["create_dtm"] = str(new_user["create_dtm"])
        new_user["modify_dtm"] = str(new_user["modify_dtm"])
        if new_user.get("expiration_date"):
            new_user["expiration_date"] = content.expirationDate
        user = global_models.User(**camel_case(new_user))
        user.password = content.password
        # user_register_notification(user)

        _ = await submit_audit_record(
            route=f"users/register/{role}",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"registered email {content.email} to LMS"
            ),
            user_id=user.userId,
        )
        return successful_response(
            payload={
                "userId": user_id,
            },
        )

    except Exception:
        log.exception(
            f"An error occured while creating user account for {role}",
        )
        return server_error(
            message=f"An error occured while creating user account for {role}",
        )


# TODO: refactor this function to make it less messy
@router.post(
    "/upload/content/{userId}",
    description="Route to upload a user pictures",
    response_model=upload.Output,
    response_model_exclude_unset=True,
)
async def upload_user_picture_route(
    userId: str,  # noqa: N803
    headShot: Union[UploadFile, None] = File(None),  # noqa: N803
    photoIdPhoto: Union[UploadFile, None] = File(None),  # noqa: N803
    otherIdPhoto: Union[UploadFile, None] = File(None),  # noqa: N803
    user: global_models.User = Depends(AuthClient(use_auth=True)),
) -> JSONResponse:
    try:
        submit_to_db = {}
        if headShot:
            saved = await save_content(
                types="users",
                file=headShot,
                content_types=["image/png", "image/jpeg", "image/jpg"],
            )
            if not saved["success"]:  # type: ignore
                return user_error(
                    message=saved["reason"],  # type: ignore
                )
            submit_to_db["head_shot"] = saved["file_id"]  # type: ignore

        if photoIdPhoto:
            saved = await save_content(
                types="users",
                file=photoIdPhoto,
                content_types=["image/png", "image/jpeg", "image/jpg"],
            )
            if not saved["success"]:  # type: ignore
                return user_error(
                    message=saved["reason"],  # type: ignore
                )
            submit_to_db["photo_id_photo"] = saved["file_id"]  # type: ignore

        if otherIdPhoto:
            saved = await save_content(
                types="users",
                file=otherIdPhoto,
                content_types=["image/png", "image/jpeg", "image/jpg"],
            )
            if not saved["success"]:  # type: ignore
                return user_error(
                    message=saved["reason"],  # type: ignore
                )
            submit_to_db["other_id_photo"] = saved["file_id"]  # type: ignore

        saved_photos = await upload_user_pictures(
            save_to_db=submit_to_db,
            user_id=userId,
            user=user,
        )
        if not saved_photos:
            return server_error(message="Failed to upload files")

        return successful_response(
            payload=camel_case(submit_to_db),
        )
    except Exception:
        log.exception("Failed to add pictures to user")
        return server_error(
            message="Failed to add pictures to user",
        )


@router.post(
    "/upload/bulk/headshots",
    description="Route to upload bulk users headshots",
    response_model=upload.BulkOutput,
    response_model_exclude_unset=True,
)
async def upload_bulk_headshot_route(
    userIds: List[str] = Form(...),  # noqa: N803
    pictures: List[UploadFile] = File(...),
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "users.*",
                "data.import_students",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        submit_to_db = {}
        uploaded = []
        zipped = list(zip(userIds, pictures))
        for picture in zipped:
            saved = await save_content(
                types="users",
                file=picture[1],
                content_types=["image/png", "image/jpeg", "image/jpg"],
            )
            if not saved["success"]:  # type: ignore
                failed = {
                    "failed": True,
                    "reason": saved["reason"],  # type: ignore
                    "userId": picture[0],
                    "headShot": None,
                }
                log.error(failed)
                uploaded.append(failed)

            submit_to_db["head_shot"] = saved["file_id"]  # type: ignore

            saved_photos = await upload_user_pictures(
                save_to_db=submit_to_db,
                user_id=picture[0],
                user=user,
            )
            if not saved_photos:
                failed = {
                    "failed": True,
                    "reason": "Failed to upload headshot",
                    "userId": picture[0],
                    "headShot": None,
                }
                log.error(failed)
                uploaded.append(failed)

            uploaded.append(
                {
                    "failed": False,
                    "userId": picture[0],
                    "headShot": saved["file_id"],  # type: ignore
                },
            )

        return successful_response(
            payload={
                "headShots": uploaded,
            },
        )

    except Exception:
        log.exception("Failed to add pictures to users")
        return server_error(
            message="Failed to add pictures to users",
        )
