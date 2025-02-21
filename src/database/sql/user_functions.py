import datetime
import math
import os
import traceback
import uuid
from fractions import Fraction
from math import ceil
from typing import List, Optional, Tuple, Union

import asyncpg
from passlib.hash import pbkdf2_sha256

from src.api.api_models import global_models
from src.api.api_models.users import lookup, my_certifications
from src.database.sql import acquire_connection, get_connection
from src.utils.convert_date import convert_tz
from src.utils.generate_random_code import generate_random_code
from src.utils.log_handler import log


async def get_user(
    user_id: Optional[str] = None,
    email: Optional[str] = None,
    phoneNumber: Optional[str] = None,  # noqa: N803
) -> Union[global_models.User, None]:
    """Function to get a user from postgres database

    Args:
        user_id (str, optional): user_id of the user being looked up.
        Defaults to None.
        email (str, optional): email of the user being looked up.
        Defaults to None.
        phoneNumber (str, optional): phone number of the user being looked up.
        Defaults to None.

    Returns:
        Union[global_models.User, None]: Returns user model or none if nothing
        is found
    """
    params = []
    where_conditions = []
    query = None
    formatted_user = None

    if user_id:
        where_conditions.append(f"user_id = ${len(params)+1}")
        params.append(user_id)

    if email:
        where_conditions.append(f"email = ${len(params)+1}")
        params.append(email)

    if phoneNumber:
        where_conditions.append(f"phone_number = ${len(params)+1}")
        params.append(phoneNumber)

    where_statement = ""
    if where_conditions:
        where_statement = f"WHERE {' AND '.join(where_conditions)}"

    query = f"""
        select
            user_id,
            first_name,
            middle_name,
            last_name,
            suffix,
            email,
            phone_number,
            dob,
            password,
            time_zone,
            head_shot,
            address,
            city,
            state,
            zipcode,
            eye_color,
            height,
            gender,
            photo_id,
            other_id,
            photo_id_photo,
            other_id_photo,
            active,
            text_notif,
            email_notif,
            expiration_date
        from users
        {where_statement};
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            user = await conn.fetchrow(query, *params)
            if user:
                formatted_user = global_models.User(
                    userId=user["user_id"],
                    firstName=user["first_name"],
                    middleName=user["middle_name"],
                    lastName=user["last_name"],
                    suffix=user["suffix"],
                    email=user["email"],
                    phoneNumber=user["phone_number"],
                    eyeColor=user["eye_color"],
                    height={
                        "feet": int(user["height"] // 12),
                        "inches": math.floor(
                            Fraction(round(user["height"] % 12 * 100), 100),
                        ),
                    }
                    if user["height"]
                    else None,  # type: ignore
                    gender=user["gender"],
                    headShot=user["head_shot"],
                    photoId=user["photo_id"],
                    otherId=user["other_id"],
                    photoIdPhoto=user["photo_id_photo"],
                    otherIdPhoto=user["other_id_photo"],
                    password=user["password"],
                    timeZone=user["time_zone"],
                    active=user["active"],
                    textNotifications=user["text_notif"],
                    emailNotifications=user["email_notif"],
                    address=user["address"],
                    city=user["city"],
                    state=user["state"],
                    zipcode=user["zipcode"],
                )
                if user["dob"]:
                    formatted_user.dob = datetime.datetime.strftime(
                        user["dob"],
                        "%m/%d/%Y",
                    )
                if user["expiration_date"]:
                    formatted_user.expirationDate = datetime.datetime.strftime(
                        user["expiration_date"],
                        "%m/%d/%Y",
                    )

    except Exception:
        log.exception(
            f"An error occured while getting the user with identifiers {params}",  # noqa: E501
        )

    return formatted_user


async def create_user(**kwargs) -> Union[bool, str]:  # noqa: ANN003
    """Function to create a user
    Args:
        kwargs dict: parameters to use to create user.
    Returns:
        bool: Returns true or false based off of whether user was able to be
        created or not
    """
    columns = []
    insert_values = []
    for key, value in kwargs["newUser"].items():
        columns.append(key)
        insert_values.append(value)

    query = """
        INSERT INTO users ({})
        VALUES ({});
    """.format(
        ", ".join(columns),
        ", ".join(["$" + str(i + 1) for i in range(len(insert_values))]),
    )

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, *insert_values)
        return True

    except asyncpg.exceptions.UniqueViolationError as err:
        key = (
            err.args[0]
            .split('duplicate key value violates unique constraint "')[1]
            .split('"')[0]
        )
        if key == "users_email_key":
            return "Email already exists in LMS"

        if key == "users_phone_number_key":
            return "Phone number already exist in LMS"

        return "User already exists in LMS"

    except Exception:
        log.exception(
            f"An error occured while creating the user with id {kwargs['newUser']['user_id']}",  # noqa: E501
        )

    return False


async def update_user(user_id: str, **kwargs) -> bool:  # noqa: ANN003
    """Function to update a user

    Args:
        email (str): email of the user being updated.
        kwargs dict: parameters to use to update user.

    Returns:
        bool: Returns True or False if user is updated.
    """

    elements = []
    for idx, key in enumerate(kwargs):
        elements.append(f"{key} = ${str(idx+2)}")

    query = "UPDATE users SET {} WHERE user_id = $1".format(
        ", ".join(elements),
    )

    values = [user_id] + list(kwargs.values())
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, *values)

        return True

    except Exception:
        log.exception("An error occured while updating user")

    return False


async def get_user_type(
    user: lookup.Input,
    roleName: Optional[str] = None,  # noqa: N803
    condition: str = "AND",
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> Tuple[List[dict], int, int]:
    """Function to find student by lookup

    Args:
        user (lookup.Input): Parameters to look up a user with
        roleName (str, optional): Role Name to do the look up with.
        Defaults to None.
        condition (str, optional): Condition to do and join or OR join.
        Defaults to "AND".
        page (int, optional): Page number for pagination. Defaults to None.
        pageSize (int, optional): Page size for pagination. Defaults to None.

    Returns:
        Union[List[dict], None]: Either returns a list of users or none.
    """

    users = []
    where_conditions = []
    values = []
    pg = []

    if roleName and not roleName == "all":
        where_conditions.append(f"r.role_name = ${len(where_conditions)+1}")
        values.append(roleName)

    if user.firstName:
        where_conditions.append(
            f"UPPER(u.first_name) LIKE UPPER(${len(where_conditions)+1})",
        )
        values.append(f"%{user.firstName}%")
    if user.lastName:
        where_conditions.append(
            f"UPPER(u.last_name) LIKE UPPER(${len(where_conditions)+1})",
        )
        values.append(f"%{user.lastName}%")
    if user._id:
        where_conditions.append(
            f"UPPER(u.other_id) LIKE UPPER(${len(where_conditions)+1})",
        )
        values.append(f"%{user._id}%")

    if user.phoneNumber:
        where_conditions.append(
            f"u.phone_number LIKE ${len(where_conditions)+1}",
        )
        values.append(f"%{user.phoneNumber}%")

    if user.email:
        where_conditions.append(
            f"UPPER(u.email) LIKE LIKE(${len(where_conditions)+1})",
        )
        values.append(f"%{user.email}%")

    # # Add conditions for instructor's first name and last name
    # if user.instructorFirstName:
    #     where_conditions.append(
    #         f"UPPER(ui.first_name) LIKE UPPER(${len(where_conditions)+1})")
    #     values.append(f"%{user.instructorFirstName}%")

    # if user.instructorLastName:
    #     where_conditions.append(
    #         f"UPPER(ui.last_name) LIKE UPPER(${len(where_conditions)+1})")
    #     values.append(f"%{user.instructorLastName}%")

    # # Add condition for course name
    # if user.courseName:
    #     where_conditions.append(
    #         f"UPPER(c.course_name) LIKE UPPER(${len(where_conditions)+1})")
    #     values.append(f"%{user.courseName}%")

    # # Add condition for first class date
    # if user.startTime:
    #     start_time = datetime.datetime.strptime(
    #         user.startTime, "%m/%d/%Y %I:%M %p")
    #     where_conditions.append(
    #         f"c.first_class_dtm AT TIME ZONE 'UTC' AT TIME ZONE ${len(where_conditions)+1} = ${len(where_conditions)+2}"  # noqa: E501
    #     )
    #     values.extend([
    #         user.timeZone if request_user else 'EST',
    #         start_time
    #     ])

    pagination = ""
    if page and pageSize:
        pagination = f"LIMIT ${len(values) + 1} OFFSET ${len(values) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        SELECT DISTINCT
            u.head_shot,
            u.user_id,
            u.first_name,
            u.last_name,
            u.email,
            u.phone_number,
            u.dob
        FROM users u
        JOIN user_role ur ON u.user_id = ur.user_id
        JOIN roles r ON ur.role_id = r.role_id
        LEFT JOIN course_registration cr ON cr.user_id = u.user_id
        LEFT JOIN course_instructor ci ON ci.course_id = cr.course_id
        LEFT JOIN users ui ON ui.user_id = ci.user_id
        LEFT JOIN courses c ON c.course_id = cr.course_id
        WHERE {f" {condition} ".join(where_conditions)}
        ORDER BY u.last_name
        {pagination};
    """

    total_pages = 0
    total_count = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(DISTINCT u.user_id)
                    FROM users u
                    JOIN user_role ur ON u.user_id = ur.user_id
                    JOIN roles r ON ur.role_id = r.role_id
                    LEFT JOIN course_registration cr ON cr.user_id = u.user_id
                    LEFT JOIN course_instructor ci ON ci.course_id = cr.course_id
                    LEFT JOIN users ui ON ui.user_id = ci.user_id
                    LEFT JOIN courses c ON c.course_id = cr.course_id
                    WHERE {f" {condition} ".join(where_conditions)};
                """,  # noqa: E501
                    *values,
                )
            found = await conn.fetch(query, *values, *pg)

            if found:
                for user in found:
                    if not user:
                        continue
                    users.append(
                        {
                            "headShot": user["head_shot"],  # type: ignore
                            "userId": user["user_id"],  # type: ignore
                            "firstName": user["first_name"],  # type: ignore
                            "lastName": user["last_name"],  # type: ignore
                            "email": user["email"],  # type: ignore
                            "phoneNumber": user["phone_number"],  # type: ignore
                            "dob": datetime.datetime.strftime(
                                user["dob"],  # type: ignore
                                "%m/%d/%Y",
                            )
                            if user["dob"]  # type: ignore
                            else None,
                        },
                    )

    except Exception:
        log.exception("An error occured while getting all users by lookup")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return users, ceil(total_pages), total_count


async def get_users_for_export(
    userIds: Optional[List[str]] = None,  # noqa: N803
    role: str = "student",
) -> Union[list, None]:
    """Function to get students for export

    Args:
        userIds (List[str], optional): List of student Ids. Defaults to None.
        role (str): Role of user exports. Defaults to student.
    Returns:
        Union[list, None]: A list of users belonging to whichever role
    """
    users = []
    if not userIds:
        return None

    roles = []
    role_start_index = len(userIds) + 1
    if role == "all":
        roles.extend(["student", "admin", "instructor"])
    else:
        roles = [role]

    query = f"""
        SELECT
            u.user_id,
            u.first_name,
            u.middle_name,
            u.last_name,
            u.suffix,
            u.email,
            u.phone_number,
            u.dob,
            u.eye_color,
            u.height,
            u.photo_id,
            u.other_id,
            u.time_zone,
            u.active,
            u.expiration_date,
            u.text_notif,
            u.email_notif,
            u.address,
            u.city,
            u.state,
            u.zipcode,
            u.gender,
            r.role_name
        FROM users u
        JOIN user_role ur
        ON ur.user_id = u.user_id
        JOIN roles r
        ON ur.role_id = r.role_id
        WHERE u.user_id IN ({', '.join(['$' + str(i + 1) for i in range(len(userIds))])})
        AND r.role_name IN ({', '.join(['$' + str(i + role_start_index) for i in range(len(roles))])});
    """  # noqa: E501

    found = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *userIds, *roles)
        if found:
            for user in found:
                users.append(
                    {
                        "user_id": user["user_id"],
                        "first_name": user["first_name"],
                        "middle_name": user["middle_name"],
                        "last_name": user["last_name"],
                        "suffix": user["suffix"],
                        "email": user["email"],
                        "phone_number": user["phone_number"],
                        "dob": datetime.datetime.strftime(
                            user["dob"],
                            "%m/%d/%Y",
                        )
                        if user["dob"]
                        else None,
                        "eye_color": user["eye_color"],
                        "height": (
                            f"feet {int(user['height'] // 12)} inches {math.floor(Fraction(round(user['height'] % 12 * 100), 100))}"  # noqa: E501
                            if user["height"]
                            else None
                        ),
                        "photo_id": user["photo_id"],
                        "other_id": user["other_id"],
                        "time_zone": user["time_zone"],
                        "active": user["active"],
                        "expiration_date": (
                            datetime.datetime.strftime(
                                user["expiration_date"],
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if user["expiration_date"]
                            else None
                        ),
                        "text_notif": user["text_notif"],
                        "email_notif": user["email_notif"],
                        "address": user["address"],
                        "city": user["city"],
                        "state": user["state"],
                        "zipcode": user["zipcode"],
                        "gender": user["gender"],
                        "role": user["role_name"],
                    },
                )

    except Exception:
        log.exception(
            f"An error occured while getting all users for export using {userIds}",  # noqa: E501
        )

    return users


async def get_certificates_for_export(
    certificate_numbers: Optional[List[str]] = None,
) -> Union[list, None]:
    """Function to get certificates for export

    Args:
        certificate_numbers (List[str], optional): List of certificate_numbers.
        Defaults to None.

    Returns:
        Union[list, None]: A list of certificate_numbers belonging to whichever
        certificates
    """
    certificates = []
    if not certificate_numbers:
        return None

    query = """
        SELECT
            u.user_id,
            u.first_name,
            u.last_name,
            u.phone_number,
            u.email,
            u.dob,
            uc.completion_date,
            uc.expiration_date,
            uc.certificate_name,
            uc.certificate_number,
            c.course_name,
            c.course_code
        FROM user_certificates uc
        JOIN
            users u on u.user_id = uc.user_id
        LEFT JOIN
            courses c on c.course_id = uc.course_id
        WHERE uc.certificate_number IN ({});
    """.format(
        ", ".join(["$" + str(i + 1) for i in range(len(certificate_numbers))]),
    )

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *certificate_numbers)
            if found:
                for certificate in found:
                    certificate_name = certificate.get("certificate_name")
                    if not certificate_name:
                        certificate_name = ""
                        if certificate["course_code"]:
                            certificate_name += (
                                f"{certificate['course_code']} "
                            )
                        if certificate["course_name"]:
                            certificate_name += certificate["course_name"]

                    certificates.append(
                        {
                            "user_id": certificate["user_id"],
                            "first_name": certificate["first_name"],
                            "last_name": certificate["last_name"],
                            "email": certificate["email"],
                            "phone_number": certificate["phone_number"],
                            "dob": datetime.datetime.strftime(
                                certificate["dob"],
                                "%m/%d/%Y",
                            )
                            if certificate["dob"]
                            else None,
                            "completion_date": datetime.datetime.strftime(
                                certificate["completion_date"],
                                "%m/%d/%Y %-I:%M %p",
                            ),
                            "expiration_date": (
                                datetime.datetime.strftime(
                                    certificate["expiration_date"],
                                    "%m/%d/%Y %-I:%M %p",
                                )
                                if certificate["expiration_date"]
                                else None
                            ),
                            "certificate_name": certificate_name,
                            "certificate_number": certificate[
                                "certificate_number"
                            ],
                        },
                    )

    except Exception:
        log.exception(
            f"An error occured while getting all certificates for export using {certificate_numbers}",  # noqa: E501
        )

    return certificates


async def get_user_class(
    role: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> Tuple[list, int, int]:
    """Function to get all users by a specific role type

    Args:
        role (str, optional): Role to look up. Defaults to None.
        page (int, optional): Page number for pagination. Defaults to None.
        pageSize (int, optional): Page size for pagination. Defaults to None.
    Returns:
        Union[list, None]: List of users or none.
    """
    users = []
    if not role:
        return users, 0, 0

    roles = []
    if role == "all":
        roles.extend(["student", "admin", "instructor"])
    else:
        roles = [role]

    pagination = ""
    pg = []

    if page and pageSize:
        pagination = f"LIMIT ${len(roles) + 1} OFFSET ${len(roles) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        SELECT
            DISTINCT
            u.head_shot,
            u.user_id,
            u.first_name,
            u.last_name,
            u.email,
            u.phone_number,
            u.dob
        FROM users AS u
        JOIN user_role AS ur ON u.user_id = ur.user_id
        JOIN roles AS r ON ur.role_id = r.role_id
        WHERE r.role_name IN ({', '.join(['$' + str(i + 1) for i in range(len(roles))])})
        ORDER BY u.last_name
        {pagination};
    """  # noqa: E501

    total_pages = 0
    total_count = 0
    found = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, *roles, *pg)
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(DISTINCT u.user_id)
                    FROM users AS u
                    JOIN user_role AS ur ON u.user_id = ur.user_id
                    JOIN roles as r ON ur.role_id = r.role_id
                    WHERE r.role_name IN ({', '.join(['$' + str(i + 1) for i in range(len(roles))])})
                """,  # noqa: E501
                    *roles,
                )

        if found:
            for user in found:
                users.append(
                    {
                        "headShot": user["head_shot"],
                        "userId": user["user_id"],
                        "firstName": user["first_name"],
                        "lastName": user["last_name"],
                        "email": user["email"],
                        "phoneNumber": user["phone_number"],
                        "dob": datetime.datetime.strftime(
                            user["dob"],
                            "%m/%d/%Y",
                        )
                        if user["dob"]
                        else None,
                    },
                )

    except Exception:
        log.exception(
            f"An error occured while getting the users with role {role}",
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return users, ceil(total_pages), total_count


async def get_roles(
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> Tuple[List[dict], int, int]:
    """Function to get roles

    Args:
        page (int, optional): Page number for pagination. Defaults to None.
        pageSize (int, optional): Page size for pagination. Defaults to None.
    Returns:
        Union[List[Role], list]: returns list of roles or empty list.
    """
    query = None
    params = []
    query = """
        select
            role_id,
            role_name,
            role_desc
        from roles WHERE active = TRUE order by role_name;
    """
    if page and pageSize:
        query = """
            select 
                role_id,
                role_name,
                role_desc 
            from roles 
            WHERE active = TRUE order by role_name LIMIT $1 OFFSET $2;
        """
        params.extend([pageSize, (page - 1) * pageSize])

    total_pages = 0
    total_count = 0
    roles = []
    found_roles = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if page and pageSize:
                total_count = await conn.fetchrow(
                    "SELECT COUNT(*) FROM roles WHERE active = TRUE;",
                )
            found_roles = await conn.fetch(query, *params)
        if found_roles:
            for role in found_roles:
                roles.append(
                    {
                        "roleId": role["role_id"],
                        "roleName": role["role_name"],
                        "description": role["role_desc"],
                    },
                )

    except Exception:
        log.exception("An error occured while getting role list")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return roles, ceil(total_pages), total_count


async def get_course_bundle_students(
    course_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> Tuple[List[dict], int, int]:
    """Function to get a courses students

    Args:
        course_id (str, optional): course id of the course looked up.
        Defaults to None.
        bundle_id (str, optional): bundle id of the bundle being looked up.
        Defaults to None

    Returns:
        list: courseor bundle students
    """
    students = []
    pagination = ""
    pg = []

    if page and pageSize:
        pagination = f"LIMIT ${len(pg) + 2} OFFSET ${len(pg) + 3}"
        pg.extend([pageSize, (page - 1) * pageSize])

    if course_id:
        value = course_id
        query = f"""
            SELECT DISTINCT
                stu.head_shot,
                stu.user_id,
                stu.first_name,
                stu.last_name,
                stu.phone_number,
                stu.email,
                stu.dob,
                cr.user_paid,
                cr.using_cash,
                cr.registration_status,
                cr.notes,
                t.transaction_id,
                CASE
                    WHEN uc.user_id IS NOT NULL THEN TRUE
                    ELSE FALSE
                END AS certificate,
                (
                    SELECT ARRAY_AGG(ROW(
                        fs.form_id,
                        f.form_name,
                        fs.passing,
                        fs.score
                    ))
                    FROM form_submissions fs
                    JOIN course_forms cf ON cf.form_id = fs.form_id
                    JOIN forms f ON f.form_id = cf.form_id
                    WHERE fs.user_id = stu.user_id 
                    AND cf.course_id = cr.course_id AND f.form_type = 'quiz'
                ) as quizzes,
                (
                    SELECT COUNT(*)
                    FROM course_forms cf
                    JOIN forms f on f.form_id = cf.form_id
                    WHERE cf.course_id = cr.course_id and f.form_type = 'quiz'
                ) as total_quizzes,
                (
                    SELECT ARRAY_AGG(ROW(
                        fs.form_id,
                        f.form_name
                    ))
                    FROM form_submissions fs
                    JOIN
                        course_forms cf ON cf.course_id = cr.course_id
                    JOIN
                        forms f on f.form_id = cf.form_id
                    WHERE fs.user_id = stu.user_id 
                    and cf.course_id = cr.course_id and f.form_type = 'survey'
                ) as surveys,
                (
                    SELECT COUNT(*)
                    FROM course_forms cf
                    JOIN forms f on f.form_id = cf.form_id
                    WHERE cf.course_id = cr.course_id 
                    and f.form_type = 'survey'
                ) as total_surveys
            FROM users AS stu
            JOIN course_registration AS cr ON stu.user_id = cr.user_id
            LEFT JOIN user_certificates AS uc ON uc.user_id = stu.user_id 
            AND uc.course_id = cr.course_id
            LEFT JOIN
                transactions t on t.course_id = cr.course_id 
                and t.user_id = cr.user_id
            WHERE cr.course_id = $1
            GROUP by
                cr.course_id,
                uc.user_id,
                stu.user_id,
                cr.registration_status,
                cr.user_paid,
                cr.using_cash,
                uc.course_id,
                cr.notes,
                t.transaction_id
            {pagination};
        """

    if bundle_id:
        value = bundle_id
        query = f"""
            SELECT DISTINCT
                stu.head_shot,
                stu.user_id,
                stu.first_name,
                stu.last_name,
                stu.phone_number,
                stu.email,
                stu.dob,
                cr.user_paid,
                cr.using_cash,
                cr.registration_status,
                cr.notes,
                t.transaction_id
            FROM bundled_courses AS bc
            JOIN
                course_registration AS cr ON cr.course_id = bc.course_id
            JOIN
                users as stu ON stu.user_id = cr.user_id
            LEFT JOIN
                transactions t on t.bundle_id = bc.bundle_id 
                and t.user_id = stu.user_id
            WHERE bc.bundle_id = $1
            {pagination};
        """
    found_students = None
    total_count = 0
    total_pages = 0
    user_ids = []
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_students = await conn.fetch(query, value, *pg)
            if page and pageSize:
                if bundle_id:
                    total_count = await conn.fetchrow(
                        """
                        SELECT COUNT(DISTINCT stu.user_id)
                        FROM bundled_courses AS bc
                        JOIN
                            course_registration AS cr ON cr.course_id = bc.course_id
                        JOIN
                            users as stu ON stu.user_id = cr.user_id
                        LEFT JOIN
                            transactions t on t.bundle_id = bc.bundle_id and t.user_id = stu.user_id
                        WHERE bc.bundle_id = $1;
                    """,  # noqa: E501
                        value,
                    )
                if course_id:
                    total_count = await conn.fetchrow(
                        """
                        SELECT COUNT(DISTINCT stu.user_id)
                        FROM users AS stu
                        JOIN course_registration AS cr ON stu.user_id = cr.user_id
                        LEFT JOIN user_certificates AS uc ON uc.user_id = stu.user_id AND uc.course_id = cr.course_id
                        LEFT JOIN
                            transactions t on t.course_id = cr.course_id and t.user_id = cr.user_id
                        WHERE cr.course_id = $1;
                    """,  # noqa: E501
                        value,
                    )
        if found_students:
            for student in found_students:
                if student["user_id"] in user_ids:
                    continue
                user_ids.append(student["user_id"])
                formatted_student = {
                    "userId": student["user_id"],
                    "headShot": student["head_shot"],
                    "firstName": student["first_name"],
                    "lastName": student["last_name"],
                    "phoneNumber": student["phone_number"],
                    "email": student["email"],
                    "dob": datetime.datetime.strftime(
                        student["dob"],
                        "%m/%d/%Y",
                    )
                    if student["dob"]
                    else None,
                    "paid": student["user_paid"],
                    "usingCash": student["using_cash"],
                    "registrationStatus": student["registration_status"],
                    "notes": student["notes"],
                    "transaction": student["transaction_id"],
                }
                if course_id:
                    formatted_student.update(
                        {
                            "certificate": student["certificate"],
                            "quizzes": {
                                "taken": len(student["quizzes"])
                                if student["quizzes"]
                                else 0,
                                "total": student["total_quizzes"],
                                "records": [
                                    {
                                        "quizId": quiz[0],
                                        "quizName": quiz[1],
                                        "passed": quiz[2],
                                        "score": quiz[3],
                                    }
                                    for quiz in student["quizzes"]
                                ]
                                if student["quizzes"]
                                else [],
                            },
                            "surveys": {
                                "taken": len(student["surveys"])
                                if student["surveys"]
                                else 0,
                                "total": student["total_surveys"],
                                "records": [
                                    {
                                        "surveyId": survey[0],
                                        "surveyName": survey[1],
                                    }
                                    for survey in student["surveys"]
                                ]
                                if student["surveys"]
                                else [],
                            },
                            # TODO: update this once signin is implemented
                            "signInSheet": {
                                "amount": 0,
                                "total": 0,
                                "records": [
                                    {
                                        # str[other, present, absent],
                                        "status": "present",
                                        "comments": "",
                                        "seriesNumber": 0,
                                    },
                                ],
                            },
                        },
                    )
                students.append(formatted_student)

    except Exception:
        log.exception(
            f"An error occured while getting students for course_id {course_id}",  # noqa: E501
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return students, ceil(total_pages), total_count


async def manage_user_roles(
    roles: list,
    user_id: str,
    action: str = "add",
) -> bool:
    """Function to manage a users roles

    Args:
        roles (list): list of roles to add/remove.
        user_id (str): user id of the user editing.
        action (str, optional): action to add or remove roles.
        Defaults to "add".

    Returns:
        bool: Bool for either successful or unsuccessful update
    """
    if not roles or not user_id:
        return False

    if action not in ("add", "remove"):
        raise ValueError("Invalid action specified. Use 'add' or 'remove'.")

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            for role in roles:
                role_id = await get_role_id(role_name=role)
                if action == "add":
                    query = """
                        INSERT INTO user_role
                        (user_id, role_id)
                        VALUES ($1, $2);
                    """
                elif action == "remove":
                    query = """
                        DELETE FROM user_role
                        WHERE user_id = $1
                        AND role_id = $2;
                    """
                else:
                    raise ValueError("Invalid action specified")

                await conn.execute(query, user_id, role_id)

        return True

    except Exception:
        log.exception(
            f"An error occured while assigning role {role_id} to user {user_id}",  # noqa: E501
        )

    return False


async def get_user_roles(user_id: str) -> list:
    """Function to get a users roles

    Args:
        user_id (str, optional): user id of the user. Defaults to None.

    Returns:
        list: list of roles for the user
    """
    roles = []

    query = """
        SELECT DISTINCT r.*
        from roles as r
        JOIN user_role as ur
        ON ur.role_id = r.role_id
        WHERE
            ur.user_id = $1
            AND r.active = true
            AND (r.expiration_date > $2 OR r.expiration_date IS NULL)
        ;
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_roles = await conn.fetch(
                query,
                user_id,
                datetime.datetime.utcnow(),
            )
            for role in found_roles:
                roles.append(
                    {
                        "roleId": role[0],
                        "roleName": role[1],
                        "roleDesc": role[2],
                    },
                )

    except Exception:
        log.exception(
            f"An error occured while getting roles for user {user_id}",
        )

    return roles


