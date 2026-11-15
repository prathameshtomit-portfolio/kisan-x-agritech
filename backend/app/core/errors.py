from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_payload(code: str, message: str, details: Any = None, request_id: str | None = None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    }


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = "http_error"
    if exc.status_code == 404:
        code = "not_found"
    elif exc.status_code == 422:
        code = "validation_error"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(code, str(exc.detail), request_id=getattr(request.state, "request_id", None)),
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"location": list(item.get("loc", [])), "message": item.get("msg"), "type": item.get("type")}
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_payload(
            "validation_error",
            "The request did not match the API schema.",
            errors,
            getattr(request.state, "request_id", None),
        ),
    )
