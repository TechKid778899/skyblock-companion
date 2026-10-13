# SkyBlock Companion — profile dashboard starter

A public-data-first MCP server for a Hypixel SkyBlock companion. This is source code, **not a deployed or connected ChatGPT app**.

## First feature: profile dashboard data

`lookup_skyblock_profile(username, profile_name="Peach")` queries SkyCrypt's public profile API and returns the selected profile payload (when the upstream schema matches), a list of available profiles, retrieval timestamp, and a direct profile link. It does not infer missing fields or bypass privacy settings.

Configured profile:
- Username: `TechKid778899`
- Profile: `Peach`
- Viewer: https://sky.shiiyu.moe/stats/TechKid778899/Peach

Other tools:
- `get_bazaar_prices(item_id?)` calls Hypixel's official Bazaar endpoint without a key; if access is denied, it reports that instead of attempting a workaround.
- `build_progression_plan(goal, current_progress?, budget_coins?)` makes a checklist from player-supplied details.

## Privacy
- No Microsoft/Minecraft credentials, session tokens, or Hypixel API keys are requested, stored, or embedded.
- Profile queries are read-only and limited to publicly available data.
- No profile data is persisted by this starter.
- Upstream APIs may throttle, change schema, or return private/incomplete data.

## Run locally
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

The server is configured for Streamable HTTP on `0.0.0.0:$PORT` (defaults to 8000). Confirm the installed MCP SDK and chosen host support this transport. Verify the actual endpoint path in host logs.

## Cloud hosting
1. Create a Python service in a host that supports a long-running Python process and inbound HTTPS. Free tiers may sleep or have usage limits.
2. Import this repository; install `requirements.txt` and start with `python server.py`.
3. Confirm the host exposes the MCP endpoint and logs contain no startup errors.
4. Test the SkyCrypt profile lookup against the live upstream; its endpoint and response schema must be verified.
5. Connect the HTTPS MCP endpoint through a supported ChatGPT app setup, then test the tool from ChatGPT.
6. Build an actual MCP App view for interactive profile cards. Returning JSON alone is not an interactive in-chat view.

## Verification status
- Python syntax was checked on the starter version.
- Live SkyCrypt API and Hypixel Bazaar access: not verified in this environment.
- Cloud deployment, HTTPS endpoint, ChatGPT connection, and interactive app view: not yet completed.

## References
- SkyCrypt: https://sky.shiiyu.moe/
- SkyCrypt API reference: https://sky.shiiyu.moe/api/v2/
- Hypixel API: https://api.hypixel.net/
- Hypixel API policy: https://developer.hypixel.net/policies/
- Hypixel developer dashboard: https://developer.hypixel.net/