async def get_user_roles_and_permissions(user_id: str) -> Tuple[list, list]:
    """Function to get a users roles

    Args:
        user_id (str): user id of the user.

    Returns:
        list: list of roles for the user
    """
    roles = []
    permissions = []
    if not user_id:
        return roles, permissions

    role_query = """
        SELECT DISTINCT r.*
        from roles as r
        JOIN user_role as ur
        ON ur.role_id = r.role_id
        WHERE
            ur.user_id = $1
            AND r.active = true
            AND (r.expiration_date > $2 OR r.expiration_date IS NULL)
        ;
    """

    permission_query = """
        SELECT DISTINCT p.*
        from roles AS r
        JOIN role_permissions AS rp ON rp.role_id = r.role_id
        JOIN permissions AS p ON p.permission_id = rp.permission_id
        JOIN user_role as ur ON ur.role_id = r.role_id
        WHERE
            ur.user_id = $1
            AND r.active = true
            AND (r.expiration_date > $2 OR r.expiration_date IS NULL)
            AND p.active = true
            AND (p.expiration_date > $2 OR p.expiration_date IS NULL)
        ;
    """

    found_roles = None
    found_permissions = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_roles = await conn.fetch(
                role_query,
                user_id,
                datetime.datetime.utcnow(),
            )
            found_permissions = await conn.fetch(
                permission_query,
                user_id,
                datetime.datetime.utcnow(),
            )
        if found_roles:
            for role in found_roles:
                roles.append(
                    {
                        "roleId": role[0],
                        "roleName": role[1],
                        "roleDesc": role[2],
                    },
                )
        if found_permissions:
            for permission in found_permissions:
                permissions.append(
                    {
                        "permissionId": permission["permission_id"],
                        "permissionNode": permission["permission_node"],
                        "description": permission["permission_desc"],
                    },
                )
    except Exception:
        log.exception(
            f"An error occured while getting roles and permissions for user {user_id}",  # noqa: E501
        )

    return roles, permissions


