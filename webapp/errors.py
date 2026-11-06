import json
import logging
from collections.abc import Mapping
from typing import Any

from kubernetes.client.rest import ApiException
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_500_INTERNAL_SERVER_ERROR

_LOGGER = logging.getLogger(__name__)


def error_response(
    message: str, status_code: int, *, details: Any | None = None
) -> JSONResponse:
    payload = {"status": "error", "message": message}
    if details is not None:
        payload["details"] = details
    return JSONResponse(payload, status_code=status_code)


def http_exception_response(exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, Mapping):
        payload = {"status": "error", **exc.detail}
        payload.setdefault("message", "Request failed")
        return JSONResponse(
            payload, status_code=exc.status_code, headers=exc.headers
        )

    return error_response(str(exc.detail), exc.status_code)


async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return http_exception_response(exc)


async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    _LOGGER.error(
        "Unhandled exception while processing %s %s",
        request.method,
        request.url.path,
        exc_info=exc,
    )
    return error_response("Internal server error", HTTP_500_INTERNAL_SERVER_ERROR)


def api_exception_status_code(exc: ApiException) -> int:
    status = getattr(exc, "status", None)
    return status if isinstance(status, int) and 400 <= status <= 599 else 503


def api_exception_message(exc: ApiException) -> str:
    body_message = _api_exception_body_message(exc)
    parts = [
        part
        for part in [str(getattr(exc, "reason", "")).strip(), body_message]
        if part
    ]
    if not parts:
        return "Kubernetes API request failed"

    deduped_parts = []
    for part in parts:
        if part not in deduped_parts:
            deduped_parts.append(part)

    return ": ".join(deduped_parts)


def _api_exception_body_message(exc: ApiException) -> str | None:
    body = getattr(exc, "body", None)
    if not body:
        return None

    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        text = str(body).strip()
        return text or None

    if not isinstance(parsed, Mapping):
        return None

    for key in ("message", "reason"):
        value = parsed.get(key)
        if value:
            return str(value)

    return None
