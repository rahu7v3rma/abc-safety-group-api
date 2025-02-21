import datetime
import json
from typing import List

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from passlib.hash import pbkdf2_sha256

from src import log
from src.api.api_models import global_models
from src.api.api_models.admin import (
    activate,
    assign,
    delete_certificates,
    gen_certificate,
    roles,
    user_delete_model,
)
from src.api.api_models.pagination import PaginationOutput
from src.api.api_models.users import update
from src.api.lib.auth.auth import AuthClient
from src.api.lib.base_responses import (
    server_error,
    successful_response,
    user_error,
)
from src.database.sql.audit_log_functions import submit_audit_record
from src.database.sql.course_functions import (
    get_course,
    get_course_certificate,
)
from src.database.sql.user_functions import (
    activate_user,
    deactivate_user,
    delete_user_certificates,
    delete_users,
    find_certificate,
    get_roles,
    get_user,
    manage_user_roles,
    update_user,
)
from src.modules.notifications import send_bug_report_notification
from src.utils.certificate_generation import generate_certificate
from src.utils.generate_random_code import (
    generate_random_certificate_number,
)
from src.utils.validate import validate_email, validate_phone_number

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    responses={404: {"description": "Details not found"}},
)


@router.get(
    "/roles/list",
    description="Route to list all roles",
    response_model=roles.ListOutput,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "admin.list_roles",
                    "admin.*",
                ],
            ),
        ),
    ],
)
async def list_roles(page: int = 1, pageSize: int = 20) -> JSONResponse:  # noqa: N803
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        roles, total_pages, total_count = await get_roles(
            page=page,
            pageSize=pageSize,
        )  # type: ignore
        if not roles:
            return server_error(message="No roles found.")

        pagination = PaginationOutput(
            curPage=page,
            totalPages=total_pages,  # type: ignore
            pageSize=len(roles),
            totalCount=total_count,  # type: ignore
        )
        return successful_response(
            payload={
                "roles": roles,
                "pagination": pagination.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get list of all roles")
        return server_error(
            message="Failed to get roles",
        )


@router.post(
    "/roles/manage/{userId}",
    description="Route to manage roles to a user",
    response_model=assign.Output,
)
async def roles_manage(
    userId: str,  # noqa: N803
    content: assign.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.manage_roles",
                "admin.*",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        if content.add:
            if not await manage_user_roles(
                roles=content.add,
                user_id=userId,
                action="add",
            ):
                return user_error(
                    message="Roles do not exist",
                )
        if content.remove:
            if not await manage_user_roles(
                roles=content.remove,
                user_id=userId,
                action="remove",
            ):
                return user_error(
                    message="Roles do not exist",
                )

        await submit_audit_record(
            route="admin/roles/manage/userId",
            details=(
                f"Update to roles for user {user.firstName} {user.lastName} "
                f"action {'add' if content.add else 'remove'} Added:"
                f" {content.add if content.add else 'None'} Removed: "
                f"{content.remove if content.remove else 'None'}"
            ),
            user_id=user.userId,
        )
        return successful_response()
    except Exception:
        log.exception(f"Failed to assign roles to user {userId}")
        return server_error(
            message=f"Failed to assign roles to user {userId}",
        )


@router.post(
    "/users/certificates/generate",
    description="Route to generate a certificate for course",
    response_model=gen_certificate.Output,
)
async def generate_certificate_route(
    content: gen_certificate.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.generate_certificates",
                "admin.*",
            ],
        ),
    ),
) -> JSONResponse:
    failed_users = []
    try:
        course, _ = await get_course(course_id=content.courseId)
        if not course:
            return user_error(message="Course does not exist")

        certificate = await get_course_certificate(course_id=content.courseId)

        for user_id in content.userIds:
            found_user = await get_user(user_id=user_id)
            if not found_user:
                failed_users.append(
                    f"User not found for user id {user_id}",
                )

            certificate_number = generate_random_certificate_number(
                length=10,
                course_code=course["courseCode"],
            )
            found = await find_certificate(
                user_id=user_id,
                course_id=content.courseId,
            )
            if found:
                failed_users.append(
                    f"User {found_user.firstName} {found_user.lastName} "  # type: ignore
                    f"already has a certificate for {course['courseName']}",
                )
                continue

            cert = await generate_certificate(
                user=found_user,  # type: ignore
                course=course,
                certificate=certificate,
                certificate_number=certificate_number,
                notify_users=content.notifyUsers,
                upload_certificates=content.uploadCertificates,
            )
            if not cert:
                failed_users.append(
                    f"Failed to generate certificate for user "
                    f"{found_user.firstName} {found_user.lastName}",  # type: ignore
                )
                continue

        if not failed_users:
            return successful_response()

        await submit_audit_record(
            route="admin/users/update/userId",
            details=(
                f"User {user.firstName} {user.lastName} "
                "generated certificate for users "
                f"{', '.join(content.userIds)} for course {content.courseId}"
            ),
            user_id=user.userId,
        )
        return successful_response(
            success=False,
            message=", ".join(failed_users),
        )

    except Exception:
        log.exception("Failed to generate certificates for users")

    return server_error(
        message="Failed to generate certificates",
    )


