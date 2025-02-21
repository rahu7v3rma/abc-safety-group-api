import datetime
import json
import os
from io import BytesIO
from typing import Optional, Union

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from src import img_handler, log
from src.api.api_models import global_models, pagination
from src.api.api_models.courses import (
    bundle,
    bundle_update,
    complete,
    course_update,
    delete,
    enroll,
    event,
    list_all,
    list_bundles_model,
    list_courses_model,
    load_course_model,
    schedule_list,
    schedule_update,
    schedule_verify,
    search,
    search_schedule_model,
    upload,
)
from src.api.lib.auth.auth import AuthClient
from src.api.lib.base_responses import (
    server_error,
    successful_response,
    user_error,
)
from src.database.sql.audit_log_functions import submit_audit_record
from src.database.sql.course_functions import (
    assign_course,
    batch_get_courses,
    check_bundle_registration,
    check_course_registration,
    delete_bundle,
    delete_class,
    delete_content,
    delete_course,
    find_class_time,
    get_bundle,
    get_content,
    get_course,
    get_course_certificate,
    get_scheduled_class,
    get_total_course_schedule,
    list_bundles,
    list_courses,
    list_courses_and_bundles,
    mark_bundle_as_complete,
    mark_class_as_complete,
    mark_course_as_complete,
    search_courses,
    search_schedule,
    set_course_picture,
    update_bundle,
    update_course,
    update_schedule,
    validate_prerequisites,
)
from src.database.sql.user_functions import (
    find_certificate,
    get_course_bundle_students,
    get_user,
    get_user_roles,
)
from src.modules.save_content import save_content
from src.utils.certificate_generation import generate_certificate
from src.utils.check_overlap import check_overlap
from src.utils.generate_random_code import (
    generate_random_certificate_number,
    generate_random_code,
)
from src.utils.image import is_valid_image, resize_image

router = APIRouter(
    prefix="/courses",
    tags=["Courses"],
    responses={404: {"description": "Details not found"}},
)


@router.get(
    "/list",
    description="Route to list all courses",
    response_model=list_courses_model.CoursesOutput,
)
async def course_list(
    ignoreBundle: bool = False,  # noqa: N803
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    complete: bool = False,
    inactive: bool = False,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.list",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        courses, total_pages, total_count = await list_courses(
            ignore_bundle=ignoreBundle,
            page=page,
            pageSize=pageSize,
            complete=complete,
            inactive=inactive,
            user=user,
        )
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(courses),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "courses": courses,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get list of all courses")
        return server_error(
            message="Failed to get courses",
        )


@router.post(
    "/search",
    description="Route to search for courses",
    response_model=search.Output,
)
async def course_search(
    content: search.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.course_search",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        found, total_pages, total_count = await search_courses(
            course_bundle=content.courseBundle,
            course_name=content.courseName,
            name=content.name,
            page=page,
            pageSize=pageSize,
            user=user,
        )
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(found),
            totalCount=total_count,
        )
        payload = {
            "pagination": pg.dict(),
        }
        if content.courseBundle:
            payload["bundles"] = found

        if content.courseName:
            payload["courses"] = found

        if content.name:
            payload["found"] = found

        return successful_response(
            payload=payload,
        )

    except Exception:
        log.exception("Failed to get list of all courses")
        return server_error(
            message="Failed to get courses",
        )


