"""Official read-only Whop clipping/UGC bounty observations.

Bounties pay fixed rewards for accepted work. They are not silently treated as
CPM Content Rewards campaigns, and API visibility does not verify account,
rights, payout, social-platform or publication eligibility.
"""
from __future__ import annotations

import math
import re
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from urllib.parse import urlsplit

import httpx

from .integrations import IntegrationError

API_BASE = "https://api.whop.com/api/v1"
API_VERSION_DATE = "2026-10-28"
MAX_RESPONSE_BYTES = 2_000_000
DOCUMENTED_GOALS = {"clipping", "ugc_content"}


class WhopError(IntegrationError):
    """Sanitized read-only discovery error; response bodies are never logged."""


def broker_origin(value: str) -> str:
    """Initial hosting is an owner-configured HTTPS Workers origin, never input from a campaign."""
    try:
        parsed = urlsplit(value)
        valid_port = parsed.port in {None, 443}
    except (ValueError, TypeError):
        raise WhopError("Configure the deployed HTTPS Whop Workers origin") from None
    if (parsed.scheme != "https" or not parsed.hostname or not valid_port
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or not parsed.hostname.endswith(".workers.dev")
            or not re.fullmatch(r"[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev", parsed.hostname)
            or any(character.isspace() for character in value)):
        raise WhopError("Configure the deployed HTTPS Whop Workers origin")
    return "https://" + parsed.hostname


def _token(value: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 32768
            or any(character.isspace() for character in value)):
        raise WhopError("Authorize Whop through secure credential configuration")
    return value


def _country(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value):
        raise WhopError("A two-letter creator residency country code is required")
    return value.upper()


def _amount(record: dict, key: str) -> float:
    value = record.get(key)
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0):
        raise WhopError("Whop returned an invalid fixed-reward amount")
    return value


def _count(record: dict, key: str) -> int:
    value = record.get(key)
    if type(value) is not int or value < 0 or value > 2**63 - 1:
        raise WhopError("Whop returned an invalid bounty slot count")
    return value


def bounty_observation(record: dict, country: str) -> dict:
    """Keep provider observations separate from verified CPM campaign evidence."""
    if not isinstance(record, dict):
        raise WhopError("Whop returned an invalid bounty record")
    identifier = record.get("id")
    if not isinstance(identifier, str) or not re.fullmatch(r"bnty_[A-Za-z0-9_-]{1,160}", identifier):
        raise WhopError("Whop returned an invalid bounty identifier")
    if not isinstance(record.get("title"), str) or not record["title"].strip():
        raise WhopError("Whop returned an invalid bounty title")
    if record.get("status") not in {"scheduled", "open", "closed", "completed", "canceled"}:
        raise WhopError("Whop returned an unknown bounty lifecycle state")
    countries = record.get("allowed_country_codes")
    if not isinstance(countries, list):
        raise WhopError("Whop did not return creator residency rules")
    normalized_countries = [_country(value) for value in countries]
    currency = record.get("currency")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
        raise WhopError("Whop did not return a valid reward currency")
    goal = record.get("business_goal_type")
    if goal is not None and not isinstance(goal, str):
        raise WhopError("Whop returned an invalid bounty goal")
    return {
        "provider": "whop",
        "id": identifier,
        "title": record["title"],
        "source_api_url": API_BASE + "/bounties/" + identifier,
        "pricing_model": "fixed_reward_per_approved_submission",
        "currency": currency.upper(),
        "gross_reward_amount": _amount(record, "gross_reward_amount"),
        "quoted_net_reward_amount": _amount(record, "net_reward_amount"),
        "total_gross_budget_amount": _amount(record, "budget_amount"),
        "gross_paid_out_amount": _amount(record, "gross_paid_out_amount"),
        "accepted_submissions_count": _count(record, "accepted_submissions_count"),
        "accepted_submissions_limit": _count(record, "accepted_submissions_limit"),
        "unresolved_submissions_count": _count(record, "unresolved_submissions_count"),
        "spots_remaining": _count(record, "spots_remaining"),
        "status": record["status"],
        "business_goal_type": goal,
        "creator_country_requested": country,
        "allowed_creator_country_codes": normalized_countries,
        "provider_reports_country_match": not normalized_countries or country in normalized_countries,
        "new_account_eligibility_verified": False,
        "rights_verified": False,
        "payout_verified": False,
        "publication_approved": False,
        "raw": record,
    }


