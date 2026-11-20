"""RFC 9457 problem+json responses for every error the API returns."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.domain.errors import (
    AuthenticationError,
    AuthorizationError,
    DomainError,
    DomainValidationError,
    NotFoundError,
    ServiceUnavailableError,
)

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    AuthorizationError: 403,
    NotFoundError: 404,
    DomainValidationError: 422,
    ServiceUnavailableError: 503,
}

TITLES = {
    400: "Solicitud incorrecta",
    401: "No autenticado",
    403: "Acceso denegado",
    404: "No encontrado",
    405: "Método no permitido",
    422: "Datos inválidos",
    500: "Error interno",
    503: "Servicio no disponible",
}


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[dict[str, Any]] | None = None


# Merge into a router's `responses=` so OpenAPI (and generated TS types) know the shape.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": ProblemDetails, "content": {PROBLEM_MEDIA_TYPE: {}}, "description": title}
    for status, title in TITLES.items()
    if status in (401, 403, 422)
}


def problem(
    request: Request,
    status: int,
    detail: str | None = None,
    *,
    headers: dict[str, str] | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    title = TITLES.get(status) or HTTPStatus(status).phrase
    body = ProblemDetails(
        title=title, status=status, detail=detail or None, instance=request.url.path, errors=errors
    )
    return JSONResponse(
        body.model_dump(exclude_none=True),
        status_code=status,
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _status_for(exc: DomainError) -> int:
    for cls in type(exc).__mro__:
        if cls in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[cls]
    return 400


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status = _status_for(exc)
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return problem(request, status, exc.detail, headers=headers)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    detail = exc.detail if isinstance(exc.detail, str) else None
    return problem(request, exc.status_code, detail, headers=exc.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{k: v for k, v in err.items() if k in ("loc", "msg", "type")} for err in exc.errors()]
    return problem(
        request, 422, "La solicitud tiene campos inválidos.", errors=jsonable_encoder(errors)
    )


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return problem(request, 500, "Ocurrió un error inesperado.")


def register_problem_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled_error)
