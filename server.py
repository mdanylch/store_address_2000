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
The ASGI application is ``app``, mounted so the MCP HTTP transport lives at
``/mcp`` (not at ``/``). Health checks or load balancers should target a path
you configure separately if you add a root route later.

Run locally::

    pip install -r requirements.txt
    uvicorn server:app --host 0.0.0.0 --port 8000

Then the MCP HTTP base URL is ``http://localhost:8000/mcp`` (exact path depends
on your MCP client’s expectations for streamable HTTP vs legacy SSE—FastMCP
defaults are documented in the fastmcp package).

Environment
-----------
No env vars are required; store data is defined in ``STORE_LOCATIONS`` below.
"""

from __future__ import annotations

import logging

from fastmcp import server

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


# ASGI app for Uvicorn / App Runner: MCP at /mcp
app = mcp.http_app(path="/mcp")
