"""ASGI middleware: request correlation and context for MCP HTTP apps."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("mcp-factory")

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def make_mcp_middleware(app: ASGIApp, service_name: str, request_ctx) -> ASGIApp:
    """Wrap the MCP ASGI app with logging and a per-request context var."""

    async def middleware(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        req_id = str(uuid.uuid4())
        token = request_ctx.set(
            {
                "service": service_name,
                "request_id": req_id,
                "path": scope.get("path", ""),
            }
        )
        try:
            logger.info(
                "[%s] start request_id=%s path=%s",
                service_name,
                req_id,
                scope.get("path"),
            )
            await app(scope, receive, send)
        finally:
            request_ctx.reset(token)
            logger.info("[%s] end request_id=%s", service_name, req_id)

    return middleware