@router.post(
    "/users/certificates/delete",
    description="Route to get delete user certificates",
    response_model=delete_certificates.Output,
)
async def delete_certificate_route(
    content: delete_certificates.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.delete_certificates",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        deleted = await delete_user_certificates(
            certificate_numbers=content.certificateNumbers,
        )
        if not deleted:
            return server_error(message="Failed to delete user certificates")

        await submit_audit_record(
            route="admin/users/delete/certificates",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"deleted certificates {', '.join(content.certificateNumbers)}"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to delete user certificates")
        return server_error(message="Failed to delete user certificates")


@router.post(
    "/users/delete/{userId}",
    description="Route to delete users from system",
    response_model=user_delete_model.Output,
)
async def delete_user_route(
    userId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.delete_users",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        failed_deletes = await delete_users(user_ids=[userId])
        if failed_deletes:
            return server_error(
                message="Failed to delete user",
            )

        await submit_audit_record(
            route="admin/users/delete/userId",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"deleted user {userId} from lms"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to delete user from LMS")
        return server_error(
            message="Failed to delete user from LMS",
        )


@router.post(
    "/users/delete",
    description="Route to delete users from system",
    response_model=user_delete_model.Output,
)
async def bulk_delete_user_route(
    content: user_delete_model.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.delete_users",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        failed_deletes, err = await delete_users(user_ids=content.userIds)
        if failed_deletes and err:
            return server_error(
                message="Failed to delete user",
            )

        await submit_audit_record(
            route="admin/users/delete",
            details=(
                f"User {user.firstName} {user.lastName} deleted "
                f"users {', '.join(content.userIds)} from lms"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to delete user from LMS")
        return server_error(
            message="Failed to delete user from LMS",
        )


@router.post(
    "/users/deactivate/{userId}",
    description="Route to deactivate user in system",
    response_model=activate.Output,
)
async def deactivate_user_route(
    userId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.deactivate_user",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        deactivated = await deactivate_user(user_id=userId)
        if isinstance(deactivated, str):
            return user_error(message="User is already deactivated")

        if not deactivated:
            return server_error(
                message="An error occured while deactivating user",
            )

        await submit_audit_record(
            route="admin/users/deactivate/userId",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"deactivated user {userId} in lms"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to deactivate users in LMS")
        return server_error(
            message="Failed to deactivate users in LMS",
        )


@router.post(
    "/users/activate/{userId}",
    description="Route to activate user in system",
    response_model=activate.Output,
)
async def activate_user_route(
    userId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.activate_user",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        activated = await activate_user(user_id=userId)
        if isinstance(activated, str):
            return user_error(message="User is already activated")

        if not activated:
            return server_error(
                message="An error occured while deactivating user",
            )

        await submit_audit_record(
            route="admin/users/activate/userId",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"activated user {userId} in lms"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to activate users in LMS")
        return server_error(
            message="Failed to activate users in LMS",
        )


# TODO: refactor this function to make it less messy
@router.post(
    "/users/update/{userId}",
    description="Route to update account",
    response_model=update.Output,
)
async def update_user_route(
    userId: str,  # noqa: N803
    content: update.Input,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.update_user",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        found_user = await get_user(user_id=userId)
        if not found_user:
            return user_error(message="User does not exist")

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
            "other_id": content.otherId,
            "time_zone": content.timeZone,
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
            "expiration_date": datetime.datetime.strptime(
                content.expirationDate,
                "%m/%d/%Y",
            )
            if content.expirationDate
            else None,
        }
        if content.password:
            updated_user.update(
                {"password": pbkdf2_sha256.hash(content.password)},
            )

        updating = await update_user(user_id=userId, **updated_user)
        if not updating:
            return server_error(
                message="Something went wrong when updating the user",
            )

        updated = await get_user(user_id=userId)
        updated = updated.dict()  # type: ignore

        try:
            del updated["password"]
        except KeyError:
            pass
        # As of right now this is just returning True or false, will
        # likely need to change to
        # return the actual user object after being updated

        await submit_audit_record(
            route="admin/users/update/userId",
            details=(
                f"User {user.firstName} {user.lastName} updated "
                f"user {userId} with values {json.dumps(content.dict())}"
            ),
            user_id=user.userId,
        )

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


@router.post(
    "/bug-report",
    description="Route to post a bug report",
)
async def submit_bug_report(
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "admin.*",
                "admin.bug_report",
            ],
        ),
    ),
    subject: str = Form(...),
    body: str = Form(...),
    files: List[UploadFile] = File(None),
) -> JSONResponse:
    try:
        attachments = []
        types = {
            "application/pdf": "pdf",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",  # noqa: E501
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",  # noqa: E501
            "application/msword": "doc",
            "application/vnd.ms-powerpoint": "ppt",
            "image/png": "png",
            "image/jpeg": "jpeg",
            "image/jpg": "jpg",
            "text/csv": "csv",
        }

        for attachment in files:
            # Assuming file.content_type is 'image/png'
            # Convert MIME type to a file extension
            if not types.get(attachment.content_type):  # type: ignore
                continue

            file_path = f"/source/src/content/temp_files/{attachment.filename}.{types.get(attachment.content_type)}"  # type: ignore # noqa: E501
            with open(file_path, "wb") as file:  # noqa: ASYNC101
                file.write(attachment.file.read())
            attachments.append(file_path)

        send_bug_report_notification(
            subject=subject,
            body=body,
            attachments=attachments,
            user=user,
        )
    except Exception:
        log.exception("An error occured while sending bug report")
        return server_error(
            message="An error occured while sending bug report",
        )

    return successful_response()
