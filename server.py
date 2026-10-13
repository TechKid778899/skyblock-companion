"""SkyBlock Companion: MCP server using Hypixel public game data.

The Hypixel API key is read only from the HYPIXEL_API_KEY environment variable.
"""
from __future__ import annotations
import os
from typing import Any
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    "SkyBlock Companion",
    transport_security=TransportSecuritySettings(
        allowed_hosts=["skyblock-companion.onrender.com", "skyblock-companion.onrender.com:*"],
        allowed_origins=["https://skyblock-companion.onrender.com"],
    ),
)
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
    """Fetch a SkyBlock profile from Hypixel's official API using HYPIXEL_API_KEY."""
    safe_username = _valid_username(username)
    if not safe_username:
        return {"ok": False, "error": "Enter a valid Minecraft username (up to 16 letters, numbers or underscores)."}
    if not profile_name.strip() or len(profile_name) > 40:
        return {"ok": False, "error": "Enter a valid profile name, such as Peach."}
    api_key = os.getenv("HYPIXEL_API_KEY", "").strip()
    profile_url = f"https://sky.shiiyu.moe/stats/{quote(safe_username, safe='')}/{quote(profile_name.strip(), safe='')}"
    if not api_key:
        return {
            "ok": False,
            "username": safe_username,
            "error": "Hypixel API key is not configured. Add HYPIXEL_API_KEY to the server's private environment variables.",
            "profile_url": profile_url,
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            # Resolve the Minecraft username to a UUID using Mojang's public API.
            mojang_response = await client.get(
                f"https://api.mojang.com/users/profiles/minecraft/{quote(safe_username, safe='')}",
                headers=HEADERS,
            )
            if mojang_response.status_code == 404:
                return {"ok": False, "username": safe_username, "error": "Mojang could not find that Minecraft username.", "profile_url": profile_url}
            mojang_response.raise_for_status()
            mojang_data = mojang_response.json()
            uuid = mojang_data.get("id") if isinstance(mojang_data, dict) else None
            if not isinstance(uuid, str) or not uuid:
                return {"ok": False, "username": safe_username, "error": "Mojang returned no UUID for that username.", "profile_url": profile_url}

            # Ask Hypixel for the user's SkyBlock profiles. Never return the API key.
            response = await client.get(
                "https://api.hypixel.net/v2/skyblock/profiles",
                params={"uuid": uuid},
                headers={**HEADERS, "API-Key": api_key},
            )
        if response.status_code == 403:
            return {"ok": False, "username": safe_username, "error": "Hypixel rejected the API key (HTTP 403). Check HYPIXEL_API_KEY in Render and confirm the key is active.", "profile_url": profile_url, "source_url": "https://api.hypixel.net/v2/skyblock/profiles"}
        if response.status_code == 429:
            return {"ok": False, "username": safe_username, "error": "Hypixel API rate limit reached. Wait before retrying.", "profile_url": profile_url}
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            return {"ok": False, "username": safe_username, "error": "Hypixel returned an unsuccessful or unexpected API response.", "profile_url": profile_url}
        profiles = payload.get("profiles") or []
        wanted = profile_name.strip().casefold()
        selected = next((p for p in profiles if isinstance(p, dict) and str(p.get("cute_name", "")).casefold() == wanted), None)
        if selected is None:
            return {
                "ok": False, "username": safe_username, "requested_profile": profile_name,
                "error": "That profile was not returned by Hypixel. It may not exist, may be hidden by in-game API settings, or the profile name may differ.",
                "available_profiles": [{"cute_name": p.get("cute_name"), "profile_id": p.get("profile_id"), "selected": p.get("selected")} for p in profiles if isinstance(p, dict)],
                "profile_url": profile_url, "source": "Hypixel official API",
            }
        members = selected.get("members") or {}
        member = members.get(uuid) if isinstance(members, dict) else None
        return {
            "ok": True, "username": safe_username, "uuid": uuid, "requested_profile": profile_name,
            "matched_profile_key": selected.get("profile_id"), "profile_found": True,
            "source": "Hypixel official SkyBlock API",
            "source_url": "https://api.hypixel.net/v2/skyblock/profiles",
            "profile_url": profile_url, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "profile": selected, "player_member_data": member,
            "available_profiles": [{"cute_name": p.get("cute_name"), "profile_id": p.get("profile_id"), "selected": p.get("selected")} for p in profiles if isinstance(p, dict)],
            "note": "Data availability depends on Hypixel API access and the player's in-game API settings. Missing values are not inferred.",
        }
    except httpx.HTTPStatusError as exc:
        return {"ok": False, "username": safe_username, "error": f"Upstream API returned HTTP {exc.response.status_code}.", "profile_url": profile_url}
    except (httpx.HTTPError, ValueError) as exc:
        return {"ok": False, "username": safe_username, "error": f"Profile lookup failed ({type(exc).__name__}). The upstream API may be unavailable or have changed.", "profile_url": profile_url}


@mcp.tool()
async def get_bazaar_prices(item_id: str = "") -> dict[str, Any]:
    """Retrieve Hypixel Bazaar prices, optionally filtered by product ID; never embeds an API key."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            response = await client.get(HYPIXEL_BAZAAR_API, headers={**HEADERS, **({"API-Key": os.getenv("HYPIXEL_API_KEY", "").strip()} if os.getenv("HYPIXEL_API_KEY", "").strip() else {})})
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


# Progress tracking storage. Set DATA_PATH to a persistent mounted directory on your host
# if progress must survive redeploys/restarts; the default local file may be ephemeral.
DATA_PATH = Path(os.getenv("DATA_PATH", "."))
DB_PATH = DATA_PATH / "skyblock_companion.sqlite3"


def _init_progress_db() -> None:
    DATA_PATH.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                progress_notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


@mcp.tool()
def add_progress_goal(goal: str, details: str = "") -> dict[str, Any]:
    """Save a progression goal so it can be revisited and updated in later chats."""
    goal = goal.strip()
    if not goal or len(goal) > 200:
        return {"ok": False, "error": "Goal must be between 1 and 200 characters."}
    now = datetime.now(timezone.utc).isoformat()
    try:
        _init_progress_db()
        with sqlite3.connect(DB_PATH) as db:
            cursor = db.execute(
                "INSERT INTO goals (goal, details, status, progress_notes, created_at, updated_at) VALUES (?, ?, 'active', '', ?, ?)",
                (goal, details.strip()[:2000], now, now),
            )
            goal_id = cursor.lastrowid
        return {"ok": True, "goal_id": goal_id, "goal": goal, "status": "active", "created_at": now}
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "error": f"Could not save progress goal ({type(exc).__name__}). Check storage configuration."}


@mcp.tool()
def list_progress_goals(include_completed: bool = True) -> dict[str, Any]:
    """List saved progression goals, newest updates first."""
    try:
        _init_progress_db()
        where = "" if include_completed else "WHERE status != 'completed'"
        with sqlite3.connect(DB_PATH) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                f"SELECT id, goal, details, status, progress_notes, created_at, updated_at FROM goals {where} ORDER BY updated_at DESC"
            ).fetchall()
        return {"ok": True, "count": len(rows), "goals": [dict(row) for row in rows]}
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "error": f"Could not read progress goals ({type(exc).__name__}). Check storage configuration."}


@mcp.tool()
def update_progress_goal(goal_id: int, status: str = "", progress_note: str = "") -> dict[str, Any]:
    """Update a saved goal's status and/or append a progress note. Status: active, paused, completed."""
    if goal_id < 1:
        return {"ok": False, "error": "Goal ID must be a positive number."}
    if status and status not in {"active", "paused", "completed"}:
        return {"ok": False, "error": "Status must be active, paused, or completed."}
    if len(progress_note) > 2000:
        return {"ok": False, "error": "Progress note must be 2000 characters or fewer."}
    try:
        _init_progress_db()
        with sqlite3.connect(DB_PATH) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM goals WHERE id = ?", (goal_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": "No saved goal found with that ID."}
            new_status = status or row["status"]
            old_notes = row["progress_notes"] or ""
            if progress_note.strip():
                stamp = datetime.now(timezone.utc).isoformat()
                new_notes = (old_notes + " | " if old_notes else "") + f"[{stamp}] {progress_note.strip()}"
            else:
                new_notes = old_notes
            now = datetime.now(timezone.utc).isoformat()
            db.execute("UPDATE goals SET status = ?, progress_notes = ?, updated_at = ? WHERE id = ?", (new_status, new_notes, now, goal_id))
        return {"ok": True, "goal_id": goal_id, "status": new_status, "updated_at": now, "progress_note_added": bool(progress_note.strip())}
    except (OSError, sqlite3.Error) as exc:
        return {"ok": False, "error": f"Could not update progress goal ({type(exc).__name__}). Check storage configuration."}


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.getenv("PORT", "8000"))
    mcp.run(transport="streamable-http")
