import logging
from json import JSONDecodeError
from collections.abc import Callable, Mapping

from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.status import HTTP_400_BAD_REQUEST

from core.sync import sync
from errors import error_response


_LOGGER = logging.getLogger(__name__)


def _summarize_request(body: Mapping) -> str:
    """Return a short summary of the sync request without sensitive fields."""
    if not isinstance(body, Mapping):
        return f"invalid_body_type={type(body).__name__}"
    metadata = body.get("parent", {}).get("metadata", {})
    return f"name={metadata.get('name')}, namespace={metadata.get('namespace')}, generation={metadata.get('generation')}"


def build_webhook(sync_func: Callable[[Mapping], Mapping]):
    async def webhook(request: Request):
        try:
            body = await request.json()
            if not isinstance(body, Mapping):
                raise HTTPException(
                    status_code=HTTP_400_BAD_REQUEST,
                    detail="Request body must be a JSON object",
                )
            _LOGGER.debug("Webhook request: %s", _summarize_request(body))
            response = sync_func(body)
        except JSONDecodeError as e:
            return error_response(
                f"Failed to parse request body: {e.msg}",
                status_code=HTTP_400_BAD_REQUEST,
            )
        except HTTPException as e:
            return error_response(str(e.detail), status_code=e.status_code)
        except KeyError as e:
            return error_response(
                f"Missing field from request: {str(e)}",
                status_code=HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            _LOGGER.error("Unexpected error processing webhook: %s", e, exc_info=True)
            return error_response("Internal server error", status_code=500)

        _LOGGER.debug("Webhook response: status=%s", response.get("status", {}))
        return JSONResponse(response)

    return webhook


routes = [
    Route("/sync", endpoint=build_webhook(sync), methods=["POST"]),
]
