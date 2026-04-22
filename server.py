"""
Store Address MCP — a small FastMCP server over HTTP (Uvicorn / AWS App Runner).

Endpoints
---------
- ``GET /`` and ``GET /health`` — return ``ok`` (for load balancer health checks).
- ``/mcp`` — MCP streamable HTTP. Clients must use the full URL including ``/mcp``,
  e.g. ``https://<host>/mcp``.

Optional auth (env ``MCP_REQUEST_HEADERS``)
-------------------------------------------
If unset, all routes stay open. If set:

- Plain text (not JSON): clients must send header ``MCP_REQUEST_HEADERS`` with this exact value.
- JSON object: each ``"Header-Name": "value"`` pair must match incoming headers.

Health routes never require these headers.

Run locally: ``uvicorn server:app --host 0.0.0.0 --port 8000`` then MCP URL is ``http://localhost:8000/mcp``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from urllib.parse import urlencode
from urllib.request import urlopen

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
    """Return required header name -> value from env, or None if auth is disabled."""
    raw = os.environ.get("MCP_REQUEST_HEADERS", "").strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"MCP_REQUEST_HEADERS JSON is invalid: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("MCP_REQUEST_HEADERS JSON must be an object")
        out = {str(k).strip(): str(v).strip() for k, v in data.items()}
        return out if out else None
    return {"MCP_REQUEST_HEADERS": raw}


class CustomHeaderAuthMiddleware(BaseHTTPMiddleware):
    """If rules are set, require matching headers on all routes except GET / and GET /health."""

    def __init__(self, app, required: dict[str, str] | None):
        super().__init__(app)
        self.required = required

    async def dispatch(self, request: Request, call_next):
        if self.required is None:
            return await call_next(request)

        path = request.url.path
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.method == "GET" and path in ("/", "/health"):
            return await call_next(request)

        for name, expected in self.required.items():
            if request.headers.get(name) != expected:
                logger.warning("auth failed: %s %s", request.method, path)
                return PlainTextResponse("Unauthorized", status_code=401)

        return await call_next(request)


_HEADER_RULES = _load_custom_header_rules()

# Mock customer-order API (no auth). Query: ?id=<order_id>
CUSTOMER_ORDER_API = "https://67e9aa0bbdcaa2b7f5b9ed62.mockapi.io/customerOrder"

mcp = server.FastMCP("Store Address MCP")

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
            return {
                "success": True,
                "city": loc["city"],
                "address": loc["address"],
                "country": loc["country"],
            }
    return {
        "success": True,
        "stores": list(STORE_LOCATIONS.values()),
        "total_stores": len(STORE_LOCATIONS),
    }


def _fetch_order_json(order_id: str) -> object:
    """Synchronous GET to MockAPI; used from async via asyncio.to_thread."""
    url = f"{CUSTOMER_ORDER_API}?{urlencode({'id': order_id})}"
    with urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


@mcp.tool()
async def check_order_status(order_id: str) -> dict:
    """Look up a customer order by id and return its status (e.g. new, cancel)."""
    oid = order_id.strip()
    if not oid.isdigit():
        return {
            "success": False,
            "error": "order_id must be digits only (e.g. 64).",
        }
    try:
        payload = await asyncio.to_thread(_fetch_order_json, oid)
    except Exception as e:
        logger.warning("check_order_status: request failed order_id=%s err=%s", oid, e)
        return {"success": False, "error": "Could not reach order service.", "order_id": oid}

    if not isinstance(payload, list) or len(payload) == 0:
        return {
            "success": False,
            "error": "No order found for this id.",
            "order_id": oid,
        }

    row = payload[0]
    if not isinstance(row, dict):
        return {"success": False, "error": "Unexpected response shape.", "order_id": oid}

    status = row.get("status", "")
    # Caller asked for status only; include success flag for errors vs OK.
    return {"success": True, "status": status}


_mcp_asgi = mcp.http_app(path="/mcp")


async def _health(_):
    return PlainTextResponse("ok")


app = Starlette(
    routes=[
        Route("/", _health),
        Route("/health", _health),
        Mount("/", _mcp_asgi),
    ],
    middleware=[Middleware(CustomHeaderAuthMiddleware, required=_HEADER_RULES)],
    lifespan=_mcp_asgi.router.lifespan_context,
)
