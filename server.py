"""SkyBlock Companion: public-data-first MCP server.

No Minecraft credentials or Hypixel API key are requested or stored.
"""
from __future__ import annotations
import os
from typing import Any
from urllib.parse import quote
from datetime import datetime, timezone

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SkyBlock Companion")
SKYCRYPT_API = os.getenv("SKYCRYPT_API_BASE", "https://sky.shiiyu.moe/api/v2/profile")
HYPIXEL_BAZAAR_API = "https://api.hypixel.net/v2/skyblock/bazaar"
TIMEOUT = httpx.Timeout(15.0, connect=8.0)
HEADERS = {"Accept": "application/json", "User-Agent": "SkyBlock-Companion/0.2 (public profile dashboard)"}


def _valid_username(username: str) -> str | None:
    username = username.strip()
    if not username or len(username) > 16 or not username.replace("_", "").isalnum():
        return None
    return username


def _profile_items(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("profiles", "profile"):
        value = payload.get(key)
        if isinstance(value, dict):
            nested = value.get("profiles")
            if isinstance(nested, dict):
                return nested
            return value
    return payload


def _find_profile(payload: Any, profile_name: str) -> tuple[str | None, dict[str, Any] | None]:
    profiles = _profile_items(payload)
    wanted = profile_name.strip().casefold()
    for key, value in profiles.items():
        if not isinstance(value, dict):
            continue
        names = [value.get("cute_name"), value.get("profile_name"), value.get("name"), key]
        if any(isinstance(name, str) and name.casefold() == wanted for name in names):
            return str(key), value
    return None, None


@mcp.tool()
async def lookup_skyblock_profile(username: str, profile_name: str = "Peach") -> dict[str, Any]:
    """Fetch a public SkyBlock profile through SkyCrypt and select a profile by cute name."""
    safe_username = _valid_username(username)
    if not safe_username:
        return {"ok": False, "error": "Enter a valid Minecraft username (up to 16 letters, numbers or underscores)."}
    if not profile_name.strip() or len(profile_name) > 40:
        return {"ok": False, "error": "Enter a valid profile name, such as Peach."}
    url = f"{SKYCRYPT_API.rstrip('/')}/{quote(safe_username, safe='')}"
    profile_url = f"https://sky.shiiyu.moe/stats/{quote(safe_username, safe='')}/{quote(profile_name.strip(), safe='')}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers=HEADERS)
        if response.status_code == 404:
            return {"ok": False, "username": safe_username, "profile_name": profile_name, "error": "No public profile was found. Check the username or profile visibility.", "profile_url": profile_url}
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, (dict, list)):
            return {"ok": False, "username": safe_username, "error": "The profile API returned an unexpected response format.", "profile_url": profile_url}
        profile_key, selected = _find_profile(payload, profile_name)
        return {
            "ok": True, "username": safe_username, "requested_profile": profile_name,
            "matched_profile_key": profile_key, "profile_found": selected is not None,
            "source": "SkyCrypt public profile API", "source_url": url, "profile_url": profile_url,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(), "profile": selected,
            "available_profiles": [
                {"key": str(key), "cute_name": value.get("cute_name"), "selected": value.get("current", value.get("selected"))}
                for key, value in _profile_items(payload).items() if isinstance(value, dict)
            ],
            "note": "Profile fields depend on the upstream API response and privacy settings. Missing values are not inferred."
        }
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "username": safe_username, "error": f"SkyCrypt returned HTTP {exc.response.status_code}.", "profile_url": profile_url, "source_url": url}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "username": safe_username, "error": f"Profile lookup failed ({type(exc).__name__}). The upstream API may be unavailable or have changed.", "profile_url": profile_url, "source_url": url}


@mcp.tool()
async def get_bazaar_prices(item_id: str = "") -> dict[str, Any]:
    """Retrieve Hypixel Bazaar prices, optionally filtered by product ID; never embeds an API key."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            response = await client.get(HYPIXEL_BAZAAR_API, headers=HEADERS)
        if response.status_code in (401, 403):
            return {"ok": False, "error": "Hypixel requires API authentication for this request. This public-only starter does not store an API key.", "source_url": "https://developer.hypixel.net/"}
        response.raise_for_status()
        payload = response.json()
        products = payload.get("products", {}) if isinstance(payload, dict) else {}
        if item_id:
            key = item_id.strip().upper()
            product = products.get(key)
            if not product:
                return {"ok": False, "error": "No matching Bazaar product ID found.", "searched_id": key, "source_url": HYPIXEL_BAZAAR_API}
            products = {key: product}
        compact = {}
        for key, product in products.items():
            quick = product.get("quick_status", {}) if isinstance(product, dict) else {}
            compact[key] = {"buy_price": quick.get("buyPrice"), "sell_price": quick.get("sellPrice"), "buy_volume": quick.get("buyVolume"), "sell_volume": quick.get("sellVolume"), "buy_orders": quick.get("buyOrders"), "sell_orders": quick.get("sellOrders")}
        return {"ok": True, "source": "Hypixel API", "source_url": HYPIXEL_BAZAAR_API, "last_updated": payload.get("lastUpdated"), "count": len(compact), "products": compact}
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "error": f"Hypixel Bazaar endpoint returned HTTP {exc.response.status_code}.", "source_url": HYPIXEL_BAZAAR_API}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "error": f"Bazaar lookup failed ({type(exc).__name__}). Endpoint access or service availability may have changed.", "source_url": HYPIXEL_BAZAAR_API}


@mcp.tool()
def build_progression_plan(goal: str, current_progress: str = "", budget_coins: int = 0) -> dict[str, Any]:
    """Create a checklist from a goal and progress the player chooses to provide."""
    goal = goal.strip()
    if not goal:
        return {"ok": False, "error": "Tell me the goal you want to work towards."}
    try:
        budget = max(0, int(budget_coins))
    except (ValueError, TypeError):
        budget = 0
    return {"ok": True, "goal": goal, "current_progress": current_progress.strip() or "Not provided yet", "budget_coins": budget, "plan": ["Confirm the exact unlock, item or milestone required.", "Check public profile data and its last-save time where available.", "Compare the lowest-cost route with the fastest practical route.", "Turn the route into a checklist and update it as progress changes."], "note": "This initial planner does not persist data or claim to know stats that were not retrieved."}


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http")
