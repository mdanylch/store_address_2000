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
2. FastMCP dispatches to the right tool based on the MCP protocol.
3. ``get_store_locations`` matches the user's text against known cities and
   returns one store or the full list.
4. ``get_bulk_pricing`` forwards a structured request to an external HTTPS API
   when a quantity is present in the text.

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
No env vars are required for the store list. For production you may want to
move the bulk-pricing API URL to configuration (not hardcoded).
"""

from __future__ import annotations

import logging
import re

import httpx
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

BULK_PRICING_API = "https://pb1xxphyld.execute-api.us-east-1.amazonaws.com/prod/chat"


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


@mcp.tool()
async def get_bulk_pricing(user_query: str) -> dict:
    """If the text contains a number, call the bulk-pricing HTTP API."""
    text = user_query.lower().strip()
    nums = re.findall(r"\d+", text)
    if not nums:
        return {
            "success": False,
            "error": "No quantity found. Example: '100 roses'.",
            "user_query": user_query,
        }

    qty = int(nums[0])
    logger.info("bulk_pricing: qty=%s query=%r", qty, user_query)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                BULK_PRICING_API,
                json={"prompt": user_query},
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
            return {"success": True, "query": user_query, "pricing_response": r.json()}
    except Exception as e:
        logger.exception("bulk_pricing failed")
        return {
            "success": False,
            "error": str(e),
            "query": user_query,
        }


# ASGI app for Uvicorn / App Runner: MCP at /mcp
app = mcp.http_app(path="/mcp")
