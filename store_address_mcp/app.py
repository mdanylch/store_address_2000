import contextvars
import logging
import re
from contextvars import ContextVar

import httpx
from fastmcp import server

from .mcp_factory_middleware import make_mcp_middleware

logger = logging.getLogger("mcp-factory")

# ─────────────────────────────────────────────────────────────
#  MCP Server Init
# ─────────────────────────────────────────────────────────────

mcp = server.FastMCP("Flower Shop v1")
request_ctx: ContextVar = contextvars.ContextVar("request_ctx")

# ─────────────────────────────────────────────────────────────
#  Store Location Data
# ─────────────────────────────────────────────────────────────

STORE_LOCATIONS = {
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

# ─────────────────────────────────────────────────────────────
#  Tools
# ─────────────────────────────────────────────────────────────


@mcp.tool()
async def get_store_locations(user_query: str) -> dict:
    """
    Get flower shop store locations.

    Use when customers ask about store locations, addresses, or where to
    find us. Returns a specific city if mentioned, all stores otherwise.

    Args:
        user_query: Customer's question about store locations.
    """
    query_lower = user_query.lower()

    for city_key, location in STORE_LOCATIONS.items():
        if city_key in query_lower or location["city"].lower() in query_lower:
            logger.info(
                "[flower_shop_v1] locations query='%s' -> city=%s", user_query, city_key
            )
            return {
                "success": True,
                "city": location["city"],
                "address": location["address"],
                "country": location["country"],
            }

    logger.info("[flower_shop_v1] locations query='%s' -> all stores", user_query)
    return {
        "success": True,
        "stores": list(STORE_LOCATIONS.values()),
        "total_stores": len(STORE_LOCATIONS),
    }


@mcp.tool()
async def get_bulk_pricing(user_query: str) -> dict:
    """
    Get pricing for bulk flower orders.

    Use when a customer asks about flower quantities and pricing.
    Examples: "100 roses", "price for 250 tulips", "500 sunflowers".
    The pricing service handles all flower validation and price logic.

    Args:
        user_query: Customer's bulk pricing question including quantity and flower type.
    """
    text = user_query.lower().strip()
    numbers = re.findall(r"\d+", text)
    quantity = int(numbers[0]) if numbers else None

    if not quantity:
        return {
            "success": False,
            "error": "Could not identify a quantity in your request.",
            "user_query": user_query,
            "hint": "Please include a quantity e.g. '100 roses' or '250 tulips'.",
        }

    api_url = "https://pb1xxphyld.execute-api.us-east-1.amazonaws.com/prod/chat"
    logger.info(
        "[flower_shop_v1] bulk pricing query='%s' quantity=%d", user_query, quantity
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                api_url,
                json={"prompt": user_query},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = response.json()
            logger.info("[flower_shop_v1] bulk pricing ✅ success")
            return {
                "success": True,
                "query": user_query,
                "pricing_response": result,
            }

    except httpx.TimeoutException:
        logger.warning("[flower_shop_v1] bulk pricing ❌ timeout")
        return {
            "success": False,
            "error": "Bulk pricing service timed out. Please try again.",
            "query": user_query,
        }

    except httpx.HTTPStatusError as e:
        logger.error("[flower_shop_v1] bulk pricing ❌ HTTP %d", e.response.status_code)
        return {
            "success": False,
            "error": f"Bulk pricing service error (HTTP {e.response.status_code})",
            "query": user_query,
        }

    except Exception as e:
        logger.error("[flower_shop_v1] bulk pricing ❌ %s", str(e))
        return {
            "success": False,
            "error": f"Failed to get bulk pricing: {str(e)}",
            "query": user_query,
        }


# ─────────────────────────────────────────────────────────────
#  Mount + Middleware (factory pattern)
# ─────────────────────────────────────────────────────────────

mcp_mount_flower_shop_v1 = mcp.http_app(path="/mcp")
mcp_mount_flower_shop_v1 = make_mcp_middleware(
    mcp_mount_flower_shop_v1, "flower_shop_v1", request_ctx
)
mcp_lifespan_flower_shop_v1 = mcp_mount_flower_shop_v1