class WhopBounties:
    """List creator-visible fixed-reward opportunities using official GET only.

    Prefer the private cloud broker, which owns the PKCE grant and durable
    rotation. A manual access token remains optional. Request only the owner's
    verified read-only ``bounty:basic:read`` scope, supported by the issuer's
    live OAuth metadata and the official List Bounties contract.
    An account API key has different account-scoped reach. No writes are made.
    """

    def __init__(self, access_token: str = "", *, broker_url: str = "", broker_token: str = "",
                 client: httpx.AsyncClient | None = None, api_version_date: str = API_VERSION_DATE):
        if broker_url or broker_token:
            self._base = broker_origin(broker_url) + "/api"
            self._access_token = _token(broker_token)
        else:
            self._base = API_BASE
            self._access_token = _token(access_token)
        try:
            parsed_date = date.fromisoformat(api_version_date)
        except (TypeError, ValueError):
            raise WhopError("A verified ISO API version date is required") from None
        if parsed_date.isoformat() != api_version_date:
            raise WhopError("A verified ISO API version date is required")
        self._http = client
        self.api_version_date = api_version_date

    @asynccontextmanager
    async def _client(self):
        if self._http is not None:
            yield self._http
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                yield client

    async def _page(self, params: dict) -> dict:
        try:
            async with self._client() as client:
                async with client.stream(
                    "GET", self._base + "/bounties", params=params,
                    headers={"Authorization": "Bearer " + self._access_token,
                             "Api-Version-Date": self.api_version_date},
                    follow_redirects=False, timeout=30,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise WhopError("Whop discovery requires owner authorization with the verified bounty:basic:read scope")
                    if not 200 <= response.status_code < 300:
                        raise WhopError(f"Whop discovery returned HTTP {response.status_code}")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > MAX_RESPONSE_BYTES:
                            raise WhopError("Whop discovery response exceeded its size limit")
            import json
            result = json.loads(payload)
        except httpx.HTTPError:
            raise WhopError("Whop discovery could not complete; check permitted HTTPS access") from None
        except (ValueError, UnicodeError):
            raise WhopError("Whop discovery returned invalid JSON") from None
        if not isinstance(result, dict):
            raise WhopError("Whop discovery returned an invalid page")
        return result

    async def list_open_bounties(self, country: str = "JO", business_goal_type: str = "clipping", *,
                                first: int = 100, max_pages: int = 5) -> dict:
        country = _country(country)
        if business_goal_type not in DOCUMENTED_GOALS:
            raise WhopError("Discovery supports only documented clipping or UGC bounty goals")
        if type(first) is not int or not 1 <= first <= 100 or type(max_pages) is not int or not 1 <= max_pages <= 20:
            raise WhopError("Use 1..100 results per page and 1..20 pages")
        params = {"status": "open", "business_goal_type": business_goal_type,
                  "country": country, "first": first}
        observations, identifiers, cursors = [], set(), set()
        complete = False
        pages_fetched = 0
        for _ in range(max_pages):
            page = await self._page(params)
            records, page_info = page.get("data"), page.get("page_info")
            if (not isinstance(records, list) or len(records) > first or not isinstance(page_info, dict)
                    or type(page_info.get("has_next_page")) is not bool):
                raise WhopError("Whop returned invalid discovery pagination")
            for record in records:
                observation = bounty_observation(record, country)
                if observation["id"] in identifiers:
                    raise WhopError("Whop discovery repeated a bounty; inspect pagination before ranking")
                identifiers.add(observation["id"])
                observations.append(observation)
            pages_fetched += 1
            if not page_info["has_next_page"]:
                complete = True
                break
            cursor = page_info.get("end_cursor")
            if (not isinstance(cursor, str) or not cursor or len(cursor) > 4096
                    or any(character.isspace() for character in cursor) or cursor in cursors):
                raise WhopError("Whop discovery returned a missing or repeated cursor")
            cursors.add(cursor)
            params = dict(params, after=cursor)
        return {"provider": "whop", "pricing_model": "fixed_reward_per_approved_submission",
                "observed_at": datetime.now(UTC).isoformat(), "api_version_date": self.api_version_date,
                "country_filter": country, "business_goal_type": business_goal_type,
                "pages_fetched": pages_fetched, "pagination_complete": complete,
                "observations": observations, "eligible_campaigns_verified": False,
                "live_publication_performed": False}