@router.post(
    "/assign/instructor/{courseId}",
    description="Route to assign an instructor to a course",
    response_model=enroll.Output,
)
async def assign_instructors(
    courseId: str,  # noqa: N803
    content: enroll.InstructorInput,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.assign_instructor",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=courseId)
        if not course:
            return user_error(message="Course does not exist")

        assigned = await assign_course(
            course_id=courseId,
            instructors=content.instructors,
        )
        if not assigned:
            return server_error(
                message="Failed to assign instructors to course",
            )

        instructors = []
        user_ids = []
        for instructor in content.instructors:
            found_user = await get_user(user_id=instructor.userId)  # type: ignore
            if found_user:
                instructors.append(found_user)
                user_ids.append(instructor.userId)  # type: ignore

        await submit_audit_record(
            route="courses/assign/instructor/courseId",
            details=f"Assigned instructors {','.join(user_ids)} to course {courseId}",  # noqa: E501
            user_id=user.userId,
        )
        return successful_response()
    except Exception:
        log.exception("Failed to assign instructors to course")
        return server_error(
            message="Failed to assign instructors to course",
        )


@router.post(
    "/delete",
    description="Route to delete courses",
    response_model=delete.Output,
)
async def course_delete(
    content: delete.Input,
    bypassChecks: bool = False,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.delete",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        if not content.courseIds:
            return user_error(message="Course IDs required")
        for course_id in content.courseIds:
            course, _ = await get_course(course_id=course_id)
            if not course:
                return user_error(
                    message="Course does not exist",
                )

            # if all checks pass delete else error
            if not await delete_course(course_id=course_id):
                return server_error(
                    message=f"Failed to delete course {course_id}",
                )
            # delete course content folder
            if course["coursePicture"]:
                os.remove(
                    f'/source/src/content/courses/{course["coursePicture"]}',
                )

        await submit_audit_record(
            route="courses/delete",
            details=(
                f"Courses {', '.join(content.courseIds)} have been deleted"
            ),
            user_id=user.userId,
        )
        return successful_response()
    except Exception:
        log.exception(f"Failed to delete course {course_id}")
        return server_error(
            message="Failed to delete course",
        )


# TODO: refactor this function to make it less messy
@router.post(
    "/bundle/delete",
    description="Route to delete bundles",
    response_model=delete.Output,
)
async def bundle_delete(
    content: delete.Input,
    bypassChecks: bool = False,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.delete",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        if not content.bundleIds:
            return user_error(message="Bundle IDs must be supplied")
        for bundle_id in content.bundleIds:
            bundle, _ = await get_bundle(bundle_id=bundle_id)
            if not bundle:
                return user_error(
                    message="Bundle does not exist",
                )
            for bc in bundle["courses"]:
                course, _ = await get_course(course_id=bc["courseId"])
                if not course:
                    continue
                # if all checks pass delete else error
                if not await delete_course(course_id=bc["courseId"]):
                    return server_error(
                        message="Failed to delete course {courseId}",
                    )
                # delete course content folder
                if course["coursePicture"]:
                    os.remove(
                        f'/source/src/content/courses/{course["coursePicture"]}',
                    )

            if not await delete_bundle(bundle_id=bundle_id):
                return server_error(
                    message=f"Failed to delete bundle {bundle_id}",
                )
        await submit_audit_record(
            route="courses/bundle/delete",
            details=(
                f"Bundles {', '.join(content.bundleIds)} have been deleted"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception(f"Failed to delete bundle {bundle_id}")
        return server_error(
            message="Failed to delete bundle",
        )


@router.get(
    "/load/{courseId}",
    description="Route to load an entire courses details",
    response_model=load_course_model.Output,
)
async def load_course(
    courseId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.load",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        user_roles = await get_user_roles(user_id=user.userId)
        roles = [role["roleName"] for role in user_roles]
        show_address = True
        enrolled = False

        if "admin" not in roles or "instructor" not in roles:
            show_address = False

        registered = await check_course_registration(
            course_id=courseId,
            user_id=user.userId,
        )
        if (
            isinstance(registered, str)
            and registered == "User already enrolled"
        ):
            enrolled = True
            show_address = True

        course, schedule = await get_course(
            course_id=courseId,
            enrolled=show_address,
            user=user,
        )
        if not course:
            return user_error(
                message="Course does not exist",
            )

        if course["enrollable"]:
            enrollable = await validate_prerequisites(
                course=course,
                user_id=user.userId,
            )
            course["enrollable"] = enrollable

        payload = {
            "course": course,
            "schedule": schedule,
            "enrolled": enrolled,
        }

        return successful_response(
            payload=payload,
        )
    except Exception:
        log.exception(f"Failed to load course {courseId}")
        return server_error(
            message=f"Failed to load course {courseId}",
        )


@router.get(
    "/bundle/list",
    description="Route to list all bundles",
    response_model=list_bundles_model.Output,
)
async def bundle_list(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    complete: bool = False,
    inactive: bool = False,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.list",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        bundles, total_pages, total_count = await list_bundles(
            page=page,
            pageSize=pageSize,
            complete=complete,
            user=user,
            inactive=inactive,
        )
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(bundles),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "bundles": bundles,
                "pagination": pg.dict(),
            },
        )
    except Exception:
        log.exception("Failed to get list of all bundles")
        return server_error(
            message="Failed to get bundles",
        )


@router.get(
    "/bundle/load/{bundleId}",
    description="Route to create a course bundle",
    response_model=bundle.Output,
)
async def load_bundle_route(
    bundleId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.load",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        user_roles = await get_user_roles(user_id=user.userId)
        roles = [role["roleName"] for role in user_roles]
        show_address = True
        enrolled = False

        if "admin" not in roles or "instructor" not in roles:
            show_address = False

        registered = await check_bundle_registration(
            bundle_id=bundleId,
            user_id=user.userId,
        )
        if (
            isinstance(registered, str)
            and registered == "User already enrolled"
        ):
            enrolled = True
            show_address = True

        bundle, schedule = await get_bundle(
            bundle_id=bundleId,
            enrolled=show_address,
            user=user,
        )
        if not bundle:
            return server_error(
                message="Bundle does not exist",
            )

        payload = {
            "bundle": bundle,
            "schedule": schedule,
            "enrolled": enrolled,
        }

        return successful_response(payload=payload)

    except Exception:
        log.exception("Failed to load course")
        return server_error(
            message="Failed to load course",
        )


@router.get(
    "/schedule",
    description="Route to get all scheduled courses",
    response_model=schedule_list.Output,
)
async def complete_schedule(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    startDate: Optional[str] = None,  # noqa: N803
    endDate: Optional[str] = None,  # noqa: N803
    complete: bool = False,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.schedule",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        schedule, total_pages, total_count = await get_total_course_schedule(
            page=page,
            pageSize=pageSize,
            start_date=startDate,
            end_date=endDate,
            complete=complete,
            user=user,
        )
        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(schedule),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "schedule": schedule,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception("Failed to fetch complete schedule")
        return server_error(
            message="Failed to fetch complete schedule",
        )


@router.post(
    "/schedule/search",
    description="Route to search for a course schedule",
    response_model=search_schedule_model.Output,
)
async def search_schedule_route(
    content: search_schedule_model.Input,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.schedule_search",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")

    try:
        schedule, total_pages, total_count = await search_schedule(
            course_name=content.courseName,
            bundle_name=content.bundleName,
            page=page,
            pageSize=pageSize,
            user=user,
        )

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(schedule),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "schedule": schedule,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception("Failed to fetch schedule")
        return server_error(
            message="Failed to fetch schedule",
        )


@router.post(
    "/schedule/verify",
    description="Route to see if schedules intertwine",
    response_model=schedule_verify.Output,
    dependencies=[
        Depends(
            AuthClient(
                use_auth=True,
                permission_nodes=[
                    "courses.*",
                    "courses.schedule",
                ],
            ),
        ),
    ],
)
async def schedule_verify_route(
    content: schedule_verify.Input,
) -> JSONResponse:
    try:
        scheduled_times = []
        amount_of_courses_with_schedules = 0

        courses = await batch_get_courses(course_ids=content.courseIds)
        if not courses:
            return user_error(message="No valid courses found")

        for course, schedule in courses:
            if not schedule:
                continue
            amount_of_courses_with_schedules += 1
            for class_time in schedule:
                course_sched = {
                    "startTime": class_time["startTime"],
                    "endTime": class_time["endTime"],
                    "courseName": course["courseName"],
                    "courseId": course["courseId"],
                }
                scheduled_times.append(course_sched)

        overlapping = []
        if amount_of_courses_with_schedules > 1:
            for schedule1 in scheduled_times:
                for schedule2 in scheduled_times:
                    if schedule1 != schedule2 and check_overlap(
                        schedule1,
                        schedule2,
                    ):
                        overlapping.append(schedule1)
                        break
                if overlapping:
                    break

        if overlapping:
            return successful_response(
                success=False,
                payload={
                    "courses": overlapping,
                },
            )

        return successful_response()
    except Exception:
        log.exception("Failed to verify course schedules")
        return server_error(
            message="Failed to verify course schedules",
        )


@router.post(
    "/schedule/delete/{courseId}/{seriesNumber}",
    description="Route to delete a scheduled class",
    response_model=course_update.Output,
)
async def delete_class_route(
    courseId: str,  # noqa: N803
    seriesNumber: int,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.schedule_delete",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=courseId)
        if not course:
            return user_error(message="Course does not exist")

        found_class = await find_class_time(
            course_id=courseId,
            series_number=seriesNumber,
        )
        if not found_class:
            return user_error(message="Class does not exist")

        await delete_class(course_id=courseId, series_number=seriesNumber)
        await submit_audit_record(
            route="courses/schedule/delete/courseId/seriesNumber",
            details=(
                f"User {user.firstName} {user.lastName} deleted "
                f"scheduled class {seriesNumber} for course {courseId}"
            ),
            user_id=user.userId,
        )

        return successful_response()

    except Exception:
        log.exception("Failed to delete course class")
        return server_error(
            message="Failed to delete course class",
        )


@router.post(
    "/update",
    description="Route to get update a course",
    response_model=course_update.Output,
)
async def update_course_route(
    content: course_update.UpdateCourseInput,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.update",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=content.courseId)
        if not course:
            return user_error(message="Course does not exist")

        if not await update_course(content):
            return server_error(message="Failed to update course")

        await submit_audit_record(
            route="courses/update",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"updated course {content.courseId} with"
                f" values {json.dumps(content.dict(exclude_none=True))}"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to act on course update")
        return server_error(
            message="Failed to act on course update",
        )


@router.post(
    "/bundle/update",
    description="Route to get update a course bundle",
    response_model=bundle_update.Output,
)
async def update_bundle_route(
    content: bundle_update.UpdateBundleInput,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.update",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        bundle, _ = await get_bundle(bundle_id=content.bundleId)
        if not bundle:
            return user_error(message="Bundle does not exist")

        enrollment_start_date = None
        if not bundle["active"] == content.active and content.active is True:
            enrollment_start_date = datetime.datetime.utcnow()
        if not await update_bundle(
            content=content,
            enrollment_start_date=enrollment_start_date,
            first_class=bundle["startDate"],
        ):
            return server_error(message="Failed to update bundle")

        await submit_audit_record(
            route="courses/bundle/update",
            details=(
                f"User {user.firstName} {user.lastName} "
                f"updated bundle {content.bundleId} with"
                f" values {json.dumps(content.dict(exclude_none=True))}"
            ),
            user_id=user.userId,
        )
        return successful_response()

    except Exception:
        log.exception("Failed to act on bundle update")
        return server_error(
            message="Failed to act on bundle update",
        )


@router.get(
    "/list/all",
    description="Route to get bundles and courses for course management",
    response_model=list_all.Output,
)
async def manage_list(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    complete: Optional[bool] = None,
    inactive: Optional[bool] = None,
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.list",
            ],
        ),
    ),
) -> JSONResponse:
    if isinstance(page, int) and page <= 0:
        page = 1
        if 1 > pageSize < 1000:
            return user_error(message="pageSize out of bounds must be 1-1000")
    try:
        (
            courses_and_bundles,
            total_pages,
            total_count,
        ) = await list_courses_and_bundles(
            page=page,
            pageSize=pageSize,
            complete=complete,
            inactive=inactive,
            user=user,
        )

        pg = pagination.PaginationOutput(
            curPage=page,
            totalPages=total_pages,
            pageSize=len(courses_and_bundles),
            totalCount=total_count,
        )
        return successful_response(
            payload={
                "found": courses_and_bundles,
                "pagination": pg.dict(),
            },
        )

    except Exception:
        log.exception("Failed to get courses or bundles")
        return server_error(
            message="Failed to get courses or bundles",
        )


@router.get(
    "/content/load/{fileId}",
    description="Route to load course content",
    response_model=None,
)
async def load_content_get(
    fileId: str,  # noqa: N803
    uid: str,
    size: int = 1024,
    published: bool = False,
) -> Union[JSONResponse, FileResponse, Response]:
    try:
        if not img_handler.get_key(redis_key=uid):
            return user_error(
                status_code=403,
                message="Unauthorized",
            )

        content, _, _ = await get_content(
            content_id=fileId,
            published=published,
        )  # type: ignore
        if content:
            user_roles = await get_user_roles(user_id=uid)
            if not user_roles:
                raise ValueError

            if (
                any(
                    role["roleName"]
                    not in ["instructor", "admin", "superuser"]
                    for role in user_roles
                )
                and not published
            ):
                return user_error(
                    status_code=401,
                    message="unauthorized",
                )

        file_location = rf"/source/src/content/courses/{fileId}"
        if not os.path.exists(file_location):
            await delete_content(file_ids=[fileId])
            return server_error(message="File does not exist")

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
        log.exception(f"Something went wrong loading content for course {id}")
        return server_error(
            message="Something wetn wrong when loading content",
        )


@router.post(
    "/schedule/update/{courseId}/{seriesNumber}",
    description="Route to update scheduled class",
    response_model=schedule_update.Output,
)
async def schedule_update_route(
    content: schedule_update.Input,
    courseId: str,  # noqa: N803
    seriesNumber: int,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.schedule_update",
            ],
        ),
    ),
) -> JSONResponse:
    new_class = None
    try:
        found_class = await find_class_time(
            course_id=courseId,
            series_number=seriesNumber,
        )
        if not found_class:
            return user_error(message="Class does not exist")

        if found_class["is_complete"]:
            return user_error(message="Class is already marked as complete")

        if found_class["in_progress"]:
            return user_error(message="Class is already in progress")

        start_dtm = datetime.datetime.strptime(
            content.startTime.replace("Z", "+0000"),
            "%Y-%m-%dT%H:%M:%S.%f%z",
        )
        end_dtm = datetime.datetime.strptime(
            content.endTime.replace("Z", "+0000"),
            "%Y-%m-%dT%H:%M:%S.%f%z",
        )

        new_class = {
            "is_complete": False,
            "course_id": courseId,
            "series_number": seriesNumber,
            "start_dtm": start_dtm,
            "end_dtm": end_dtm,
            "in_progress": False,
        }
        updated = await update_schedule(new_class=new_class)
        if not updated:
            return server_error(message="Failed to update scheduled class")

        # users = []
        # instructors = await get_instructors(courseId)
        # if instructors:
        #     users.extend(instructors)
        # students = await get_students(courseId)
        # if students:
        #     users.extend(students)

        # course, _ = await get_course(course_id=courseId)
        # scheduled_class_update_notifcation(
        #     users=users,
        #     new_class=new_class,
        #     original_class=found_class,
        #     course=course,
        # )

        await submit_audit_record(
            route="courses/schedule/update",
            details=(
                f"User {user.firstName} {user.lastName} updated schedule "
                f"details for course {courseId} series_number {seriesNumber}"
                f" from {str(found_class['start_dtm'])} - {str(found_class['end_dtm'])}"  # noqa: E501
                f" to {str(new_class['start_dtm'])} - {str(new_class['end_dtm'])}"  # noqa: E501
            ),
            user_id=user.userId,
        )

    except Exception:
        log.exception("Something went wrong when trying to update class time")
        return server_error(
            message="Something went wrong when trying to update class time",
        )

    return successful_response()


@router.post(
    "/content/upload/{courseId}",
    description="Route to upload a course picture/content",
    response_model=upload.Output,
)
async def upload_course_content_route(
    courseId: str,  # noqa: N803
    coursePicture: Union[UploadFile, None] = File(None),  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.upload_content",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=courseId)
        if not course:
            return user_error(
                message="Course does not exist",
            )

        if coursePicture:
            saved = await save_content(
                types="courses",
                file=coursePicture,
                content_types=["image/png", "image/jpeg", "image/jpg"],
            )
            if not saved["success"]:  # type: ignore
                return user_error(
                    message=saved["reason"],  # type: ignore
                )

            picture_set = await set_course_picture(
                course_id=courseId,
                course_picture=saved["file_id"],  # type: ignore
                user=user,
            )
            if not picture_set:
                return server_error(message="Failed to set course picture")

        successfully_saved = []

        await submit_audit_record(
            route="courses/upload/content/courseId",
            details=f"User {user.firstName} {user.lastName} uploaded content for course {courseId}",  # noqa: E501
            user_id=user.userId,
        )
        return successful_response(
            payload={"content": successfully_saved},
        )

    except Exception:
        log.exception("Failed to add content to course")
        return server_error(
            message="Failed to add content to course",
        )


# TODO: refactor this function to make it less messy
@router.post(
    "/complete/{courseId}",
    description="Route to mark a course as complete",
    response_model=complete.Output,
)
async def complete_course_route(
    courseId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.complete",
            ],
        ),
    ),
    generateCertificates: bool = False,  # noqa: N803
    uploadCertificates: bool = False,  # noqa: N803
    notifyUsers: bool = True,  # noqa: N803
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=courseId)
        if not course:
            return user_error(
                message=f"No course with id {courseId} exists",
            )

        if course["complete"]:
            return user_error(message="Course is already marked as complete")

        await mark_class_as_complete(course_id=courseId)
        await mark_course_as_complete(course_id=courseId)

        await submit_audit_record(
            route="courses/complete/courseId",
            details=f"User {user.firstName} {user.lastName} marked course {courseId} as complete",  # noqa: E501
            user_id=user.userId,
        )
        students, _, _ = await get_course_bundle_students(course_id=courseId)

        if not generateCertificates:
            return successful_response()

        certificate = await get_course_certificate(course_id=courseId)

        if students:
            for student in students:
                found_user = await get_user(user_id=student["userId"])  # type: ignore
                if not found_user:
                    continue
                found_certificate = await find_certificate(
                    user_id=found_user.userId,
                    course_id=courseId,
                )
                if found_certificate:
                    continue

                certificate_number = generate_random_certificate_number(
                    length=10,
                    course_code=course["courseCode"],
                )
                cert = await generate_certificate(
                    user=found_user,
                    course=course,
                    certificate=certificate,
                    certificate_number=certificate_number,
                    notify_users=notifyUsers,
                    upload_certificates=uploadCertificates,
                )
                if not cert:
                    continue

        await submit_audit_record(
            route="courses/complete/courseId",
            details=(
                f"User {user.firstName} {user.lastName} generated "
                f"certificates for students in course {courseId}"
            ),
            user_id=user.userId,
        )

        return successful_response()
    except Exception:
        log.exception("Failed to mark complete course as complete")
        return server_error(
            message="Failed to mark complete course as complete",
        )


@router.post(
    "/schedule/complete/{courseId}/{seriesNumber}",
    description="Route to mark a class as complete",
    response_model=complete.Output,
)
async def complete_class_route(
    courseId: str,  # noqa: N803
    seriesNumber: int,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.schedule_complete",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        course, _ = await get_course(course_id=courseId)
        if not course:
            return user_error(
                message="Course does not exist",
            )

        await mark_class_as_complete(
            course_id=courseId,
            series_number=seriesNumber,
        )

        await submit_audit_record(
            route="courses/schedule/complete/courseId",
            details=(
                f"User {user.firstName} {user.lastName} marked series "
                f"number {seriesNumber} as complete for course {courseId}"
            ),
            user_id=user.userId,
        )
        return successful_response()
    except Exception:
        log.exception("Failed to mark complete course as complete")
        return server_error(
            message="Failed to mark complete course as complete",
        )


@router.get(
    "/schedule/load/{courseId}/{seriesNumber}",
    description="Route to get scheduled class's details",
    response_model=event.Output,
)
async def get_class_route(
    courseId: str,  # noqa: N803
    seriesNumber: int,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.load_class",
            ],
        ),
    ),
) -> JSONResponse:
    try:
        show_details = False
        user_roles = await get_user_roles(user_id=user.userId)
        registered = await check_course_registration(
            course_id=courseId,
            user_id=user.userId,
        )
        if (
            isinstance(registered, str)
            and registered == "User already enrolled"
        ) or (
            any(
                role["roleName"] in ["instructor", "admin", "superuser"]
                for role in user_roles
            )
        ):
            show_details = True
        scheduled_class = await get_scheduled_class(
            course_id=courseId,
            series_number=seriesNumber,
            show_details=show_details,
            user=user,
        )
        if not scheduled_class:
            return server_error(message="Failed to find scheduled class")

        return successful_response(
            payload={
                "details": scheduled_class,
            },
        )

    except Exception:
        log.exception("Failed to get class details")
        return server_error(
            message="Failed to get class details",
        )


