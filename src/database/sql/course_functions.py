import datetime
import os
from math import ceil
from typing import List, Optional, Tuple, Union

from src import log
from src.api.api_models import global_models
from src.api.api_models.courses import (
    bundle,
    bundle_update,
    course_update,
    create,
)
from src.database.sql import acquire_connection, get_connection
from src.utils.convert_date import convert_tz
from src.utils.snake_case import camel_to_snake


async def list_courses(
    user: global_models.User,
    ignore_bundle: bool = False,
    enrollment: bool = False,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    complete: bool = False,
    inactive: bool = False,
    ignore_enrolled: bool = False,
    user_id: Optional[str] = None,
) -> Tuple[list, int, int]:
    conditions = []

    params = []
    if not enrollment:
        conditions.append(f"c.is_complete = ${len(params)+1}")
        params.append(complete)

    if enrollment:
        conditions.extend(
            [
                "c.active = true",
                "c.is_complete = false",
                "(c.waitlist = true or c.is_full = false)",
                "c.registration_expiration_dtm > CURRENT_TIMESTAMP",
                "c.enrollment_start_date < CURRENT_TIMESTAMP",
            ],
        )
    if ignore_bundle:
        conditions.append("bc.course_id IS NULL")

    if inactive:
        conditions.append("c.active = false")

    if ignore_enrolled:
        conditions.append(f"""
        NOT EXISTS (
            SELECT 1
            FROM course_registration cr
            WHERE cr.user_id = ${len(params)+1} and cr.course_id = c.course_id
        )""")
        params.append(user_id)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    pagination_clause = ""
    pg = []
    if page and pageSize:
        pagination_clause = (
            f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        )
        pg = [pageSize, (page - 1) * pageSize]

    query = f"""
        SELECT
            c.course_picture,
            c.course_id,
            c.course_name,
            c.first_class_dtm,
            c.brief_description,
            c.classes_in_series,
            c.active,
            c.is_complete,
            c.create_dtm,
            c.live_classroom
        FROM courses AS c
        LEFT JOIN bundled_courses AS bc ON c.course_id = bc.course_id
        {where_clause}
        ORDER BY c.create_dtm DESC
        {pagination_clause};
    """

    total_count = 0
    total_pages = 0
    coursesList = []
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT COUNT(*)
                    FROM courses AS c
                    LEFT JOIN bundled_courses AS bc ON c.course_id = bc.course_id
                    {where_clause};
                """,
                    *params,
                )
            courses = await conn.fetch(query, *params, *pg)

            for course in courses:
                course_object = {
                    "courseId": course["course_id"],
                    "coursePicture": course["course_picture"],
                    "courseName": course["course_name"],
                    "startDate": (
                        datetime.datetime.strftime(
                            convert_tz(
                                course["first_class_dtm"],
                                tz=user.timeZone,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if course["first_class_dtm"]
                        else None
                    ),
                    "totalClasses": course["classes_in_series"],
                    "courseType": "Course",
                    "active": course["active"],
                    "complete": course["is_complete"],
                    "briefDescription": course["brief_description"],
                }
                coursesList.append(course_object)
    except Exception:
        log.exception("An error occured while getting courses list")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return coursesList, ceil(total_pages), total_count


async def get_course(
    course_id: str,
    user: Optional[global_models.User] = None,
    full_details: bool = False,
    enrolled: bool = False,
) -> tuple:
    """Function to get a course

    Args:
        course_id (str, optional): Course Id to get the course wanted.
        Defaults to None.

    Returns:
        Union[None, global_models.Course]: Model of a course with values
    """
    if not course_id:
        return None, None

    course = None
    schedule = None
    query = """
        SELECT
            c.course_id,
            c.course_name,
            c.brief_description,
            c.course_picture,
            c.price,
            c.languages,
            c.instruction_types,
            c.active,
            c.max_students,
            c.is_full,
            c.waitlist,
            c.first_class_dtm,
            c.enrollment_start_date,
            c.registration_expiration_dtm,
            c.description,
            c.email,
            c.phone_number,
            c."address",
            c.remote_link,
            c.waitlist_limit,
            c.allow_cash,
            c.course_code,
            c.is_complete,
            c.live_classroom
        FROM
            courses c
        WHERE
            c.course_id = $1
        GROUP BY
            c.course_id;
    """

    prerequisitesQuery = """
        SELECT
            c.course_id,
            c.course_name
            FROM courses c
            LEFT JOIN prerequisites p
            on c.course_id = p.prerequisite
            where p.course_id = $1;
    """

    instructorsQuery = """
        SELECT
            u.user_id,
            u.first_name,
            u.last_name
            FROM users u
            JOIN course_instructor ci
            ON u.user_id = ci.user_id
            WHERE ci.course_id = $1;
    """

    scheduleQuery = """
        SELECT
            is_complete,
            course_id,
            series_number,
            start_dtm,
            end_dtm,
            in_progress
        FROM course_dates
        WHERE course_id = $1
        ORDER BY start_dtm ASC;
    """

    formQuery = """
        SELECT
            cf.form_id,
            cf.form_name,
            cf.course_id,
            f.form_type
        FROM course_forms cf
        LEFT JOIN forms f ON cf.form_id = f.form_id
        GROUP BY cf.form_id, cf.form_name, cf.course_id, f.form_type
        WHERE cf.course_id = $1;
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_course = await conn.fetchrow(query, course_id)
            prerequisites = await conn.fetch(prerequisitesQuery, course_id)
            found_schedule = await conn.fetch(scheduleQuery, course_id)
            instructors = await conn.fetch(instructorsQuery, course_id)

            if full_details:
                forms = await conn.fetch(formQuery, course_id)
                quiz = []
                survey = []
                if forms:
                    for f in forms:
                        if f["form_type"] == "quiz":
                            quiz.append(f)
                        elif f["form_type"] == "survey":
                            survey.append(f)

            if found_course:
                course = {
                    "courseId": found_course["course_id"],
                    "courseName": found_course["course_name"],
                    "briefDescription": found_course["brief_description"],
                    "coursePicture": found_course["course_picture"],
                    "price": found_course["price"],
                    "prerequisites": [],
                    "languages": found_course["languages"],
                    "instructionTypes": found_course["instruction_types"],
                    "active": found_course["active"],
                    "maxStudents": found_course["max_students"],
                    "isFull": found_course["is_full"],
                    "waitlist": found_course["waitlist"],
                    "startDate": datetime.datetime.strftime(
                        convert_tz(
                            found_course["first_class_dtm"],
                            tz=user.timeZone if user else None,
                        ),
                        "%m/%d/%Y %-I:%M %p",
                    ),
                    "description": found_course["description"],
                    "instructors": [],
                    "email": found_course["email"],
                    "phoneNumber": found_course["phone_number"],
                    "waitlistLimit": found_course["waitlist_limit"],
                    "allowCash": found_course["allow_cash"],
                    "courseCode": found_course["course_code"],
                    "complete": found_course["is_complete"],
                }
                if enrolled:
                    course.update(
                        {
                            "remoteLink": found_course["remote_link"],
                            "address": found_course["address"],
                        },
                    )

                if found_course["enrollment_start_date"]:
                    enrollable = (
                        True
                        if found_course["enrollment_start_date"]
                        <= datetime.datetime.utcnow()
                        <= found_course["registration_expiration_dtm"]
                        else False
                    )
                else:
                    enrollable = False
                course.update({"enrollable": enrollable})

                if full_details:
                    course.update({"quiz": quiz})
                    course.update({"survey": survey})

                if instructors:
                    for instructor in instructors:
                        course["instructors"].append(
                            {
                                "userId": instructor["user_id"],
                                "firstName": instructor["first_name"],
                                "lastName": instructor["last_name"],
                            },
                        )

                if prerequisites:
                    for prereq in prerequisites:
                        course["prerequisites"].append(
                            {
                                "courseId": prereq["course_id"],
                                "courseName": prereq["course_name"],
                            },
                        )

                schedule = []
                if found_schedule:
                    for event in found_schedule:
                        class_event = {
                            "courseId": event["course_id"],
                            "courseName": found_course["course_name"],
                            "startTime": datetime.datetime.strftime(
                                convert_tz(
                                    event["start_dtm"],
                                    tz=user.timeZone if user else None,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "endTime": datetime.datetime.strftime(
                                convert_tz(
                                    event["end_dtm"],
                                    tz=user.timeZone if user else None,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "duration": (
                                event["end_dtm"] - event["start_dtm"]
                            ).total_seconds()
                            // 60,
                            "seriesNumber": event["series_number"],
                            "complete": event["is_complete"],
                        }
                        if enrolled:
                            class_event.update(
                                {
                                    "address": found_course["address"],
                                    "remoteLink": found_course["remote_link"],
                                },
                            )
                        schedule.append(class_event)

        return (
            course,
            schedule,
        )
    except Exception:
        log.exception(
            f"An error occured while getting course with course_id {course_id}",
        )

    return (None, None)


async def batch_get_courses(
    course_ids: List[str],
    full_details: bool = False,
) -> Union[None, List[tuple]]:
    """Function to get a course

    Args:
        course_id (str, optional): Course Id to get the course wanted. Defaults to None.

    Returns:
        Union[None, global_models.Course]: Model of a course with values
    """
    if not course_ids:
        return []

    courses = {}
    schedules = {}

    length = ", ".join(["$" + str(i + 1) for i in range(len(course_ids))])

    query = f"""
        SELECT
            c.course_id,
            c.course_name,
            c.brief_description,
            c.course_picture,
            c.price,
            c.languages,
            c.instruction_types,
            c.active,
            c.max_students,
            c.is_full,
            c.waitlist,
            c.first_class_dtm,
            c.enrollment_start_date,
            c.registration_expiration_dtm,
            c.description,
            c.email,
            c.phone_number,
            c."address",
            c.remote_link,
            c.waitlist_limit,
            c.allow_cash,
            c.course_code,
            c.is_complete,
            c.live_classroom
        FROM
            courses c
        WHERE
            c.course_id IN ({length})
        GROUP BY
            c.course_id;
    """

    prerequisitesQuery = f"""
        SELECT
            c.course_id as prereq,
            c.course_name,
            p.course_id
        FROM courses c
        LEFT JOIN prerequisites p
        on c.course_id = p.prerequisite
        where p.course_id IN ({length});
    """

    instructorsQuery = f"""
        SELECT
            u.user_id,
            u.first_name,
            u.last_name,
            ci.course_id
        FROM users u
        JOIN course_instructor ci
        ON u.user_id = ci.user_id
        WHERE ci.course_id IN ({length});
    """

    scheduleQuery = f"""
        SELECT
            cd.is_complete,
            cd.course_id,
            cd.series_number,
            cd.start_dtm,
            cd.end_dtm,
            cd.in_progress,
            c.live_classroom
        FROM course_dates AS cd
        JOIN courses c on c.course_id = cd.course_id
        WHERE cd.course_id IN ({length})
        ORDER BY start_dtm ASC;
    """

    formQuery = f"""
        SELECT
            cf.form_id,
            cf.form_name,
            cf.course_id,
            f.form_type
        FROM course_forms cf
        LEFT JOIN forms f ON cf.form_id = f.form_id
        GROUP BY cf.form_id, cf.form_name, cf.course_id, f.form_type
        WHERE cf.course_id IN ({length});
    """

    found_courses = None
    prerequisites = None
    found_schedule = None
    instructors = None
    found_forms = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_courses = await conn.fetch(query, *course_ids)
            prerequisites = await conn.fetch(prerequisitesQuery, *course_ids)
            found_schedule = await conn.fetch(scheduleQuery, *course_ids)
            instructors = await conn.fetch(instructorsQuery, *course_ids)

            if full_details:
                found_forms = await conn.fetch(formQuery, *course_ids)

        if found_courses:
            for c in found_courses:
                if courses.get(c["course_id"]):
                    continue
                courses[c["course_id"]] = {
                    "courseId": c["course_id"],
                    "courseName": c["course_name"],
                    "briefDescription": c["brief_description"],
                    "coursePicture": c["course_picture"],
                    "price": c["price"],
                    "prerequisites": [],
                    "languages": c["languages"],
                    "instructionTypes": c["instruction_types"],
                    "active": c["active"],
                    "maxStudents": c["max_students"],
                    "isFull": c["is_full"],
                    "waitlist": c["waitlist"],
                    "startDate": c["first_class_dtm"].strftime(
                        "%m/%d/%Y %-I:%M %p",
                    ),
                    "description": c["description"],
                    "instructors": [],
                    "email": c["email"],
                    "phoneNumber": c["phone_number"],
                    "address": c["address"],
                    "remoteLink": c["remote_link"],
                    "waitlistLimit": c["waitlist_limit"],
                    "allowCash": c["allow_cash"],
                    "courseCode": c["course_code"],
                    "complete": c["is_complete"],
                }

                if c["enrollment_start_date"]:
                    enrollable = (
                        True
                        if c["enrollment_start_date"]
                        <= datetime.datetime.utcnow()
                        <= c["registration_expiration_dtm"]
                        else False
                    )
                else:
                    enrollable = False
                courses[c["course_id"]].update({"enrollable": enrollable})

                if full_details:
                    courses[c["course_id"]].update({"quiz": []})
                    courses[c["course_id"]].update({"survey": []})

            if found_forms:
                for form in found_forms:
                    if not courses.get(form["course_id"]):
                        continue

                    if form["form_type"] == "quiz":
                        courses[form["course_id"]]["quiz"].append(form)
                    elif form["form_type"] == "survey":
                        courses[form["course_id"]]["survey"].append(form)

            if instructors:
                for instructor in instructors:
                    if not courses.get(instructor["course_id"]):
                        continue
                    courses[instructor["course_id"]]["instructors"].append(
                        {
                            "userId": instructor["user_id"],
                            "firstName": instructor["first_name"],
                            "lastName": instructor["last_name"],
                        },
                    )

            if prerequisites:
                for prereq in prerequisites:
                    if not courses.get(prereq["course_id"]):
                        continue
                    courses[prereq["course_id"]]["prerequisites"].append(
                        {
                            "courseId": prereq["prereq"],
                            "courseName": prereq["course_name"],
                        },
                    )

            if found_schedule:
                for event in found_schedule:
                    if not courses.get(event["course_id"]):
                        continue

                    if not schedules.get(event["course_id"]):
                        schedules[event["course_id"]] = []

                    schedules[event["course_id"]].append(
                        {
                            "courseId": event["course_id"],
                            "startTime": event["start_dtm"].strftime(
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "endTime": event["end_dtm"].strftime(
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "duration": (
                                event["end_dtm"] - event["start_dtm"]
                            ).total_seconds()
                            // 60,
                            "seriesNumber": event["series_number"],
                            "complete": event["is_complete"],
                        },
                    )

        paired_courses = []
        for course_id, details in courses.items():
            paired_courses.append((details, schedules.get(course_id, [])))

        return paired_courses
    except Exception:
        log.exception("An error occured while getting courses")

    return []


async def check_course_registration(
    course_id: str,
    user_id: str,
) -> Union[dict, str, None]:
    course, _ = await get_course(course_id=course_id)

    if not course:
        return None

    query = """
        SELECT
            cr.course_id,
            cr.user_id,
            cr.registration_status,
            cr.student_registration_date,
            cr.enroll_date,
            cr.denial_reason,
            cr.user_paid,
            cr.using_cash,
            c.auto_student_enrollment
        FROM
            course_registration  cr
        JOIN courses c on c.course_id = cr.course_id
        WHERE cr.course_id = $1 AND cr.registration_status IN ('enrolled', 'waitlist', 'pending');
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            users = await conn.fetch(query, course_id)

        enrolled = []
        waitlist = []
        course_data = {
            "courseId": course_id,
            "isFull": course["isFull"],
            "waitlist": course["waitlist"],
            "enrollable": course["enrollable"],
            "complete": course["complete"],
        }
        change = False
        if users:
            for u in users:
                if user_id == u["user_id"]:
                    return "User already enrolled"
                if u["registration_status"] == "enrolled":
                    enrolled.append(u)
                elif u["registration_status"] == "waitlist":
                    waitlist.append(u)
                # course_data["pending"] = u[4]

        if not course["isFull"] and len(enrolled) >= course["maxStudents"]:
            course_data["isFull"] = True
            change = True
        if course["waitlist"] and len(waitlist) >= course["waitlistLimit"]:
            course_data["waitlist"] = False
            change = True

        if change:
            updated = course_update.UpdateCourseInput(
                courseId=course_data["courseId"],
                isFull=course_data["isFull"],
                waitlist=course_data["waitlist"],
            )
            await update_course(updated)

        return course_data

    except Exception:
        log.exception(
            f"An error occured while getting students registration type for {course_id}",
        )

    return None


async def check_bundle_registration(
    bundle_id: str,
    user_id: str,
) -> Union[dict, str, None]:
    bundle = await get_bundle(bundle_id=bundle_id)

    if not bundle[0]:
        return None

    bundle = bundle[0]

    course_ids = [course["courseId"] for course in bundle["courses"]]

    query = """
        SELECT
            cr.course_id,
            cr.user_id,
            cr.registration_status,
            cr.student_registration_date,
            cr.enroll_date,
            cr.denial_reason,
            cr.user_paid,
            cr.using_cash,
            c.auto_student_enrollment
        FROM
            course_registration  cr
        JOIN courses c on c.course_id = cr.course_id
        WHERE cr.course_id IN ({}) AND cr.registration_status IN ('enrolled', 'waitlist', 'pending');
    """.format(", ".join(["$" + str(i + 1) for i in range(len(course_ids))]))

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            users = await conn.fetch(query, *course_ids)
        enrolled = []
        waitlist = []
        bundle_data = {
            "bundleId": bundle_id,
            "isFull": bundle["isFull"],
            "enrollable": bundle["enrollable"],
            "waitlist": bundle["waitlist"],
            "courses": bundle["courses"],
            "complete": bundle["complete"],
        }

        change = False
        if users:
            for u in users:
                if user_id == u["user_id"]:
                    return "User already enrolled"
                if u["registration_status"] == "enrolled":
                    enrolled.append(u)
                elif u["registration_status"] == "waitlist":
                    waitlist.append(u)
                # course_data["pending"] = u[4]

        if not bundle["isFull"] and len(enrolled) / 3 >= bundle["maxStudents"]:
            bundle_data["isFull"] = True
            change = True
        if bundle["waitlist"] and len(waitlist) / 3 >= bundle["waitlistLimit"]:
            bundle_data["waitlist"] = False
            change = True

        if change:
            updated = bundle_update.UpdateBundleInput(
                bundleId=bundle_data["bundleId"],
                isFull=bundle_data["isFull"],
                waitlist=bundle_data["waitlist"],
            )
            await update_bundle(updated)

        return bundle_data

    except Exception:
        log.exception(
            f"An error occured while getting students registration type for {bundle_id}",
        )

    return None


async def search_courses(
    user: global_models.User,
    course_name: Optional[str] = None,
    course_bundle: Optional[str] = None,
    name: Optional[str] = None,
    catalog: bool = False,
    page: int = 1,
    pageSize: int = 20,
) -> tuple:
    """Function to search for a course

    Args:
        course_name (str, optional): Course name needed to find the course. Defaults to None.
        course_bundle (str, optional): Bundle name needed to find the course bundle. Defaults to None.
        catalog (bool, optional): depicts whether not its for the catalog for students. Defaults to None.

    Returns:
        Tuple[list, list]: A list of courses
    """

    query = None
    value = None
    params = []

    pagination = ""
    if page and pageSize:
        pagination = "LIMIT $2 OFFSET $3"
        params.extend([pageSize, (page - 1) * pageSize])

    if course_name:
        value = f"%{course_name}%"
        query = f"""
            SELECT
                c.course_picture,
                c.course_id,
                c.course_name,
                c.first_class_dtm,
                c.brief_description,
                c.classes_in_series,
                c.active,
                c.is_complete,
                c.create_dtm,
                c.waitlist,
                c.is_full,
                c.registration_expiration_dtm,
                c.live_classroom
            FROM courses AS c
            where UPPER(c.course_name) LIKE UPPER($1)
            {"and c.is_complete = false and c.active = true and (c.is_full = false or c.waitlist = true)" +
            " and c.registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''}
            ORDER BY c.create_dtm DESC
            {pagination};
        """

    if course_bundle:
        value = f"%{course_bundle}%"
        query = f"""
            SELECT
                cb.bundle_photo,
                cb.bundle_id,
                cb.bundle_name,
                cb.active,
                cb.is_complete,
                SUM(c.classes_in_series) AS total_classes,
                cb.create_dtm,
                MIN(cd.start_dtm) as start_dtm,
                cb.waitlist,
                cb.is_full,
                cb.registration_expiration_dtm
            FROM
                course_bundles cb
            LEFT JOIN
                bundled_courses bc ON cb.bundle_id = bc.bundle_id
            LEFT JOIN
                courses c ON bc.course_id = c.course_id
            LEFT JOIN
                course_dates cd ON cd.course_id = bc.course_id
            where UPPER(cb.bundle_name) LIKE UPPER($1)
            {"and cb.is_complete = false and cb.active = true and (cb.is_full = false or" +
            " cb.waitlist) = true and cb.registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''}
            GROUP BY
                cb.bundle_id, cb.bundle_name, cb.brief_description, cb.bundle_photo, cb.active, cb.is_complete
            ORDER BY
                cb.create_dtm DESC
            {pagination};
        """

    if name:
        value = f"%{name}%"
        query = f"""
            WITH course_data AS (
                SELECT
                    c.course_id AS id,
                    c.course_name AS name,
                    'course' AS type,
                    c.first_class_dtm AS start_dtm,
                    c.classes_in_series AS total_classes,
                    c.course_picture,
                    c.brief_description,
                    c.active,
                    c.is_complete,
                    c.waitlist,
                    c.is_full,
                    c.registration_expiration_dtm,
                    c.live_classroom
                FROM courses c
                UNION ALL
                SELECT
                    cb.bundle_id AS id,
                    cb.bundle_name AS name,
                    'bundle' AS type,
                    MIN(cd.start_dtm) AS start_dtm,
                    COUNT(cd.start_dtm) AS total_classes,
                    NULL AS course_picture,
                    NULL AS brief_description,
                    cb.active,
                    cb.is_complete,
                    cb.waitlist,
                    cb.is_full,
                    cb.registration_expiration_dtm
                    FALSE AS live_classroom
                FROM course_bundles cb
                JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
                JOIN course_dates cd ON bc.course_id = cd.course_id
                GROUP BY cb.bundle_id, cb.bundle_name, cb.active, cb.is_complete
            )
            SELECT *
            FROM course_data
            WHERE UPPER(name) LIKE UPPER($1)
            {"and is_complete = false and active = true and (is_full = false or waitlist = true)" +
            " and registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''}
            ORDER BY start_dtm
            {pagination};
        """

    courses = []
    total_count = 0
    total_pages = 0
    found_courses = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_courses = await conn.fetch(query, value, *params)
            if course_name:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT COUNT(DISTINCT c.course_id)
                    FROM courses AS c
                    WHERE UPPER(c.course_name) LIKE UPPER($1)
                    {"and c.is_complete = false and c.active = true and c.is_full = false or c.waitlist = true" +
                    " and c.registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''};
                """,
                    value,
                )
            elif course_bundle:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT COUNT(DISTINCT cb.bundle_id)
                    FROM course_bundles cb
                    JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
                    JOIN courses c ON bc.course_id = c.course_id
                    WHERE UPPER(cb.bundle_name) LIKE UPPER($1)
                    {"and cb.is_complete = false and cb.active = true and cb.is_full = false and" +
                    " cb.waitlist = true and cb.registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''};
                """,
                    value,
                )
            elif name:
                total_count = await conn.fetchrow(
                    f"""
                    WITH course_data AS (
                        SELECT
                            c.course_id AS id,
                            c.course_name AS name,
                            'course' AS type,
                            c.first_class_dtm AS start_dtm,
                            c.classes_in_series AS total_classes,
                            c.course_picture,
                            c.brief_description,
                            c.active,
                            c.is_complete,
                            c.waitlist,
                            c.is_full,
                            c.registration_expiration_dtm
                        FROM courses c
                        UNION ALL
                        SELECT
                            cb.bundle_id AS id,
                            cb.bundle_name AS name,
                            'bundle' AS type,
                            MIN(cd.start_dtm) AS start_dtm,
                            COUNT(cd.start_dtm) AS total_classes,
                            NULL AS course_picture,
                            NULL AS brief_description,
                            cb.active,
                            cb.is_complete,
                            cb.waitlist,
                            cb.is_full,
                            cb.registration_expiration_dtm
                        FROM course_bundles cb
                        JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
                        JOIN course_dates cd ON bc.course_id = cd.course_id
                        GROUP BY cb.bundle_id, cb.bundle_name, cb.active, cb.is_complete
                    )
                    SELECT COUNT(DISTINCT id)
                    FROM course_data
                    WHERE UPPER(name) LIKE UPPER($1)
                    {"and is_complete = false and active = true and is_full = false and waitlist = true" +
                    " and registration_expiration_dtm > CURRENT_TIMESTAMP" if catalog else ''};
                """,
                    value,
                )
        if found_courses:
            if course_name:
                for found in found_courses:
                    courses.append(
                        {
                            "coursePicture": found["course_picture"],
                            "courseId": found["course_id"],
                            "courseName": found["course_name"],
                            "startDate": datetime.datetime.strftime(
                                convert_tz(
                                    found["first_class_dtm"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "briefDescription": found["brief_description"],
                            "totalClasses": found["classes_in_series"],
                            "courseType": "Course",
                            "active": found["active"],
                            "complete": found["is_complete"],
                        },
                    )

            if course_bundle:
                for found in found_courses:
                    courses.append(
                        {
                            "bundlePicture": found["bundle_photo"],
                            "bundleId": found["bundle_id"],
                            "bundleName": found["bundle_name"],
                            "active": found["active"],
                            "complete": found["is_complete"],
                            "totalClasses": found["total_classes"],
                            "courseType": "Bundle",
                            "startDate": datetime.datetime.strftime(
                                convert_tz(
                                    found["start_dtm"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if found["start_dtm"]
                            else None,
                        },
                    )

            if name:
                for found in found_courses:
                    courses.append(
                        {
                            "id": found["id"],
                            "picture": found["course_picture"],
                            "name": found["name"],
                            "type": found["type"],
                            "startDate": datetime.datetime.strftime(
                                convert_tz(
                                    found["start_dtm"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if found["start_dtm"]
                            else None,
                            "totalClasses": found["total_classes"],
                            "active": found["active"],
                            "complete": found["is_complete"],
                            "briefDescription": found["brief_description"],
                        },
                    )

    except Exception:
        log.exception(
            f"An error occured while getting courses related to {value}",
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return courses, ceil(total_pages), total_count


async def assign_course(
    course_id: str,
    students: Optional[list] = None,
    instructors: Optional[list] = None,
) -> bool:
    """Function to assign a course to students or instructors

    Args:
        course_id (str, optional): Course Id to assign to user. Defaults to None.
        students (list, optional): List of students to be assigned to course. Defaults to None.
        instructors (list, optional): List of students to be assigned to course. Defaults to None.

    Raises:
        ValueError: If students and instructors are both provided

    Returns:
        boolean: True if it was assigned, false if it failed
    """
    query = None
    value_type = None
    values = None

    if students and instructors:
        raise ValueError(
            "Can only assign one type of user to a course not both",
        )

    if students:
        value_type = "students"
        query = """
            INSERT INTO course_registration (
                course_id,
                user_id,
                registration_status,
                student_registration_date,
                enroll_date,
                denial_reason,
                user_paid,
                using_cash,
                notes
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9);
        """
        values = []
        for student in students:
            values.append(
                (
                    course_id,
                    student.userId,
                    student.registrationStatus,
                    datetime.datetime.utcnow(),
                    datetime.datetime.utcnow()
                    if student.registrationStatus == "enrolled"
                    else None,
                    student.denialReason,
                    student.userPaid,
                    student.usingCash,
                    student.notes,
                ),
            )

    if instructors:
        value_type = "instructors"
        query = """
            INSERT INTO course_instructor (
                course_id,
                user_id
            )
            VALUES ($1, $2);
        """
        values = []
        for instructor in instructors:
            values.append(
                (
                    course_id,
                    instructor,
                ),
            )

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.executemany(query, values)
        return True

    except Exception:
        log.exception(
            f"An error occured while assigning {value_type} to course_id {course_id}",
        )
    return False


async def delete_course(course_id: str) -> bool:
    """Function to delete a course

    Args:
        course_id (str, optional): Course Id in which needs to be deleted.
        Defaults to None.

    Returns:
        bool: True if deleted, False if failed
    """
    if not course_id:
        return False

    queries = [
        "DELETE FROM prerequisites WHERE course_id = $1 or prerequisite = $1;",
        "DELETE FROM course_dates WHERE course_id = $1;",
        "DELETE FROM course_instructor WHERE course_id = $1;",
        "DELETE FROM course_registration WHERE course_id = $1;",
        "DELETE FROM course_content WHERE course_id = $1;",
        "DELETE FROM bundled_courses WHERE course_id = $1;",
        "DELETE FROM courses WHERE course_id = $1;",
    ]

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            for query in queries:
                await conn.execute(query, course_id)
        return True

    except Exception:
        log.exception(
            f"An error occured while getting deleting course {course_id}",
        )

    return False


async def update_course(content: course_update.UpdateCourseInput) -> bool:
    """Function to update a course

    Args:
        content (course_update.UpdateCourseInput): Takes in a model of optional args to be updated.

    Returns:
        dict: Returns a course
    """
    try:
        course_id = content.courseId
        instructors = content.instructors
        prerequisites = content.prerequisites
        course = camel_to_snake(content.dict(exclude_unset=True))
        if course.get("enrollable"):
            course["enrollment_start_date"] = datetime.datetime.utcnow()

        del course["enrollable"]
        del course["course_id"]
        del course["instructors"]
        del course["prerequisites"]

        updaters = []
        course_values = [course_id]
        for idx, key in enumerate(list(course.keys())):
            updaters.append(f"{key}=${idx+2}")

        update_query = "UPDATE courses SET {} WHERE course_id = $1;".format(
            ", ".join(updaters),
        )
        course_values.extend(list(course.values()))

        if instructors:
            instructor_update_query = (
                """DELETE FROM course_instructor WHERE course_id = $1;"""
            )
            instructor_update_query_1 = """
                INSERT INTO course_instructor (
                    course_id,
                    user_id
                )
                VALUES ($1, $2);
            """

            instructorValues = []
            for instructor in instructors:
                instructorValues.append(
                    [
                        course_id,
                        instructor,
                    ],
                )

        if prerequisites:
            prerequisites_update_query = (
                """DELETE FROM prerequisites WHERE course_id = $1;"""
            )
            prerequisites_update_query_1 = """
                INSERT INTO prerequisites (
                    course_id,
                    prerequisite
                )
                VALUES ($1, $2);
            """
            prerequisitesValues = []
            for prerequisite in prerequisites:
                prerequisitesValues.append(
                    [
                        course_id,
                        prerequisite,
                    ],
                )

        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(update_query, *course_values)
            if instructors:
                for instructor in instructorValues:
                    await conn.execute(instructor_update_query, course_id)
                    await conn.execute(instructor_update_query_1, *instructor)

            if prerequisites:
                for prerequisite in prerequisitesValues:
                    await conn.execute(prerequisites_update_query, course_id)
                    await conn.execute(
                        prerequisites_update_query_1,
                        *prerequisite,
                    )
        return True

    except Exception:
        log.exception("An error occured while updating course")

    return False


async def list_bundles(
    user: global_models.User,
    enrollment: bool = False,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    complete: bool = False,
    user_id: Optional[str] = None,
    ignore_enrolled: bool = False,
    inactive: bool = False,
) -> Tuple[list, int, int]:
    """Function to list all bundles

    Returns:
        list: A list of bundles
    """

    conditions = []
    params = []
    pg = []
    if enrollment:
        conditions.extend(
            [
                "cb.active = true",
                "cb.is_complete = false",
                "(cb.waitlist = true or c.is_full = false)",
                "cb.registration_expiration_dtm > CURRENT_TIMESTAMP",
                "cb.enrollment_start_date < CURRENT_TIMESTAMP",
            ],
        )
    else:
        conditions.append(f"cb.is_complete = ${len(params)+1}")
        params.append(complete)

    if ignore_enrolled:
        conditions.append(f"""
        NOT EXISTS (
            SELECT 1
            FROM course_registration cr
            WHERE cr.user_id = ${len(params)+1} and cr.course_id = c.course_id
        )""")
        params.append(user_id)
    where_condition = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    if inactive:
        conditions.append("cb.active = false")

    pagination = ""
    if page and pageSize:
        pagination = f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        SELECT
            cb.bundle_photo,
            cb.bundle_id,
            cb.bundle_name,
            cb.active,
            cb.is_complete,
            SUM(distinct c.classes_in_series) AS total_classes,
            cb.create_dtm,
            MIN(cd.start_dtm) as start_dtm
        FROM
            course_bundles cb
        JOIN
            bundled_courses bc ON cb.bundle_id = bc.bundle_id
        JOIN
            course_dates cd ON bc.course_id = cd.course_id
        JOIN
            courses c ON bc.course_id = c.course_id
        {where_condition}
        GROUP BY
            cb.bundle_id, cb.bundle_name, cb.brief_description, cb.bundle_photo, cb.active, cb.is_complete
        ORDER BY
            cb.create_dtm DESC
        {pagination};
    """

    listBundles = []
    total_count = 0
    total_pages = 0
    bundles = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            bundles = await conn.fetch(query, *params, *pg)
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT COUNT(*)
                    FROM course_bundles cb
                    JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
                    JOIN courses c ON bc.course_id = c.course_id
                    {where_condition}
                    GROUP BY cb.bundle_id, cb.bundle_name, cb.brief_description, cb.bundle_photo, cb.active, cb.is_complete
                    ORDER BY cb.create_dtm DESC;
                """,
                    *params,
                )

        if bundles:
            for b in bundles:
                listBundles.append(
                    {
                        "bundleId": b["bundle_id"],
                        "bundlePicture": b["bundle_photo"],
                        "bundleName": b["bundle_name"],
                        "startDate": datetime.datetime.strftime(
                            convert_tz(
                                b["start_dtm"],
                                tz=user.timeZone,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if b["start_dtm"]
                        else None,
                        "totalClasses": b["total_classes"],
                        "courseType": "Bundle",
                        "active": b["active"],
                        "complete": b["is_complete"],
                    },
                )
    except Exception:
        log.exception("An error occured while getting a course bundle")
        log.info(query)
        log.info(params)
    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return listBundles, ceil(total_pages), total_count


async def update_bundle(
    content: bundle_update.UpdateBundleInput,
    enrollment_start_date: Optional[datetime.datetime] = None,
    first_class: Optional[str] = None,
) -> bool:
    """Functiont o update a bundle

    Args:
        content (bundle_update.UpdateBundleInput): Model of optional arguments to be updated in a bundle.

    Returns:
        dict: Returns bundle back
    """

    try:
        courses = content.courseIds
        bundle_id = content.bundleId
        bundle = camel_to_snake(content.dict(exclude_unset=True))
        del bundle["bundle_id"]
        del bundle["course_ids"]

        if enrollment_start_date:
            bundle["enrollment_start_date"] = enrollment_start_date
            bundle["registration_expiration_dtm"] = datetime.datetime.strptime(
                first_class,  # type: ignore
                "%m/%d/%Y %I:%M %p",
            )

        update_query = (
            "UPDATE course_bundles SET {} WHERE bundle_id = $1".format(
                ", ".join(
                    [
                        f"{key} = ${idx+2}"
                        for idx, key in enumerate(list(bundle.keys()))
                    ],
                ),
            )
        )

        update_values = [bundle_id]
        update_values.extend(list(bundle.values()))

        if courses:
            courses_update_query_1 = (
                """DELETE FROM bundled_courses WHERE course_id = $1;"""
            )
            courses_update_query = """
                INSERT INTO bundled_courses (
                    bundle_id,
                    course_id
                )
                VALUES ($1, $2);
            """

            courseValues = []
            for course_id in courses:
                courseValues.append(
                    (
                        bundle_id,
                        course_id,
                    ),
                )

        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(update_query, *update_values)
            if courses:
                for value in courseValues:
                    await conn.execute(courses_update_query_1, value[0])
                    await conn.execute(courses_update_query, *value)
        return True

    except Exception:
        log.exception("An error occured while updating bundle")

    return False


async def create_course(
    general: create.General,
    user: global_models.User,
    course_id: str,
    classes_in_series: int = 20,
    active: bool = False,
    first_class_dtm: datetime.datetime = None,
    quizzes: list = None,
    surveys: list = None,
    schedule: List[dict] = None,
    frequency: dict = None,
    is_complete: bool = False,
    certificate: bool = False,
    live_classroom: bool = True,
) -> bool:
    """Function to create a course

    Args:
        general (create.General): Model of general info of a course. Course Name, etc.
        schedule (dict): _description_
        frequency (dict): _description_
        user (global_models.User): _description_
        course_id (str): Id of the Course being created
        classes_in_series (int, optional): _description_. Defaults to 20.
        active (bool, optional): _description_. Defaults to False.
        content (list, optional): Any course content, such as images, pdf, etc. Defaults to None.
        first_class_dtm (str, optional): Starting date of the first class. Defaults to None.

    Raises:
        ValueError: If unable to assign instructors to the course

    Returns:
        bool: True if created, False if failed
    """
    courseQuery = """
        INSERT INTO courses (
            course_id,
            course_name,
            brief_description,
            description,
            instruction_types,
            remote_link,
            address,
            max_students,
            classes_in_series,
            class_frequency,
            active,
            enrollment_start_date,
            registration_expiration_dtm,
            create_dtm,
            modify_dtm,
            created_by,
            modified_by,
            auto_student_enrollment,
            waitlist,
            waitlist_limit,
            price,
            allow_cash,
            phone_number,
            languages,
            is_complete,
            is_full,
            first_class_dtm,
            email,
            course_code,
            certificate,
            live_classroom
        )
        VALUES (
            $1,
            $2,
            $3,
            $4,
            $5,
            $6,
            $7,
            $8,
            $9,
            $10,
            $11,
            $12,
            $13,
            $14,
            $15,
            $16,
            $17,
            $18,
            $19,
            $20,
            $21,
            $22,
            $23,
            $24,
            $25,
            $26,
            $27,
            $28,
            $29,
            $30,
            $31
        );
    """

    scheduleValues = []
    prerequisitesValues = []

    if schedule:
        scheduleQuery = """
            INSERT INTO course_dates (
                is_complete,
                course_id,
                series_number,
                start_dtm,
                end_dtm,
                in_progress
            ) VALUES ($1, $2, $3, $4, $5, $6);
        """

        for idx, event in enumerate(schedule):
            scheduleValues.append(
                (
                    is_complete,
                    course_id,
                    idx + 1,
                    event[0].replace(tzinfo=None),
                    event[1].replace(tzinfo=None),
                    False,
                ),
            )

    if general.prerequisites:
        prerequisitesQuery = """
            INSERT INTO prerequisites (
                course_id,
                prerequisite
            ) VALUES ($1, $2);
        """

        if general.prerequisites:
            for prerequisite in general.prerequisites:
                prerequisitesValues.append(
                    (
                        course_id,
                        prerequisite,
                    ),
                )

    formQuery = """
        INSERT INTO course_forms (
            course_id,
            form_id,
            create_dtm,
            modify_dtm,
            available,
            created_by,
            modified_by,
            is_complete
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
    """

    forms = []
    formValues = []
    if quizzes:
        forms.extend(quizzes)
    if surveys:
        forms.extend(surveys)
    if forms:
        for form_id in forms:
            formValues.append(
                (
                    course_id,
                    form_id,
                    datetime.datetime.utcnow(),
                    datetime.datetime.utcnow(),
                    False,
                    user.userId,
                    user.userId,
                    False,
                ),
            )

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                courseQuery,
                course_id,
                general.courseName,
                general.briefDescription if general.briefDescription else None,
                general.description,
                general.instructionTypes,
                general.remoteLink,
                general.address,
                general.maxStudents,
                classes_in_series,
                frequency["frequency_type"],
                active,
                datetime.datetime.utcnow() if general.enrollable else None,
                first_class_dtm.replace(tzinfo=None)
                - datetime.timedelta(hours=3),
                datetime.datetime.utcnow(),
                datetime.datetime.utcnow(),
                user.userId,
                user.userId,
                True if active else False,
                general.waitlist,
                general.waitlistLimit
                if general.waitlistLimit
                else general.maxStudents,
                general.price,
                general.allowCash,
                general.phoneNumber,
                general.languages if general.languages else None,
                is_complete,
                False,
                first_class_dtm.replace(tzinfo=None),
                general.email,
                general.courseCode if general.courseCode else None,
                certificate,
                live_classroom,
            )

            if scheduleValues:
                await conn.executemany(scheduleQuery, scheduleValues)

            if prerequisitesValues:
                await conn.executemany(prerequisitesQuery, prerequisitesValues)

            if formValues:
                await conn.executemany(formQuery, formValues)

        if general.instructors:
            assigned = await assign_course(
                course_id=course_id,
                instructors=general.instructors,
            )
            if not assigned:
                raise ValueError("Unable to assign instructors to course")

        return True

    except Exception:
        log.exception("An error occured while creating course")

    return False


async def create_bundle(
    content: bundle.Input,
    bundle_id: str,
    user_id: str,
    is_complete: bool = False,
):
    """Function to create a bundle

    Args:
        content (bundle.Input): Model of what is being sent to create the bundle with
        bundle_id (str): Bundle Id being used for creation of Bundle
        user_id (str): The user id of which the bundle belongs to

    Returns:
        boolean: True if bundle was created, False if bundle failed
    """

    bundle_query = """
        INSERT INTO course_bundles (
            bundle_id,
            bundle_name,
            active,
            enrollment_start_date,
            registration_expiration_dtm,
            max_students,
            create_dtm,
            modify_dtm,
            created_by,
            modified_by,
            auto_student_enrollment,
            waitlist,
            waitlist_limit,
            price,
            allow_cash,
            is_full,
            is_complete
        ) VALUES (
            $1,
            $2,
            $3,
            $4,
            (
                SELECT
                    MIN(start_dtm)
                FROM course_dates
                WHERE course_id IN ({})
            ),
            $5,
            $6,
            $7,
            $8,
            $9,
            true,
            $10,
            $11,
            $12,
            $13,
            false,
            $14
        );
    """.format(
        ", ".join(["$" + str(i + 15) for i in range(len(content.courseIds))]),
    )

    courses_query = """
        INSERT INTO bundled_courses (
            bundle_id,
            course_id
        ) VALUES ($1, $2);
    """

    values = []
    for course_id in content.courseIds:
        values.append(
            (
                bundle_id,
                course_id,
            ),
        )

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                bundle_query,
                bundle_id,
                content.bundleName,
                content.active,
                datetime.datetime.utcnow() if content.active else None,
                content.maxStudents,
                datetime.datetime.utcnow(),
                datetime.datetime.utcnow(),
                user_id,
                user_id,
                content.waitlist,
                content.maxStudents,
                content.price,
                content.allowCash,
                is_complete,
                *content.courseIds,
            )

            if values:
                await conn.executemany(courses_query, values)

        return True

    except Exception:
        log.exception("An error occured while creating course")

    return False


async def get_bundle(
    bundle_id: str,
    enrolled: bool = False,
    user: global_models.User = None,
) -> tuple:
    """Function to get a bundle based on a bundle ID

    Args:
        bundle_id (str): Bundle Id to look up, is required

    Returns:
        tuple: Returns a bundle and schedule
    """

    query = """
        SELECT
            c.course_id,
            c.course_name,
            c.brief_description,
            c.first_class_dtm,
            c.instruction_types,
            c.languages,
            c.live_classroom,
            b.bundle_name,
            b.bundle_id,
            b.bundle_photo,
            b.price,
            b.active,
            b.max_students,
            b.is_full,
            b.waitlist,
            b.waitlist_limit,
            b.is_complete,
            MIN(cd.start_dtm) as start_date,
            b.enrollment_start_date,
            b.registration_expiration_dtm,
            b.allow_cash
        FROM
            course_bundles b
        JOIN
            bundled_courses bc ON bc.bundle_id = b.bundle_id
        JOIN
            courses c ON c.course_id = bc.course_id
        LEFT JOIN
            prerequisites p ON p.bundle_id = b.bundle_id AND p.course_id = c.course_id
        LEFT JOIN
            course_dates cd ON cd.course_id = c.course_id
        WHERE
            b.bundle_id = $1
        GROUP BY
            c.course_id,
            c.course_name,
            c.first_class_dtm,
            c.brief_description,
            c.instruction_types,
            c.languages,
            b.bundle_name,
            b.bundle_id,
            b.bundle_photo,
            b.price,
            b.active,
            b.max_students,
            b.is_full,
            b.waitlist,
            b.waitlist_limit,
            c.live_classroom
        ORDER BY
            start_date DESC;
    """

    prerequisitesQuery = """
        SELECT
            b.bundle_id,
            b.bundle_name,
            b.brief_description
            FROM course_bundles b
            JOIN prerequisites p
            on b.bundle_id = p.bundle_id
            where p.bundle_id = $1;
    """

    scheduleQuery = """
        SELECT
            c.course_name,
            cd.course_id,
            cd.start_dtm,
            cd.end_dtm,
            cd.series_number,
            cd.is_complete,
            cd.in_progress,
            c.address,
            c.remote_link,
            c.live_classroom
        FROM course_dates cd
        JOIN courses c
        ON c.course_id = cd.course_id
        JOIN bundled_courses bc
        ON cd.course_id = bc.course_id
        WHERE bc.bundle_id = $1;
    """
    schedule = None
    bundle = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_bundle = await conn.fetch(query, bundle_id)
            found_prerequisites = await conn.fetch(
                prerequisitesQuery,
                bundle_id,
            )
            found_schedule = await conn.fetch(scheduleQuery, bundle_id)

            if found_bundle:
                schedule = []
                bundle = {
                    "courses": [],
                    "languages": [],
                    "instructionTypes": [],
                    "prerequisites": [],
                }
                for course in found_bundle:
                    course_info = {
                        "courseId": course["course_id"],
                        "courseName": course["course_name"],
                        "briefDescription": course["brief_description"],
                        "startDate": datetime.datetime.strftime(
                            convert_tz(
                                course["first_class_dtm"],
                                tz=user.timeZone if user else None,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if course["first_class_dtm"]
                        else None,
                    }
                    bundle["courses"].append(course_info)
                    for instruction_type in course["instruction_types"]:
                        if instruction_type not in bundle["instructionTypes"]:
                            bundle["instructionTypes"].append(instruction_type)

                    for lang in course["languages"]:
                        if lang not in bundle["languages"]:
                            bundle["languages"].append(lang)

                    enrollable = False
                    if (
                        course["enrollment_start_date"]
                        and course["registration_expiration_dtm"]
                        and course["active"]
                    ):
                        if (
                            course["enrollment_start_date"]
                            <= datetime.datetime.utcnow()
                            <= course["registration_expiration_dtm"]
                        ):
                            enrollable = True
                    bundle.update(
                        {
                            "bundleName": course["bundle_name"],
                            "bundleId": course["bundle_id"],
                            "bundlePicture": course["bundle_photo"],
                            "price": course["price"],
                            "active": course["active"],
                            "maxStudents": course["max_students"],
                            "isFull": course["is_full"],
                            "waitlist": course["waitlist"],
                            "waitlistLimit": course["waitlist_limit"],
                            "enrollable": enrollable,
                            "allowCash": course["allow_cash"],
                            "complete": course["is_complete"],
                            "startDate": datetime.datetime.strftime(
                                course["start_date"],
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if course["start_date"]
                            else None,
                        },
                    )

            if found_prerequisites:
                for course in found_prerequisites:
                    bundle["prerequisites"].append(
                        {
                            "courseId": course["bundle_id"],
                            "courseName": course["bundle_name"],
                            "briefDescription": course["brief_description"],
                        },
                    )
            if found_schedule:
                for event in found_schedule:
                    class_event = {
                        "courseId": event["course_id"],
                        "courseName": event["course_name"],
                        "startTime": datetime.datetime.strftime(
                            convert_tz(
                                event["start_dtm"],
                                tz=user.timeZone if user else None,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        ),
                        "endTime": datetime.datetime.strftime(
                            convert_tz(
                                event["end_dtm"],
                                tz=user.timeZone if user else None,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        ),
                        "duration": (
                            event["end_dtm"] - event["start_dtm"]
                        ).total_seconds()
                        // 60,
                        "seriesNumber": event["series_number"],
                        "complete": event["is_complete"],
                    }
                    if enrolled:
                        class_event.update(
                            {
                                "address": event["address"],
                                "remoteLink": event["remote_link"],
                            },
                        )
                    schedule.append(class_event)

    except Exception:
        log.exception("An error occured while getting a bundle")

    return (bundle, schedule)


async def get_total_course_schedule(
    user: global_models.User,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,
    complete: bool = False,
) -> list:
    """Function to get complete course schedule for all courses

    Args:
        start_date (str, optional): date to start search at. Defaults to None.
        end_date (str, optional): date to end search at. Defaults to None.

    Returns:
        list: List of classes in schedule
    """
    where_clause = ""
    schedule = []
    conditions = []
    params = [complete]
    pagination = ""
    pg = []

    if start_date:
        conditions.append(
            f"cd.start_dtm AT TIME ZONE 'UTC' AT TIME ZONE ${len(params)+1} >= ${len(params)+2}",
        )
        params.extend(
            [
                user.timeZone,
                datetime.datetime.strptime(start_date, "%m/%d/%Y"),
            ],
        )

    if end_date:
        conditions.append(
            f"cd.end_dtm AT TIME ZONE 'UTC' AT TIME ZONE ${len(params)+1} < ${len(params)+2}",
        )
        params.extend(
            [
                user.timeZone,
                (
                    datetime.datetime.strptime(end_date, "%m/%d/%Y")
                    + datetime.timedelta(days=1)
                ),
            ],
        )

    if page and pageSize:
        pagination = f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    if conditions:
        where_clause = f"AND {' AND '.join(conditions)}"

    query = f"""
        SELECT
            cd.course_id,
            c.course_name,
            cd.start_dtm,
            cd.end_dtm,
            cd.series_number,
            cd.is_complete,
            cd.in_progress,
            c.address,
            c.remote_link,
            c.languages,
            STRING_AGG(u.first_name || ' ' || u.last_name, ', ') AS instructors,
            c.live_classroom
        FROM course_dates cd
        JOIN courses c
            ON c.course_id = cd.course_id
        LEFT JOIN course_instructor ci
            ON ci.course_id = cd.course_id
        LEFT JOIN users u
            ON u.user_id = ci.user_id
        WHERE cd.is_complete = $1
        {where_clause}
        GROUP BY cd.course_id, c.course_name, cd.start_dtm, cd.end_dtm, cd.in_progress,
        cd.series_number, cd.is_complete, c.address, c.remote_link, c.languages, c.live_classroom
        ORDER BY start_dtm ASC
        {pagination};
    """

    total_count = 0
    total_pages = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *params, *pg)
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    select
                        COUNT(*)
                    FROM course_dates cd
                    WHERE cd.is_complete = $1
                    {where_clause};
                """,
                    *params,
                )
            if found:
                for event in found:
                    schedule.append(
                        {
                            "courseId": event["course_id"],
                            "courseName": event["course_name"],
                            "startTime": datetime.datetime.strftime(
                                convert_tz(
                                    event["start_dtm"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "duration": (
                                event["end_dtm"] - event["start_dtm"]
                            ).total_seconds()
                            // 60,
                            "seriesNumber": event["series_number"],
                            "complete": event["is_complete"],
                            "address": event["address"],
                            "remoteLink": event["remote_link"],
                            "instructors": event["instructors"],
                            "languages": ", ".join(event["languages"])
                            if event["languages"]
                            else None,
                        },
                    )

    except Exception:
        log.exception(
            "An error occured while getting complete course schedule",
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize
    return schedule, ceil(total_pages), total_count


async def get_content(
    course_id: str = None,
    content_id: str = None,
    published: bool = None,
    page: int = 1,
    pageSize: int = 20,
) -> Tuple[list, int, int]:
    """Get content for a course based on Id"""

    conditions = []
    params = []
    pg = []

    if isinstance(published, bool):
        i = len(params) + 1
        conditions.append(f"published = ${i}")
        params.append(published)

    if course_id:
        i = len(params) + 1
        conditions.append(f"course_id = ${i}")
        params.append(course_id)

    if content_id:
        i = len(params) + 1
        conditions.append(f"content_id = ${i}")
        params.append(content_id)

    pagination = ""
    if page and pageSize:
        pagination = f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        SELECT content_name, content_id, published
        FROM course_content
        WHERE {' and '.join(conditions)}
        ORDER BY content_name
        {pagination};
    """

    content = []
    total_count = 0
    total_pages = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *params, *pg)
            if pg:
                total_count = await conn.fetchrow(
                    f"SELECT COUNT(*) FROM course_content WHERE {' and '.join(conditions)}",
                    *params,
                )
        if found:
            for c in found:
                content.append(
                    {
                        "contentName": c["content_name"],
                        "contentId": c["content_id"],
                        "published": c["published"],
                    },
                )

    except Exception:
        log.exception("An error occured while getting course content")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return content, ceil(total_pages), total_count


async def find_class_time(course_id: str, series_number: int):
    """Function to find class time

    Args:
        course_id (str): Course Id needed to get class time from
        series_number (int): Series Number needed to get class time

    Returns:
        null: Nothing right now?
    """

    found = None
    query = """
        SELECT
            cd.is_complete,
            cd.course_id,
            cd.series_number,
            cd.start_dtm,
            cd.end_dtm,
            cd.in_progress,
            c.live_classroom,
            c.course_name,
            c.remote_link,
            c.address
        FROM course_dates AS cd
        JOIN courses c ON c.course_id = cd.course_id
        WHERE cd.course_id = $1
        AND cd.series_number = $2
    """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_class = await conn.fetchrow(query, course_id, series_number)
            if found_class:
                found = {
                    "is_complete": found_class["is_complete"],
                    "course_id": found_class["course_id"],
                    "series_number": found_class["series_number"],
                    "start_dtm": found_class["start_dtm"],
                    "end_dtm": found_class["end_dtm"],
                    "in_progress": found_class["in_progress"],
                    "live_classroom": found_class["live_classroom"],
                    "course_name": found_class["course_name"],
                    "remote_link": found_class["remote_link"],
                    "address": found_class["address"],
                }

    except Exception:
        log.exception("An error occured while getting scheduled class")

    return found


async def update_schedule(new_class: dict):
    """Function to update a schedule

    Args:
        new_class (dict): A dict including the new class being added to the schedule

    Returns:
        bool: True if updated, false if failed
    """

    query = """
        UPDATE course_dates
        SET start_dtm = $1, end_dtm = $2, in_progress = $3
        WHERE course_id = $4 AND series_number = $5;
    """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                query,
                new_class["start_dtm"].replace(tzinfo=None),
                new_class["end_dtm"].replace(tzinfo=None),
                new_class["in_progress"],
                new_class["course_id"],
                new_class["series_number"],
            )
        return True

    except Exception:
        log.exception("An error occured while getting scheduled class")

    return False


async def validate_prerequisites(course: dict, user_id: str):
    if len(course["prerequisites"]) <= 0:
        return True

    prerequisite_course_ids = [
        prerequisite["courseId"] for prerequisite in course["prerequisites"]
    ]

    query = """
    SELECT COUNT(*)
    FROM
        user_certificates
    WHERE
        user_id = $1 AND course_id IN ({})
    """.format(
        ", ".join(
            ["$" + str(i + 2) for i in range(len(prerequisite_course_ids))],
        ),
    )

    count = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            count = await conn.fetchrow(
                query,
                user_id,
                *prerequisite_course_ids,
            )

        if count and count != len(prerequisite_course_ids):
            return False

        return True

    except Exception:
        log.exception(
            "An error occured while getting the users certificates for prerequisite validation",
        )

    return False


async def set_course_picture(
    course_id: str,
    course_picture: str,
    user: global_models.User,
):
    query = """
        UPDATE courses SET
            course_picture=$1,
            modify_dtm=$2,
            modified_by=$3
        WHERE course_id=$4;
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                query,
                course_picture,
                datetime.datetime.utcnow(),
                user.userId,
                course_id,
            )
        return True

    except Exception:
        log.exception(
            f"An error occured while updating course picture for course {course_id}",
        )

    return False


async def get_course_certificate(course_id: str):
    query = """
        SELECT
            c.certificate_name,
            c.certificate_id,
            c.certificate_length,
            c.certificate_template
        FROM certificate as c
        JOIN course_certificates as cc
        ON c.certificate_id = cc.certificate_id
        WHERE cc.course_id = $1;
    """

    found = {}
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_certificate = await conn.fetchrow(query, course_id)
            if found_certificate:
                found = {
                    "certificateName": found_certificate["certificate_name"],
                    "certificateId": found_certificate["certificate_id"],
                    "certificateLength": found_certificate[
                        "certificate_length"
                    ],
                    "certificateTemplate": found_certificate[
                        "certificate_template"
                    ],
                }

    except Exception:
        log.exception(
            f"An error occured while getting certificate for course {course_id}",
        )

    return found


async def delete_content(file_ids: list, course_id: str = None) -> bool:
    query = """
        DELETE FROM course_content
        WHERE content_id in ({});
    """.format(", ".join(["$" + str(i + 1) for i in range(len(file_ids))]))

    if course_id:
        query = """
            DELETE FROM course_content
            WHERE course_id=$1 and content_id in ({});
        """.format(", ".join(["$" + str(i + 2) for i in range(len(file_ids))]))

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if course_id:
                await conn.execute(query, course_id, *file_ids)
            else:
                await conn.execute(query, *file_ids)

        for file_id in file_ids:
            filePath = f"/source/src/content/users/{file_id}"
            if os.path.exists(filePath):
                os.remove(filePath)

        return True
    except Exception:
        log.exception("An error occured while deleting course content")

    return False


async def delete_bundle(bundle_id: str) -> bool:
    queries = [
        "DELETE FROM course_bundles where bundle_id = $1;",
        "DELETE FROM prerequisites where bundle_id = $1;",
        "DELETE FROM bundled_courses where bundle_id = $1;",
    ]

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            for query in queries:
                await conn.execute(query, bundle_id)
        return True
    except Exception:
        log.exception(f"Failed to delete bundle {bundle_id}")
    return False


async def mark_class_as_complete(
    course_id: str,
    series_number: int = None,
) -> bool:
    query = """
        UPDATE
            course_dates
        SET
            is_complete=$1,
            in_progress=FALSE
        WHERE
            course_id=$2;
    """

    if series_number:
        query = """
            UPDATE
                course_dates
            SET
                is_complete=$1,
                in_progress=FALSE
            WHERE
                course_id=$2 and series_number=$3;
        """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if series_number:
                await conn.execute(query, True, course_id, series_number)
            else:
                await conn.execute(query, True, course_id)

        return True

    except Exception:
        log.exception(
            f"Failed to mark course classes for {course_id} as complete",
        )

    return False


async def mark_course_as_complete(course_id: str) -> bool:
    query = """
        UPDATE
            courses
        SET
            is_complete=$1
        WHERE
            course_id=$2;
    """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, True, course_id)

        return True

    except Exception:
        log.exception(f"Failed to mark course {course_id} as complete")

    return False


async def mark_bundle_as_complete(bundle_id: str) -> bool:
    query = """
        UPDATE
            course_bundles
        SET
            is_complete=$1
        WHERE
            bundle_id=$2;
    """
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, True, bundle_id)

        return True

    except Exception:
        log.exception(f"Failed to mark bundle {bundle_id} as complete")

    return False


async def get_scheduled_class(
    course_id: str,
    series_number: int,
    user: global_models.User,
    show_details: bool = False,
) -> dict:
    query = """
        SELECT
            cd.is_complete,
            cd.series_number,
            cd.start_dtm,
            cd.end_dtm,
            c.course_name,
            c.remote_link,
            c.address,
            cd.in_progress,
            c.live_classroom
        FROM course_dates cd
        JOIN courses c on c.course_id = cd.course_id
        WHERE cd.course_id = $1 and cd.series_number = $2;
    """

    instructor_query = """
        SELECT
            u.user_id,
            u.first_name,
            u.last_name
        FROM users u
        LEFT JOIN
            course_instructor ci on u.user_id = ci.user_id
        WHERE ci.course_id = $1;
    """
    formatted_class = None
    found_class = None
    found_instructors = None
    signed_in = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_class = await conn.fetchrow(query, course_id, series_number)
            found_instructors = await conn.fetch(instructor_query, course_id)
            if show_details:
                signed_in = await conn.fetchrow(
                    """
                        SELECT
                            sign_in,
                            "absent" as absent
                        FROM class_details
                        WHERE
                            user_id = $1
                            AND course_id = $2
                            AND series_number = $3;
                    """,
                    user.userId,
                    course_id,
                    series_number,
                )
        if found_class:
            can_start = False
            if (
                not found_class["is_complete"]
                and found_class["start_dtm"]
                and not found_class["in_progress"]
                and found_class["live_classroom"]
            ):
                can_start = True

            formatted_class = {
                "courseId": course_id,
                "courseName": found_class["course_name"],
                "complete": found_class["is_complete"],
                "seriesNumber": found_class["series_number"],
                "startTime": datetime.datetime.strftime(
                    convert_tz(
                        found_class["start_dtm"],
                        tz=user.timeZone,
                    ),
                    "%m/%d/%Y %-I:%M %p",
                ),
                "endTime": datetime.datetime.strftime(
                    convert_tz(
                        found_class["end_dtm"],
                        tz=user.timeZone,
                    ),
                    "%m/%d/%Y %-I:%M %p",
                ),
                "duration": (
                    found_class["end_dtm"] - found_class["start_dtm"]
                ).total_seconds()
                // 60,
                "instructors": [],
            }
            if show_details:
                formatted_class.update(
                    {
                        "remoteLink": found_class["remote_link"],
                        "address": found_class["address"],
                        "canStart": can_start,
                        "signedIn": signed_in["sign_in"]
                        if signed_in
                        else False,
                        "absent": signed_in["absent"] if signed_in else False,
                    },
                )

            if found_instructors:
                for instructor in found_instructors:
                    formatted_class["instructors"].append(
                        {
                            "userId": instructor["user_id"],
                            "firstName": instructor["first_name"],
                            "lastName": instructor["last_name"],
                        },
                    )

    except Exception:
        log.exception("Failed to get scheduled class details")

    return formatted_class


async def delete_class(course_id: str, series_number: int) -> bool:
    query = """
        DELETE FROM course_dates WHERE course_id = $1 and series_number = $2;
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, course_id, series_number)

        return True
    except Exception:
        log.exception("Failed to delete class")

    return False


async def search_schedule(
    user: global_models.User,
    course_name: Optional[str] = None,
    bundle_name: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,
) -> list:
    schedule = []
    params = []
    query = None
    pagination = ""
    if page and pageSize:
        pagination = f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        params.extend([pageSize, (page - 1) * pageSize])

    if course_name:
        query = f"""
            SELECT
                cd.course_id,
                c.course_name,
                cd.start_dtm,
                cd.end_dtm,
                cd.series_number,
                cd.is_complete,
                cd.in_progress,
                c.live_classroom
            FROM course_dates cd
            JOIN courses c
            on c.course_id = cd.course_id
            WHERE UPPER(c.course_name) like UPPER(${len(params) + 1})
            ORDER BY start_dtm ASC
            {pagination};
        """
        params.append(f"%{course_name}%")

    if bundle_name:
        query = f"""
            SELECT
                c.course_id,
                c.course_name,
                cd.start_dtm,
                cd.end_dtm,
                cd.series_number,
                cd.is_complete,
                cd.in_progress,
                c.live_classroom
            FROM course_bundles b
            JOIN
                bundled_courses bc on bc.bundle_id = b.bundle_id
            JOIN
                courses c  on c.course_id = bc.course_id
            JOIN
                course_dates cd on cd.course_id = c.course_id
            WHERE UPPER(b.bundle_name) like UPPER(${len(params) + 1})
            ORDER BY start_dtm ASC
            {pagination};
        """
        params.append(f"%{bundle_name}%")

    total_count = 0
    total_pages = 0
    found = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *params)
            if page and pageSize:
                if course_name:
                    total_count = await conn.fetchrow(
                        """
                        SELECT
                            COUNT(*)
                        FROM course_dates cd
                        JOIN courses c
                        on c.course_id = cd.course_id
                        WHERE c.course_name like $1;
                    """,
                        course_name,
                    )
                if bundle_name:
                    total_count = await conn.fetchrow(
                        """
                        SELECT
                            COUNT(*)
                        FROM course_bundles b
                        JOIN
                            bundled_courses bc on bc.bundle_id = b.bundle_id
                        JOIN
                            courses c  on c.course_id = bc.course_id
                        JOIN
                            course_dates cd on cd.course_id = c.course_id
                        WHERE b.bundle_name like $1;
                    """,
                        bundle_name,
                    )
        if found:
            for event in found:
                schedule.append(
                    {
                        "courseId": event["course_id"],
                        "courseName": event["course_name"],
                        "startTime": convert_tz(
                            event["start_dtm"],
                            tz=user.timeZone,
                        ).strftime("%m/%d/%Y %-I:%M %p"),
                        "duration": (
                            event["end_dtm"] - event["start_dtm"]
                        ).total_seconds()
                        // 60,
                        "seriesNumber": event["series_number"],
                        "complete": event["is_complete"],
                    },
                )

    except Exception:
        log.exception(
            f"An error occured while getting {'course' if course_name else 'bundle'} schedule",
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize
    return schedule, ceil(total_pages), total_count


async def list_courses_and_bundles(
    user: global_models.User,
    page: int = 1,
    pageSize: int = 20,
    complete: Optional[bool] = False,
    inactive: Optional[bool] = False,
) -> list:
    formatted = []
    where_condition = []

    if complete:
        where_condition.append("is_complete = TRUE")

    if inactive:
        where_condition.append("active = TRUE")

    where_clause = ""
    if where_condition:
        where_clause = f"WHERE {' AND '.join(where_condition)}"
    pg = []
    pagination = ""
    if page and pageSize:
        pagination = "LIMIT $1 OFFSET $2"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        WITH course_data AS (
            SELECT
                DISTINCT
                c.course_id AS id,
                c.course_name AS name,
                'course' AS type,
                c.first_class_dtm AS start_dtm,
                c.classes_in_series AS total_classes,
                c.course_picture,
                c.brief_description,
                c.active AS active,
                c.is_complete AS is_complete,
                c.live_classroom
            FROM courses c
            UNION ALL
            SELECT
                DISTINCT
                cb.bundle_id AS id,
                cb.bundle_name AS name,
                'bundle' AS type,
                MIN(cd.start_dtm) AS start_dtm,
                COUNT(cd.start_dtm) AS total_classes,
                NULL AS course_picture,
                NULL AS brief_description,
                cb.active AS active,
                cb.is_complete AS is_complete,
                FALSE AS live_classroom
            FROM course_bundles cb
            JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
            JOIN course_dates cd ON bc.course_id = cd.course_id
            GROUP BY cb.bundle_id, cb.bundle_name, cb.active, cb.is_complete
        )
        SELECT * FROM course_data {where_clause} ORDER BY start_dtm DESC
        {pagination};
    """

    found = None
    total_count = 0
    total_pages = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *pg)
            if page and pageSize:
                total_count = await conn.fetchrow(f"""
                    WITH course_data AS (
                        SELECT
                            DISTINCT
                            c.course_id AS id,
                            c.course_name AS name,
                            'course' AS type,
                            c.first_class_dtm AS start_dtm,
                            c.classes_in_series AS total_classes,
                            c.course_picture,
                            c.brief_description,
                            c.active AS active,
                            c.is_complete AS is_complete,
                            c.live_classroom
                        FROM courses c
                        UNION ALL
                        SELECT
                            DISTINCT
                            cb.bundle_id AS id,
                            cb.bundle_name AS name,
                            'bundle' AS type,
                            MIN(cd.start_dtm) AS start_dtm,
                            COUNT(cd.start_dtm) AS total_classes,
                            NULL AS course_picture,
                            NULL AS brief_description,
                            cb.active AS active,
                            cb.is_complete AS is_complete,
                            FALSE AS live_classroom
                        FROM course_bundles cb
                        JOIN bundled_courses bc ON cb.bundle_id = bc.bundle_id
                        JOIN course_dates cd ON bc.course_id = cd.course_id
                        GROUP BY cb.bundle_id, cb.bundle_name, cb.active, cb.is_complete
                    )
                    SELECT COUNT(*) FROM course_data {where_clause};
                """)
        if found:
            for course_bundle in found:
                formatted.append(
                    {
                        "id": course_bundle["id"],
                        "picture": course_bundle["course_picture"],
                        "name": course_bundle["name"],
                        "type": course_bundle["type"],
                        "startDate": datetime.datetime.strftime(
                            convert_tz(
                                course_bundle["start_dtm"],
                                tz=user.timeZone,
                            ),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if course_bundle["start_dtm"]
                        else None,
                        "totalClasses": course_bundle["total_classes"],
                        "active": course_bundle["active"],
                        "complete": course_bundle["is_complete"],
                        "briefDescription": course_bundle["brief_description"],
                    },
                )

    except Exception:
        log.exception("An error occured while getting all bundles and courses")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize
    return formatted, ceil(total_pages), total_count
