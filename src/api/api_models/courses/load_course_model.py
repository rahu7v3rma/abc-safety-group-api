from typing import List, Optional, Union

from src.api.api_models.bases import BaseModel, BaseOutput
from src.api.api_models.global_models import Course
from src.api.api_models.pagination import PaginationOutput


class QuizRecord(BaseModel):
    quizId: str  # noqa: N815
    quizName: str  # noqa: N815
    passed: bool
    score: Union[int, float]


class SurveyRecord(BaseModel):
    surveyId: str  # noqa: N815
    surveyName: str  # noqa: N815


class SignInRecord(BaseModel):
    status: str
    comments: Optional[str]
    seriesNumber: int  # noqa: N815


class Quiz(BaseModel):
    taken: int
    total: int
    records: List[Optional[QuizRecord]]


class Survey(BaseModel):
    taken: int
    total: int
    records: List[Optional[SurveyRecord]]


class SignInSheet(BaseModel):
    amount: int
    total: int
    records: List[Optional[SignInRecord]]


class Student(BaseModel):
    userId: str  # noqa: N815
    headShot: Optional[str]  # noqa: N815
    firstName: str  # noqa: N815
    lastName: str  # noqa: N815
    phoneNumber: Optional[str]  # noqa: N815
    email: Optional[str]
    dob: Optional[str]
    registrationStatus: str  # noqa: N815
    paid: bool
    usingCash: bool  # noqa: N815
    notes: Optional[str]
    transaction: Optional[str]
    certificate: bool
    quizzes: Optional[Quiz]
    surveys: Optional[Survey]
    signInSheet: Optional[SignInSheet]  # noqa: N815


class Schedule(BaseModel):
    courseId: str  # noqa: N815
    courseName: str  # noqa: N815
    startDate: str  # noqa: N815
    duration: str
    seriesNumber: int  # noqa: N815
    complete: bool
    address: Optional[str]
    remoteLink: Optional[str]  # noqa: N815


class CoursesPayload(BaseModel):
    course: Course
    schedule: Optional[List[Schedule]]
    enrolled: bool


class Output(BaseOutput):
    payload: CoursesPayload


class StudentPayload(BaseModel):
    students: List[Optional[Student]]
    pagination: PaginationOutput


class StudentOutput(BaseOutput):
    payload: StudentPayload