async def get_role_id(role_name: str) -> Union[str, None]:
    """Functon to get a role's role_id

    Args:
        role_name (str, optional): role name of the role being looked up.
        Defaults to None.

    Returns:
        str: Returns the role Id of the role
    """
    query = """
    SELECT role_id from roles where role_name = $1
    """
    role_id = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_role_id = await conn.fetchrow(query, role_name)
            if found_role_id:
                role_id = found_role_id["role_id"]

    except Exception:
        log.exception(
            f"An error occured while getting role_id for role {role_name}",
        )

    return role_id


async def get_students(
    course_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
    user_ids: Optional[List[str]] = None,
) -> list:
    """function to get students for a course

    Args:
        course_id (str, optional): course id to get students
        bundle_id (str, optional): bundle id to get students with
    Returns:
        list: students of the course id/bundle id provided
    """
    params = []
    where_condition = []

    if course_id:
        where_condition.append(f"cr.course_id = ${len(params) + 1}")
        params.append(course_id)

    if bundle_id:
        where_condition.append(f"b.bundle_id = ${len(params) + 1}")
        params.append(bundle_id)

    if user_ids:
        length = ", ".join(["$" + str(i + 1) for i in range(len(user_ids))])
        where_condition.append(f"u.user_id IN ({length})")
        params.append(*user_ids)

    query = f"""
        SELECT
            u.user_id,
            u.first_name,
            u.last_name,
            u.email,
            u.phone_number,
            u.text_notif,
            u.email_notif,
            u.time_zone
        FROM users u
        JOIN course_registration cr
        on cr.user_id = u.user_id
        WHERE {' AND '.join(where_condition)};
    """

    if bundle_id:
        query = f"""
            SELECT
                u.user_id,
                u.first_name,
                u.last_name,
                u.email,
                u.phone_number,
                u.text_notif,
                u.email_notif,
                u.time_zone
            FROM users u
            JOIN course_registration cr
            on cr.user_id = u.user_id
            JOIN bundled_courses bc
            on cr.course_id = bc.course_id
            JOIN course_bundles b
            ON bc.bundle_id = b.bundle_id
            WHERE {' AND '.join(where_condition)};
        """
    formatted_students = []
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            students = await conn.fetch(query, *params)
            if students:
                for student in students:
                    formatted_students.append(
                        {
                            "user_id": student["user_id"],
                            "first_name": student["first_name"],
                            "last_name": student["last_name"],
                            "email": student["email"],
                            "phone_number": student["phone_number"],
                            "email_allowed": student["email_notif"],
                            "text_allowed": student["text_notif"],
                            "time_zone": student["time_zone"],
                        },
                    )

    except Exception:
        log.exception(
            f"An error occured while getting students for course {params[0]}",
        )

    return formatted_students


