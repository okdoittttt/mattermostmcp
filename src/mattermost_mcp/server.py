from __future__ import annotations

import logging
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .auth import EnvTokenAuth, MissingTokenError
from .client import MattermostClient
from .safety import sanitize_error_message

logger = logging.getLogger("mattermost_mcp")

mcp = FastMCP("mattermost-mcp")

_client: MattermostClient | None = None
_init_error: str | None = None


def get_client() -> MattermostClient:
    global _client, _init_error
    if _client is None:
        try:
            _client = MattermostClient(EnvTokenAuth())
        except MissingTokenError as exc:
            _init_error = str(exc)
            raise
    _client._ensure()
    return _client


def safe_call(fn, *args, **kwargs) -> dict[str, Any]:
    try:
        return fn(*args, **kwargs)
    except MissingTokenError as exc:
        return {"error": "auth_not_configured", "hint": sanitize_error_message(str(exc))}
    except Exception as exc:  # noqa: BLE001
        msg = sanitize_error_message(repr(exc))
        status = getattr(exc, "status_code", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        if status == 401:
            return {"error": "unauthorized", "hint": "Token is invalid or expired. Check MM_TOKEN."}
        if status == 403:
            return {"error": "forbidden", "hint": "You don't have permission for this resource."}
        if status == 404:
            return {"error": "not_found", "hint": "Target resource was not found."}
        if status == 429:
            return {"error": "rate_limited", "hint": "Mattermost rate limit hit. Retry later."}
        return {"error": "internal_error", "detail": msg}


# Importing the tools module side-effects in tool registration via @mcp.tool().
from . import tools  # noqa: E402, F401


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("MM_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    mcp.run()


if __name__ == "__main__":
    main()
