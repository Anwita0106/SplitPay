"""
Domain errors shared by the REST layer and the AI agent.

DomainError subclasses FastAPI's HTTPException on purpose:
  * FastAPI still renders it as {"detail": "..."} with the right status code,
    so every existing client keeps working;
  * services stay usable from non-HTTP callers (the AI agent catches it and
    turns `.detail` into a human sentence);
  * a stable machine-readable `code` and optional `extra` payload let the UI
    react precisely (e.g. DUPLICATE_GROUP_NAME -> "Create anyway?").
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse


class DomainError(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str = "ERROR",
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail)
        self.code = code
        self.extra = extra or {}


def not_found(what: str = "Resource", code: str = "NOT_FOUND") -> DomainError:
    return DomainError(status.HTTP_404_NOT_FOUND, f"{what} not found.", code)


def forbidden(detail: str, code: str = "FORBIDDEN") -> DomainError:
    return DomainError(status.HTTP_403_FORBIDDEN, detail, code)


def conflict(detail: str, code: str = "CONFLICT", extra: dict[str, Any] | None = None) -> DomainError:
    return DomainError(status.HTTP_409_CONFLICT, detail, code, extra)


def invalid(detail: str, code: str = "INVALID") -> DomainError:
    return DomainError(status.HTTP_422_UNPROCESSABLE_ENTITY, detail, code)


async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    body: dict[str, Any] = {"detail": exc.detail, "code": exc.code}
    if exc.extra:
        body["extra"] = exc.extra
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)