async def get_instructors(
    course_id: Optional[str] = None,
    bundle_id: Optional[str] = None,
) -> list:
    """function to get instructors of a course

    Args:
        course_id (str): id of the course to check
        bundle_id (str, optional): bundle id to get instructors with

    Returns:
        list: list of instructors
    """

    if course_id:
        value = course_id
        query = """
            SELECT
                u.user_id,
                u.first_name,
                u.last_name,
                u.email,
                u.phone_number,
                u.text_notif,
                u.email_notif,
                u.time_zone
            FROM users u
            JOIN course_instructor ci
            on u.user_id = ci.user_id
            WHERE ci.course_id = $1;
        """
    if bundle_id:
        value = bundle_id
        query = """
            SELECT
                u.user_id,
                u.first_name,
                u.last_name,
                u.email,
                u.phone_number,
                u.text_notif,
                u.email_notif,
                u.time_zone
            FROM users u
            JOIN course_instructor ci
            on u.user_id = ci.user_id
            JOIN bundled_courses bc
            on cr.course_id = bc.course_id
            JOIN course_bundles b
            ON bc.bundle_id = b.bundle_id
            WHERE b.bundle_id = $1;
        """
    formatted_instructors = []
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            instructors = await conn.fetch(query, value)
            if instructors:
                for instructor in instructors:
                    formatted_instructors.append(
                        {
                            "user_id": instructor["user_id"],
                            "first_name": instructor["first_name"],
                            "last_name": instructor["last_name"],
                            "email": instructor["email"],
                            "phone_number": instructor["phone_number"],
                            "email_allowed": instructor["text_notif"],
                            "text_allowed": instructor["email_notif"],
                            "time_zone": instructor["time_zone"],
                        },
                    )
    except Exception:
        log.exception(
            f"Failed to get course instructors for course_id {course_id}",
        )
    return formatted_instructors


