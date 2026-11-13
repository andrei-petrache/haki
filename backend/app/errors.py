"""A machine-readable code on every error response.

Every error body is {"detail": ..., "code": ...}. `detail` is unchanged: the
English message, or for a 422 FastAPI's list of problems. `code` is a stable
snake_case name that clients translate and branch on, instead of matching
English text. Codes are part of the API: add new ones, never rename or
reuse one.
"""

from enum import StrEnum
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.utils import is_body_allowed_for_status_code
from starlette.exceptions import HTTPException as StarletteHTTPException


class ErrorCode(StrEnum):
    # Raised by our own code (see ERRORS)
    NOT_AUTHENTICATED = "not_authenticated"
    INVALID_TOKEN = "invalid_token"
    INVALID_CREDENTIALS = "invalid_credentials"
    WRONG_PASSWORD = "wrong_password"
    EMAIL_TAKEN = "email_taken"
    FOOD_NOT_FOUND = "food_not_found"
    FOOD_NAME_TAKEN = "food_name_taken"
    FOOD_IN_USE = "food_in_use"
    CATALOG_FOOD_NOT_FOUND = "catalog_food_not_found"
    ENTRY_NOT_FOUND = "entry_not_found"
    MEAL_FULL = "meal_full"
    EXERCISE_NOT_FOUND = "exercise_not_found"
    EXERCISE_NAME_TAKEN = "exercise_name_taken"
    EXERCISE_IN_USE = "exercise_in_use"
    CATALOG_EXERCISE_NOT_FOUND = "catalog_exercise_not_found"
    WORKOUT_NOT_FOUND = "workout_not_found"
    PROGRAM_NOT_FOUND = "program_not_found"
    PROGRAM_DAY_NOT_FOUND = "program_day_not_found"
    PROGRAM_CONFLICT = "program_conflict"
    VALIDATION_ERROR = "validation_error"
    DATABASE_UNAVAILABLE = "database_unavailable"
    SERVER_BUSY = "server_busy"
    # Errors FastAPI or Starlette raise themselves (an unknown path, a wrong
    # method) carry no code: they get one from their status (see FALLBACK)
    BAD_REQUEST = "bad_request"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    CONFLICT = "conflict"
    HTTP_ERROR = "http_error"


# The status and English message of each code our own code raises
ERRORS: dict[ErrorCode, tuple[HTTPStatus, str]] = {
    ErrorCode.NOT_AUTHENTICATED: (HTTPStatus.UNAUTHORIZED, "Not authenticated"),
    ErrorCode.INVALID_TOKEN: (HTTPStatus.UNAUTHORIZED, "Invalid or expired token"),
    ErrorCode.INVALID_CREDENTIALS: (
        HTTPStatus.UNAUTHORIZED,
        "Invalid email or password",
    ),
    # 403, not 401: the token is valid, and clients sign out on a 401
    ErrorCode.WRONG_PASSWORD: (HTTPStatus.FORBIDDEN, "Current password is wrong"),
    ErrorCode.EMAIL_TAKEN: (HTTPStatus.CONFLICT, "Email already registered"),
    ErrorCode.FOOD_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Food not found"),
    ErrorCode.FOOD_NAME_TAKEN: (
        HTTPStatus.CONFLICT,
        "A food with this name already exists",
    ),
    ErrorCode.FOOD_IN_USE: (HTTPStatus.CONFLICT, "Food is used by meal entries"),
    ErrorCode.CATALOG_FOOD_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Catalog food not found"),
    ErrorCode.ENTRY_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Entry not found"),
    # app.entries passes the message with the limit in it
    ErrorCode.MEAL_FULL: (HTTPStatus.CONFLICT, "The meal is full"),
    ErrorCode.EXERCISE_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Exercise not found"),
    ErrorCode.EXERCISE_NAME_TAKEN: (
        HTTPStatus.CONFLICT,
        "An exercise with this name already exists",
    ),
    ErrorCode.EXERCISE_IN_USE: (
        HTTPStatus.CONFLICT,
        "Exercise is used by workouts or programs",
    ),
    ErrorCode.CATALOG_EXERCISE_NOT_FOUND: (
        HTTPStatus.NOT_FOUND,
        "Catalog exercise not found",
    ),
    ErrorCode.WORKOUT_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Workout not found"),
    ErrorCode.PROGRAM_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Program not found"),
    ErrorCode.PROGRAM_DAY_NOT_FOUND: (HTTPStatus.NOT_FOUND, "Program day not found"),
    ErrorCode.PROGRAM_CONFLICT: (
        HTTPStatus.CONFLICT,
        "A program with this name already exists, "
        "or two of its days have the same position",
    ),
    ErrorCode.DATABASE_UNAVAILABLE: (
        HTTPStatus.SERVICE_UNAVAILABLE,
        "Service temporarily unavailable, try again shortly",
    ),
    ErrorCode.SERVER_BUSY: (
        HTTPStatus.SERVICE_UNAVAILABLE,
        "Server busy, try again shortly",
    ),
}

FALLBACK: dict[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: ErrorCode.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED: ErrorCode.NOT_AUTHENTICATED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    HTTPStatus.CONFLICT: ErrorCode.CONFLICT,
}


class ApiError(HTTPException):
    """An HTTPException with a code; its status and message come from ERRORS."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        status_code, message = ERRORS[code]
        super().__init__(status_code, detail=detail or message, headers=headers)
        self.code = code


def error_response(
    code: ErrorCode, headers: dict[str, str] | None = None
) -> JSONResponse:
    """The response for `code`, for exception handlers that build their own."""
    status_code, message = ERRORS[code]
    return JSONResponse(
        {"detail": message, "code": code}, status_code=status_code, headers=headers
    )


def code_for(exc: StarletteHTTPException) -> ErrorCode:
    """The exception's own code, or one that follows from its status."""
    if isinstance(exc, ApiError):
        return exc.code
    return FALLBACK.get(exc.status_code, ErrorCode.HTTP_ERROR)


def http_error(request: Request, exc: Exception) -> Response:
    """FastAPI's HTTPException handler, with the code added to the body."""
    assert isinstance(exc, StarletteHTTPException)
    if not is_body_allowed_for_status_code(exc.status_code):
        return Response(status_code=exc.status_code, headers=exc.headers)
    return JSONResponse(
        {"detail": exc.detail, "code": code_for(exc)},
        status_code=exc.status_code,
        headers=exc.headers,
    )


def validation_error(request: Request, exc: Exception) -> JSONResponse:
    """FastAPI's 422 handler, with the code added to the body."""
    assert isinstance(exc, RequestValidationError)
    return JSONResponse(
        {"detail": jsonable_encoder(exc.errors()), "code": ErrorCode.VALIDATION_ERROR},
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Answer every HTTPException and every 422 with a code."""
    app.add_exception_handler(StarletteHTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