# TODO: refactor this function to make it less messy
@router.post(
    "/bundle/complete/{bundleId}",
    description="Route to mark a bundle as complete",
    response_model=complete.Output,
)
async def complete_bundle_route(
    bundleId: str,  # noqa: N803
    user: global_models.User = Depends(
        AuthClient(
            use_auth=True,
            permission_nodes=[
                "courses.*",
                "courses.complete",
            ],
        ),
    ),
    generateCertificates: bool = False,  # noqa: N803
    uploadCertificates: bool = False,  # noqa: N803
    notifyUsers: bool = True,  # noqa: N803
) -> JSONResponse:
    try:
        bundle, _ = await get_bundle(bundle_id=bundleId)
        if not bundle:
            return user_error(
                message=f"No bundle with id {bundleId} exists",
            )

        if bundle["complete"]:
            return user_error(message="Bundle is already marked as complete")

        await mark_bundle_as_complete(bundle_id=bundleId)

        for course in bundle["courses"]:
            await mark_course_as_complete(course_id=course["courseId"])
            await mark_class_as_complete(course_id=course["courseId"])
            course, _ = await get_course(course_id=course["courseId"])
            if not course:
                continue
            if not generateCertificates:
                continue

            certificate = await get_course_certificate(
                course_id=course["courseId"],
            )
            students, _, _ = await get_course_bundle_students(
                course_id=course["courseId"],
            )
            if students:
                for student in students:
                    found_user = await get_user(user_id=student["userId"])
                    found_certificate = await find_certificate(
                        user_id=found_user.userId,  # type: ignore
                        course_id=course["courseId"],
                    )
                    if found_certificate:
                        continue

                    certificate_number = generate_random_code(15)
                    cert = await generate_certificate(
                        user=found_user,  # type: ignore
                        course=course,
                        certificate=certificate,
                        certificate_number=certificate_number,
                        notify_users=notifyUsers,
                        upload_certificates=uploadCertificates,
                    )
                    if not cert:
                        continue

        await submit_audit_record(
            route="courses/bundle/complete/bundleId",
            details=f"User {user.firstName} {user.lastName} marked bundle {bundleId} as complete",  # noqa: E501
            user_id=user.userId,
        )

        if generateCertificates:
            await submit_audit_record(
                route="courses/bundle/complete/bundleId",
                details=f"User {user.firstName} {user.lastName} generated certificates in bundle {bundleId}",  # noqa: E501
                user_id=user.userId,
            )

        return successful_response()

    except Exception:
        log.exception("Failed to mark complete bundle as complete")
        return server_error(
            message="Failed to mark complete bundle as complete",
        )