async def get_user_certifications(
    user: global_models.User,
    certificate_number: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    newest: bool = False,
) -> Tuple[list, int, int]:
    certificates_query = """
        SELECT
            uc.user_id,
            c.course_code,
            c.course_name,
            COALESCE(cert.certificate_name, uc.certificate_name) as certificate_name,
            uc.certificate_number,
            uc.completion_date,
            uc.expiration_date,
            u.first_name as student_first,
            u.last_name as student_last,
            inst.first_name as instr_first,
            inst.last_name as instr_last,
            uc.instructor_name
        FROM user_certificates as uc
        LEFT JOIN courses as c
        ON c.course_id = uc.course_id
        LEFT JOIN certificate cert
        ON uc.certificate_id = cert.certificate_id
        LEFT JOIN users as u
        ON u.user_id = uc.user_id
        LEFT JOIN users as inst
        ON uc.instructor_id = inst.user_id
        WHERE uc.user_id = $1
    """  # noqa: E501
    certificates_query_args = [user.userId]

    total_count_query = """
        SELECT COUNT(*)
        FROM user_certificates as uc
        LEFT JOIN courses as c
        ON c.course_id = uc.course_id
        LEFT JOIN certificate cert
        ON uc.certificate_id = cert.certificate_id
        LEFT JOIN users as u
        ON u.user_id = uc.user_id
        LEFT JOIN users as inst
        ON uc.instructor_id = inst.user_id
        WHERE uc.user_id = $1
    """
    total_count_query_args = [user.userId]

    if certificate_number:
        certificates_query += " AND uc.certificate_number = $2"
        total_count_query += " AND uc.certificate_number = $2"
        certificates_query_args.append(certificate_number)
        total_count_query_args.append(certificate_number)

    certificates_query += (
        f" ORDER BY uc.completion_date {'DESC' if newest else 'ASC'}"
    )

    if page and pageSize:
        certificates_query += (
            " LIMIT $3 OFFSET $4"
            if certificate_number
            else " LIMIT $2 OFFSET $3"
        )
        certificates_query_args.extend([pageSize, (page - 1) * pageSize])  # type: ignore

    certificates_query += ";"
    total_count_query += ";"

    certifications = []

    total_pages = 0
    total_count = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            certificates = await conn.fetch(
                certificates_query,
                *certificates_query_args,
            )
            if page and pageSize:
                total_count = await conn.fetchrow(
                    total_count_query,
                    *total_count_query_args,
                )
            if certificates:
                for c in certificates:
                    certificate_name = (
                        c["certificate_name"]
                        or (
                            (
                                f"{c['course_name']}, "
                                if c["course_name"]
                                else ""
                            )
                            + c["course_code"]
                        )
                        or "N/A"
                    )
                    instructor = (
                        c["instructor_name"]
                        or (
                            (
                                f"{c['instr_first']} "
                                if c["instr_first"]
                                else ""
                            )
                            + c["instr_last"]
                        )
                        or os.getenv("COMPANY_NAME")
                    )
                    certificate = my_certifications.Certification(
                        userId=c["user_id"],
                        certificateName=certificate_name,
                        certificateNumber=c["certificate_number"],
                        completionDate=datetime.datetime.strftime(
                            convert_tz(c["completion_date"], tz=user.timeZone),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if c["completion_date"]
                        else None,  # type: ignore
                        expirationDate=datetime.datetime.strftime(
                            convert_tz(c["expiration_date"], tz=user.timeZone),
                            "%m/%d/%Y %-I:%M %p",
                        )
                        if c["expiration_date"]
                        else None,
                        student=f"{c['student_first']} {c['student_last']}",
                        instructor=instructor,  # type: ignore
                    )
                    certifications.append(certificate.dict())

    except Exception:
        log.exception(
            f"An error occured while getting certifications for user {user.userId}",  # noqa: E501
        )

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return certifications, ceil(total_pages), total_count


async def upload_user_pictures(
    user_id: str,
    save_to_db: dict,
    user: global_models.User,
) -> bool:
    set_conditions = ["modify_dtm = $1"]
    params = [datetime.datetime.utcnow()]
    param_counter = 2
    if save_to_db.get("head_shot"):
        set_conditions.append(f"head_shot = ${param_counter}")
        params.append(save_to_db["head_shot"])
        param_counter += 1
    if save_to_db.get("photo_id_photo"):
        set_conditions.append(f"photo_id_photo = ${param_counter}")
        params.append(save_to_db["photo_id_photo"])
        param_counter += 1
    if save_to_db.get("other_id_photo"):
        set_conditions.append(f"other_id_photo = ${param_counter}")
        params.append(save_to_db["other_id_photo"])
        param_counter += 1

    query = f"""
        UPDATE users SET {', '.join(set_conditions)}
        WHERE user_id=${param_counter};
    """
    params.append(user_id)  # type: ignore

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(query, *params)
        return True

    except Exception:
        log.exception(
            f"An error occured while updating user picture for user {user_id}",
        )

    return False


async def delete_users(user_ids: list) -> tuple:
    failed_deletes = []
    err = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            for user_id in user_ids:
                try:
                    user = await get_user(user_id=user_id)
                    if not user:
                        log.error(f"user not found for user_id {user_id}")
                        failed_deletes.append(
                            {
                                "userId": user_id,
                                "reason": "Failed to find user",
                            },
                        )
                        continue
                    async with conn.transaction():
                        await conn.execute(
                            "DELETE FROM user_role WHERE user_id = $1",
                            user_id,
                        )
                        await conn.execute(
                            "DELETE FROM course_instructor WHERE user_id = $1",
                            user_id,
                        )
                        await conn.execute(
                            "DELETE FROM course_registration WHERE user_id = $1",  # noqa: E501
                            user_id,
                        )
                        await conn.execute(
                            "DELETE FROM form_submissions WHERE user_id = $1",
                            user_id,
                        )
                        await conn.execute(
                            "DELETE FROM user_certificates WHERE user_id = $1",
                            user_id,
                        )
                        await conn.execute(
                            "DELETE FROM users WHERE user_id = $1",
                            user_id,
                        )

                    if user.headShot:
                        file_path = (
                            f"/source/src/content/users/{user.headShot}"
                        )
                        if os.path.exists(file_path):
                            os.remove(file_path)

                    if user.otherIdPhoto:
                        file_path = (
                            f"/source/src/content/users/{user.otherIdPhoto}"
                        )
                        if os.path.exists(file_path):
                            os.remove(file_path)

                    if user.photoIdPhoto:
                        file_path = (
                            f"/source/src/content/users/{user.photoIdPhoto}"
                        )
                        if os.path.exists(file_path):
                            os.remove(file_path)

                except Exception:
                    log.exception("Failed to delete something")
                    failed_deletes.append(
                        {
                            "userId": user_id,
                            "reason": "Failed to delete specific user",
                        },
                    )
    except Exception:
        log.exception("An exception occured while deleting users")
        err = "Fatal error occured"

    return (failed_deletes if failed_deletes else None, err)


async def deactivate_user(user_id: str) -> Union[bool, str]:
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                """UPDATE users SET active=false WHERE user_id = $1""",
                user_id,
            )
        return True
    except Exception:
        log.exception(
            f"An exception occured while deactivating user {user_id}",
        )
    return False


