"""Read-only private broker health; no OAuth credentials leave their cloud vault."""
import json

import httpx

from .config import Settings
from .whop import WhopError, _token, broker_origin


async def broker_status(settings: Settings, *, client: httpx.AsyncClient | None = None) -> dict:
    if not settings.whop_broker_url or not settings.whop_broker_token:
        return {"status": "awaiting_owner_cloud_authorization", "requested_scope": "bounty:basic:read",
                "durable_renewal_verified": False, "live_publishing": False}
    origin, token = broker_origin(settings.whop_broker_url), _token(settings.whop_broker_token)
    own_client = client is None
    http = client or httpx.AsyncClient(timeout=30, follow_redirects=False)
    try:
        async with http.stream("GET", origin + "/api/status", headers={"Authorization": "Bearer " + token},
                               follow_redirects=False, timeout=30) as response:
            if response.status_code in {401, 403}:
                raise WhopError("Authorize the owner broker through secure settings")
            if response.status_code != 200:
                raise WhopError(f"Whop broker status returned HTTP {response.status_code}")
            payload = bytearray()
            async for chunk in response.aiter_bytes():
                payload.extend(chunk)
                if len(payload) > 16_384:
                    raise WhopError("Whop broker status exceeded its size limit")
        result = json.loads(payload)
        if not isinstance(result, dict) or result.get("live_publishing") is not False:
            raise WhopError("Whop broker returned an invalid safety status")
        # Explicit fields only: arbitrary upstream bodies/IDs must not enter logs.
        allowed = {"authorized", "renewal_required", "refresh_in_progress", "durable_renewal_verified",
                   "scope_verified", "discovery_verified"}
        return {"status": "reachable", "requested_scope": "bounty:basic:read", "live_publishing": False,
                **{name: result[name] for name in allowed if type(result.get(name)) is bool}}
    except httpx.HTTPError:
        raise WhopError("Whop broker status could not complete; verify permitted HTTPS access") from None
    except (ValueError, UnicodeError):
        raise WhopError("Whop broker returned invalid status JSON") from None
    finally:
        if own_client:
            await http.aclose()
