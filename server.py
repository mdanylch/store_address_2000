"""
Store-address MCP over HTTP (FastMCP).

What this is
------------
An MCP (Model Context Protocol) server that exposes *tools* an AI client can call.
This file builds one FastMCP instance, registers tools, then exposes the MCP
endpoint as a normal ASGI app (Starlette) so you can run it with Uvicorn—on your
machine or on AWS App Runner.

Data flow (high level)
----------------------
1. A client (e.g. Cursor, Claude Desktop with HTTP MCP, or a custom app) sends
   HTTP requests to the MCP route (see ``app`` below).
2. FastMCP dispatches to the tool based on the MCP protocol.
3. ``get_store_locations`` matches the user's text against known cities and
   returns one store or the full list.

HTTP entrypoint
---------------
The ASGI application ``app`` exposes **GET /** and **GET /health** (plain ``ok``)
for load-balancer health checks (e.g. AWS App Runner). The MCP streamable HTTP
transport is at **/mcp**.

Run locally::

    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8000

Then the MCP HTTP base URL is ``http://localhost:8000/mcp`` (exact path depends
on your MCP client’s expectations for streamable HTTP vs legacy SSE—FastMCP
defaults are documented in the fastmcp package).

Environment
-----------
Optional **CustomHeaderAuth** (e.g. Webex MCP):

- ``MCP_REQUEST_HEADERS`` — If unset, all routes except health stay open. If set:

  - **Plain string** (does not start with ``{``): treat as the secret value clients
    must send in the HTTP header named ``MCP_REQUEST_HEADERS`` (matches Webex
    CustomHeaderAuth when header name and env name align).

  - **JSON object**: e.g. ``{"X-Api-Key": "secret", "X-Other": "v2"}`` — every
    listed header must match (case-insensitive names per HTTP).

Health checks ``GET /`` and ``GET /health`` never require these headers (App Runner).
"""

from __future__ import annotations

import json
import logging
import os

from fastmcp import server
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Mount, Route

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _load_custom_header_rules() -> dict[str, str] | None:
    """Parse MCP_REQUEST_HEADERS env into required header name -> value."""
    raw = os.environ.get("MCP_REQUEST_HEADERS", "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"MCP_REQUEST_HEADERS JSON invalid: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("MCP_REQUEST_HEADERS JSON must be a JSON object")
        out = {str(k): str(v) for k, v in data.items()}
        return out if out else None
    # Single header: name MCP_REQUEST_HEADERS, value = env string (Webex default pattern)
    return {"MCP_REQUEST_HEADERS": raw}


class CustomHeaderAuthMiddleware(BaseHTTPMiddleware):
    """Require configured headers on protected paths (not on / or /health GET)."""

    def __init__(self, app, required: dict[str, str] | None):
        super().__init__(app)
        self.required = required

    async def dispatch(self, request: Request, call_next):
        if self.required is None:
            return await call_next(request)

        path = request.url.path
        if request.method == "GET" and path in ("/", "/health"):
            return await call_next(request)

        for name, expected in self.required.items():
            got = request.headers.get(name)
            if got != expected:
                logger.warning("custom header auth failed for path=%s header=%s", path, name)
                return PlainTextResponse("Unauthorized", status_code=401)

        return await call_next(request)


try:
    _HEADER_RULES = _load_custom_header_rules()
except ValueError as e:
    logger.error("%s", e)
    raise

mcp = server.FastMCP("Store Address MCP")

# Built-in catalog: key = lowercase token to match in user text.
STORE_LOCATIONS: dict[str, dict[str, str]] = {
    "amsterdam": {
        "city": "Amsterdam",
        "address": "Haarlerbergweg 13, 1101 CH Amsterdam, Netherlands",
        "country": "Netherlands",
    },
    "paris": {
        "city": "Paris",
        "address": "18 Rue Washington, 75008 Paris, France",
        "country": "France",
    },
    "lisbon": {
        "city": "Lisbon",
        "address": "2740-244 Porto Salvo, Portugal",
        "country": "Portugal",
    },
}


@mcp.tool()
async def get_store_locations(user_query: str) -> dict:
    """Return one store if a city is mentioned, otherwise all stores."""
    q = user_query.lower()
    for key, loc in STORE_LOCATIONS.items():
        if key in q or loc["city"].lower() in q:
            logger.info("locations: matched city=%s", key)
            return {
                "success": True,
                "city": loc["city"],
                "address": loc["address"],
                "country": loc["country"],
            }
    logger.info("locations: no city match, returning all")
    return {
        "success": True,
        "stores": list(STORE_LOCATIONS.values()),
        "total_stores": len(STORE_LOCATIONS),
    }


_mcp_asgi = mcp.http_app(path="/mcp")


async def _health(_):
    return PlainTextResponse("ok")


# Outer app: health routes for App Runner + MCP under /mcp (must preserve MCP lifespan)
app = Starlette(
    routes=[
        Route("/", _health),
        Route("/health", _health),
        Mount("/", _mcp_asgi),
    ],
    middleware=[
        Middleware(CustomHeaderAuthMiddleware, required=_HEADER_RULES),
    ],
    lifespan=_mcp_asgi.router.lifespan_context,
)