async def activate_user(user_id: str) -> Union[bool, str]:
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            await conn.execute(
                """UPDATE users SET active=true WHERE user_id = $1""",
                user_id,
            )
        return True
    except Exception:
        log.exception(f"An exception occured while activating user {user_id}")
    return False


async def get_certificates(
    user: global_models.User,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
    newest: bool = False,
) -> Tuple[list, int, int]:
    """Function to get all user certifications

    Returns:
        list: List of user certifications
    """
    formatted_certifications = []
    found_certificates = None

    query = f"""
        SELECT
            u.user_id,
            u.head_shot,
            u.first_name,
            u.last_name,
            uc.certificate_number,
            uc.completion_date,
            uc.expiration_date,
            uc.instructor_name,
            COALESCE(cert.certificate_name, uc.certificate_name) as certificate_name,
            c.course_name,
            c.course_code,
            (
                SELECT ARRAY_AGG(ARRAY[inst.first_name, inst.last_name])
                FROM course_instructor ci
                LEFT JOIN
                    users inst ON inst.user_id = ci.user_id
                WHERE ci.course_id = uc.course_id
            ) as instructors
        FROM users u
        JOIN user_certificates uc
        ON u.user_id = uc.user_id
        LEFT JOIN courses c ON c.course_id = uc.course_id
        LEFT JOIN certificate cert ON uc.certificate_id = cert.certificate_id
        ORDER BY uc.completion_date {'DESC' if newest else 'ASC'}
    """  # noqa: E501
    query_args = []

    if page and pageSize:
        query += " LIMIT $1 OFFSET $2"
        query_args = [pageSize, (page - 1) * pageSize]

    query += ";"

    total_pages = 0
    total_count = 0
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found_certificates = await conn.fetch(query, *query_args)
            if page and pageSize:
                total_count = await conn.fetchrow("""
                    SELECT
                        COUNT(*)
                    FROM user_certificates;
                """)

        if found_certificates:
            for cert in found_certificates:
                certificate_name = (
                    cert.get("certificate_name")
                    or (
                        (
                            f"{cert['course_name']}, "
                            if cert["course_name"]
                            else ""
                        )
                        + cert["course_code"]
                    )
                    or "N/A"
                )
                instructor = cert["instructor_name"]
                if cert["instructors"]:
                    instructor = f"{cert['instructors'][0][0]} {cert['instructors'][0][1]}"  # noqa: E501
                if not instructor:
                    instructor = os.getenv("COMPANY_NAME")

                formatted_certifications.append(
                    {
                        "userId": cert["user_id"],
                        "headShot": cert["head_shot"],
                        "firstName": cert["first_name"],
                        "lastName": cert["last_name"],
                        "certificateNumber": cert["certificate_number"],
                        "certificateName": certificate_name,
                        "completionDate": (
                            datetime.datetime.strftime(
                                convert_tz(
                                    cert["completion_date"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if cert["completion_date"]
                            else None
                        ),
                        "expirationDate": (
                            datetime.datetime.strftime(
                                convert_tz(
                                    cert["expiration_date"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if cert["expiration_date"]
                            else None
                        ),
                        "instructor": instructor,
                    },
                )
    except Exception:
        log.exception("Failed to get certifications")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return formatted_certifications, ceil(total_pages), total_count


async def delete_user_certificates(certificate_numbers: list) -> bool:
    query = """
        DELETE FROM user_certificates where certificate_number = $1
    """

    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            for certificate_number in certificate_numbers:
                await conn.execute(query, certificate_number)
        return True

    except Exception:
        log.exception(f"Failed to delete certificates {certificate_numbers}")

    return False


async def find_certificate(
    user_id: str,
    course_id: str,
    certificate_name: Optional[str] = None,
) -> bool:
    query = """
    SELECT * FROM user_certificates WHERE user_id = $1 AND certificate_name = $2;
    """  # noqa: E501

    if course_id:
        query = """
        SELECT * FROM user_certificates WHERE user_id = $1 AND course_id = $2;
        """

    found = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if course_id:
                found = await conn.fetch(query, user_id, course_id)
            else:
                found = await conn.fetch(query, user_id, certificate_name)

        if found:
            return True

    except Exception:
        log.exception("Failed to find user certificates")

    return False


async def search_certificates(
    user: global_models.User,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    email: Optional[str] = None,
    phone_number: Optional[str] = None,
    certificate_number: Optional[str] = None,
    page: int = 1,
    pageSize: int = 20,  # noqa: N803
) -> Tuple[list, int, int]:
    params = []
    conditions = []
    where_clause = ""
    pagination = ""
    certificates = []
    pg = []

    if first_name:
        conditions.append(f"UPPER(u.first_name) LIKE UPPER(${len(params)+1})")
        params.append(f"%{first_name}%")

    if last_name:
        conditions.append(f"UPPER(u.last_name) LIKE UPPER(${len(params)+1})")
        params.append(f"%{first_name}%")

    if email:
        conditions.append(f"UPPER(u.email) LIKE UPPER(${len(params)+1})")
        params.append(f"%{email}%")

    if phone_number:
        conditions.append(f"u.phone_number LIKE ${len(params)+1}")
        params.append(f"%{phone_number}%")

    if certificate_number:
        conditions.append(
            f"UPPER(uc.certificate_number) LIKE UPPER(${len(params)+1})",
        )
        params.append(f"%{certificate_number}%")

    if conditions:
        where_clause = f"WHERE {' AND '.join(conditions)}"

    if page and pageSize:
        pagination = f"LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}"
        pg.extend([pageSize, (page - 1) * pageSize])

    query = f"""
        SELECT
            u.user_id,
            u.head_shot,
            u.first_name,
            u.last_name,
            uc.certificate_number,
            uc.completion_date,
            uc.expiration_date,
            uc.instructor_name,
            cert.certificate_name,
            c.course_name,
            c.course_code,
            (
                SELECT ARRAY_AGG(ARRAY[inst.first_name, inst.last_name])
                FROM course_instructor ci
                LEFT JOIN
                    users inst ON inst.user_id = ci.user_id
                WHERE ci.course_id = uc.course_id
            ) as instructors
        FROM users u
        JOIN
            user_certificates uc ON u.user_id = uc.user_id
        LEFT JOIN
            courses c ON c.course_id = uc.course_id
        LEFT JOIN
            certificate cert ON uc.certificate_id = cert.certificate_id
        {where_clause}
        ORDER BY uc.completion_date ASC
        {pagination};
    """

    total_pages = 0
    total_count = 0
    found_certificates = None
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            if page and pageSize:
                total_count = await conn.fetchrow(
                    f"""
                    SELECT
                        COUNT(*)
                    FROM users u
                    JOIN user_certificates uc ON u.user_id = uc.user_id
                    LEFT JOIN courses c ON c.course_id = uc.course_id
                    LEFT JOIN certificate cert ON uc.certificate_id = cert.certificate_id
                    {where_clause};
                """,  # noqa: E501
                    *params,
                )
            found_certificates = await conn.fetch(query, *params, *pg)

        if found_certificates:
            for cert in found_certificates:
                certificate_name = cert.get("certificate_name")
                if not certificate_name:
                    certificate_name = ""
                    if cert["course_code"]:
                        certificate_name += f"{cert['course_code']} "
                    if cert["course_name"]:
                        certificate_name += cert["course_name"]

                instructor = ""
                if cert["instructor_name"]:
                    instructor = cert["instructor_name"]
                if not instructor:
                    instructor = (
                        f"{cert['instructors'][0][0]} {cert['instructors'][0][1]}"  # noqa: E501
                        if cert["instructors"]
                        else os.getenv("COMPANY_NAME")
                    )

                certificates.append(
                    {
                        "userId": cert["user_id"],
                        "headShot": cert["head_shot"],
                        "firstName": cert["first_name"],
                        "lastName": cert["last_name"],
                        "certificateNumber": cert["certificate_number"],
                        "certificateName": certificate_name,
                        "completionDate": (
                            datetime.datetime.strftime(
                                convert_tz(
                                    cert["completion_date"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if cert["completion_date"]
                            else None
                        ),
                        "expirationDate": (
                            datetime.datetime.strftime(
                                convert_tz(
                                    cert["expiration_date"],
                                    tz=user.timeZone,
                                ),
                                "%m/%d/%Y %-I:%M %p",
                            )
                            if cert["expiration_date"]
                            else None
                        ),
                        "instructor": instructor,
                    },
                )
    except Exception:
        log.exception("Failed to search for user certificates")

    if total_count:
        total_count = total_count[0]
        total_pages = total_count / pageSize

    return certificates, ceil(total_pages), total_count


async def check_permissions(user_id: str, permission_nodes: list) -> list:
    lookup_nodes = ["superuser"]
    lookup_nodes.extend(permission_nodes)
    placeholders = ", ".join(f"${i+2}" for i in range(len(lookup_nodes)))
    query = f"""
        SELECT
            p.permission_id,
            p.permission_node
        FROM users u
        JOIN
            user_role ur ON ur.user_id = u.user_id
        JOIN
            roles r ON r.role_id = ur.role_id
        JOIN
            role_permissions rp ON rp.role_id = r.role_id
        JOIN
            permissions p ON p.permission_id = rp.permission_id
        WHERE u.user_id = $1 and p.permission_node IN ({placeholders});
    """

    found = None
    missing = []
    try:
        db_pool = await get_connection()
        async with acquire_connection(db_pool) as conn:
            found = await conn.fetch(query, user_id, *lookup_nodes)

        if not found:
            found = []

        found_permissions = [
            permission["permission_node"] for permission in found
        ]

        if "superuser" in found_permissions:
            return []

        # Check if the user has any of the required permission nodes
        if any(
            permission in found_permissions for permission in permission_nodes
        ):
            return []
        # Return an empty list if the user has any of the required permissions

        # If not, find the missing permissions
        for permission in permission_nodes:
            if permission not in found_permissions:
                missing.append(permission)

    except Exception:
        log.exception("Failed to look up permission nodes for user")

    return missing


async def get_or_create_user(user: dict) -> dict:
    try:
        found_user = await get_user(
            email=user["email"], phoneNumber=user["phone_number"]
        )
        if found_user:
            return {"status": True, "result": found_user, "type": "found"}

        new_user = {
            "user_id": str(uuid.uuid4()),
            "first_name": user["first_name"],
            "last_name": user["last_name"],
            "email": user["email"],
            "phone_number": user["phone_number"],
            "password": pbkdf2_sha256.hash(generate_random_code(12)),
            "time_zone": "America/New_York",
            "create_dtm": datetime.datetime.utcnow(),
            "modify_dtm": datetime.datetime.utcnow(),
            "active": True,
            "text_notif": True,
            "email_notif": True,
            "expiration_date": None,
        }
        created = await create_user(newUser=new_user)
        if isinstance(created, str):
            return {
                "status": False,
                "reason": f"Failed to create user due to {created}",
                "solution": "Please try again with different information.",
            }
        if not created:
            raise Exception("Failed to create user")

        add_role = await manage_user_roles(
            roles=["student"],
            user_id=new_user["user_id"],
            action="add",
        )
        if not add_role:
            raise Exception("Failed to add role to user")

        created_user = await get_user(user_id=new_user["user_id"])
        if not created_user:
            raise Exception("Failed to get created user")

        return {"status": True, "result": created_user, "type": "created"}
    except Exception as exception:
        log.exception(
            f"Failed to get or create user with {exception=} for user {user}"
        )
        traceback.print_exc()

    return {
        "status": False,
        "reason": "Failed to get or create user",
        "solution": "Contact support",
        "system": f"Failed to get or create user for {user=}, more in logs.",
    }
