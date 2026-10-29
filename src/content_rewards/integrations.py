"""Official API transport adapters. Callers enforce campaign and publication approvals.

No adapter refreshes credentials, invents campaign endpoints, retries publication
writes, or calls a paid content-generation API. Tokens are never put in URLs.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

import httpx


class IntegrationError(RuntimeError):
    """A sanitized provider error that is safe to display in status output."""


class IndeterminatePublishError(IntegrationError):
    """A publication may have succeeded; reconcile before attempting it again."""


def _https_url(value: str, expected_host: str | None = None) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise IntegrationError("A valid public HTTPS URL is required") from None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.fragment
        or host == "localhost"
        or "." not in host
        or host.endswith((".localhost", ".local", ".internal", ".test"))
    ):
        raise IntegrationError("A valid public HTTPS URL is required")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise IntegrationError("A valid public HTTPS URL is required")
    if expected_host is not None and host != expected_host.lower():
        raise IntegrationError("URL does not match the configured provider host")
    return value


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise IntegrationError("Invalid provider identifier")
    return quote(value, safe="")


def _youtube_count(value: object) -> int:
    """YouTube statistics are unsigned integer counters, never coercible values."""
    if type(value) is int:
        count = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]{1,20}", value):
        count = int(value)
    else:
        raise IntegrationError("YouTube returned invalid statistics")
    if not 0 <= count <= 2**64 - 1:
        raise IntegrationError("YouTube returned invalid statistics")
    return count


class _Adapter:
    provider = "provider"

    def __init__(self, access_token: str, client: httpx.AsyncClient | None = None, *, token_provider=None):
        if not access_token or not access_token.strip() or "\n" in access_token or "\r" in access_token:
            raise IntegrationError("An authorized access token is required")
        self._access_token = access_token
        self._http = client
        self._token_provider = token_provider

    @asynccontextmanager
    async def _client(self):
        if self._http is not None:
            yield self._http
        else:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=20), follow_redirects=False) as client:
                yield client

    async def _request(self, method: str, url: str, *, indeterminate: bool = False, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        token = await self._token_provider.get_access_token() if self._token_provider else self._access_token
        headers["Authorization"] = "Bearer " + token
        try:
            async with self._client() as client:
                response = await client.request(method, url, headers=headers, follow_redirects=False, **kwargs)
        except httpx.HTTPError:
            error = IndeterminatePublishError if indeterminate else IntegrationError
            raise error(f"{self.provider} request failed; {'reconcile before retrying' if indeterminate else 'check connectivity and authorization'}") from None
        if response.status_code == 401 and self._token_provider and hasattr(self._token_provider, "invalidate"):
            # Renewal happens on the next operation. Never replay a publication write.
            self._token_provider.invalidate()
        if response.status_code >= 500 and indeterminate:
            raise IndeterminatePublishError(f"{self.provider} returned HTTP {response.status_code}; reconcile before retrying")
        if not 200 <= response.status_code < 300:
            raise IntegrationError(f"{self.provider} returned HTTP {response.status_code}")
        return response

    def _json(self, response: httpx.Response, *, indeterminate: bool = False) -> dict:
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise TypeError
            return result
        except (ValueError, UnicodeError, TypeError):
            error = IndeterminatePublishError if indeterminate else IntegrationError
            raise error(f"{self.provider} returned an invalid response") from None

    def _id(self, response: httpx.Response, *, indeterminate: bool = False) -> str:
        value = self._json(response, indeterminate=indeterminate).get("id")
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            error = IndeterminatePublishError if indeterminate else IntegrationError
            raise error(f"{self.provider} response did not contain a valid identifier")
        return value


class YouTubePublisher(_Adapter):
    """YouTube Data API v3 resumable upload. Default uploads remain private."""

    provider = "YouTube"
    api_base = "https://www.googleapis.com/youtube/v3"

    def __init__(self, access_token: str, client: httpx.AsyncClient | None = None, *, privacy_status: Literal["private", "unlisted", "public"] = "private", token_provider=None):
        super().__init__(access_token, client, token_provider=token_provider)
        if privacy_status not in ("private", "unlisted", "public"):
            raise IntegrationError("Invalid YouTube privacy status")
        self.privacy_status = privacy_status

    async def verify_account(self) -> dict:
        response = await self._request("GET", self.api_base + "/channels", params={"part": "snippet,status", "mine": "true"})
        items = self._json(response).get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise IntegrationError("YouTube authorization did not identify one channel")
        _identifier(items[0].get("id"))
        return items[0]

    async def upload(self, path: Path, title: str, description: str) -> str:
        path = Path(path)
        if not path.is_file() or path.stat().st_size == 0 or path.suffix.lower() != ".mp4":
            raise IntegrationError("A nonempty local MP4 file is required")
        if not title.strip() or len(title) > 100 or len(description.encode("utf-8")) > 5000:
            raise IntegrationError("YouTube title or description exceeds the supported limits")
        size = path.stat().st_size
        response = await self._request(
            "POST", "https://www.googleapis.com/upload/youtube/v3/videos",
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"},
            json={"snippet": {"title": title, "description": description, "categoryId": "22"}, "status": {"privacyStatus": self.privacy_status}},
        )
        location = response.headers.get("Location", "")
        _https_url(location, "www.googleapis.com")
        if not urlsplit(location).path.startswith("/upload/youtube/v3/videos"):
            raise IntegrationError("YouTube returned an unexpected resumable upload URL")

        async def chunks() -> AsyncIterator[bytes]:
            source = await asyncio.to_thread(path.open, "rb")
            try:
                while chunk := await asyncio.to_thread(source.read, 1024 * 1024):
                    yield chunk
            finally:
                await asyncio.to_thread(source.close)

        completed = await self._request(
            "PUT", location, headers={"Content-Type": "video/mp4", "Content-Length": str(size)},
            content=chunks(), indeterminate=True,
        )
        return self._id(completed, indeterminate=True)

    async def metrics(self, video_id: str) -> dict:
        response = await self._request("GET", self.api_base + "/videos", params={"part": "statistics", "id": _identifier(video_id)})
        items = self._json(response).get("items")
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
            raise IntegrationError("YouTube video statistics are unavailable")
        stats = items[0].get("statistics")
        if not isinstance(stats, dict) or "viewCount" not in stats:
            raise IntegrationError("YouTube did not return view statistics")
        result = {"views": _youtube_count(stats["viewCount"])}
        for source, target in (("likeCount", "likes"), ("commentCount", "comments")):
            if source in stats:
                result[target] = _youtube_count(stats[source])
        return result


class InstagramPublisher(_Adapter):
    """Instagram API with Instagram Login, for authorized professional accounts."""

    provider = "Instagram"

    def __init__(self, access_token: str, account_id: str, api_version: str, client: httpx.AsyncClient | None = None):
        super().__init__(access_token, client)
        self.account_id = _identifier(account_id)
        if not re.fullmatch(r"v\d{2}\.\d+", api_version):
            raise IntegrationError("An explicitly verified Instagram API version is required")
        self.api_base = "https://graph.instagram.com/" + api_version

    async def verify_account(self) -> dict:
        # Instagram Login's `id` is app-scoped; `user_id` identifies the
        # professional publishing account. /me binds the response to this token.
        response = await self._request("GET", self.api_base + "/me", params={"fields": "user_id,username,account_type"})
        result = self._json(response)
        if "data" in result:
            accounts = result["data"]
            if not isinstance(accounts, list) or len(accounts) != 1 or not isinstance(accounts[0], dict):
                raise IntegrationError("Instagram authorization did not identify one professional account")
            result = accounts[0]
        user_id = result.get("user_id")
        if (isinstance(user_id, bool) or not isinstance(user_id, (str, int))
                or str(user_id) != self.account_id):
            raise IntegrationError("Instagram authorization did not match the configured account")
        account_type = result.get("account_type")
        if not isinstance(account_type, str) or account_type.upper() not in ("BUSINESS", "MEDIA_CREATOR"):
            raise IntegrationError("Instagram publishing requires a professional account")
        return {"id": str(user_id), "user_id": str(user_id), "username": result.get("username"),
                "account_type": account_type.upper()}

    async def publishing_capacity(self) -> dict:
        """Read this account's current quota; never assume a universal post limit."""
        response = await self._request(
            "GET", self.api_base + "/" + self.account_id + "/content_publishing_limit",
            params={"fields": "quota_usage,config"},
        )
        entries = self._json(response).get("data")
        try:
            if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
                raise ValueError
            usage = entries[0]["quota_usage"]
            config = entries[0]["config"]
            total, duration = config["quota_total"], config["quota_duration"]
            if (any(type(value) is not int or not 0 <= value <= 2**64 - 1
                    for value in (usage, total, duration)) or duration == 0):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise IntegrationError("Instagram publishing capacity is unavailable or invalid") from None
        return {"quota_usage": usage, "quota_total": total, "quota_duration": duration,
                "remaining": max(0, total - usage)}

    async def require_publishing_capacity(self):
        if (await self.publishing_capacity())["remaining"] == 0:
            raise IntegrationError("Instagram publishing capacity is exhausted; wait before creating or publishing content")

    async def create_container(self, video_url: str, caption: str) -> str:
        _https_url(video_url)
        if len(caption) > 2200:
            raise IntegrationError("Instagram caption exceeds the supported limit")
        response = await self._request("POST", self.api_base + "/" + self.account_id + "/media", data={"media_type": "REELS", "video_url": video_url, "caption": caption})
        return self._id(response)

    async def container_status(self, container_id: str) -> str:
        response = await self._request("GET", self.api_base + "/" + _identifier(container_id), params={"fields": "status_code"})
        result = self._json(response).get("status_code")
        if result not in ("EXPIRED", "ERROR", "FINISHED", "IN_PROGRESS", "PUBLISHED"):
            raise IntegrationError("Instagram returned an unknown container state")
        return result

    async def publish_container(self, container_id: str) -> str:
        response = await self._request("POST", self.api_base + "/" + self.account_id + "/media_publish", data={"creation_id": _identifier(container_id)}, indeterminate=True)
        return self._id(response, indeterminate=True)

    async def metrics(self, media_id: str) -> dict:
        response = await self._request("GET", self.api_base + "/" + _identifier(media_id) + "/insights", params={"metric": "views,likes,comments,saved,shares,reach"})
        entries = self._json(response).get("data")
        if not isinstance(entries, list):
            raise IntegrationError("Instagram returned invalid insights")
        result = {}
        try:
            for item in entries:
                name = item["name"]
                value = item["values"][0]["value"]
                if name in ("views", "likes", "comments", "saved", "shares", "reach"):
                    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                        raise ValueError
                    result[name] = value
            if "views" not in result:
                raise ValueError
            return result
        except (KeyError, IndexError, TypeError, ValueError):
            raise IntegrationError("Instagram view insights are unavailable or invalid") from None


class EvidenceFeed:
    """Read an explicitly configured HTTPS JSON feed; payloads remain untrusted.

    DNS and egress controls must also restrict this configured destination. No
    redirects are followed and no credentials are sent. A feed cannot authorize
    publication or establish country eligibility merely by asserting booleans.
    """

    def __init__(self, expected_host: str, client: httpx.AsyncClient | None = None):
        _https_url("https://" + expected_host)
        self.expected_host = expected_host.lower()
        self._http = client

    async def fetch(self, url: str) -> list[dict]:
        _https_url(url, self.expected_host)
        async with self._client() as client:
            try:
                async with client.stream("GET", url, timeout=30, follow_redirects=False) as response:
                    if response.status_code != 200:
                        raise IntegrationError(f"Campaign feed returned HTTP {response.status_code}")
                    payload = bytearray()
                    async for chunk in response.aiter_bytes():
                        payload.extend(chunk)
                        if len(payload) > 2_000_000:
                            raise IntegrationError("Campaign feed exceeded the size limit")
                data = json.loads(payload)
            except httpx.HTTPError:
                raise IntegrationError("Campaign feed request failed") from None
            except (ValueError, UnicodeError):
                raise IntegrationError("Campaign feed returned invalid JSON") from None
        if isinstance(data, dict):
            data = data.get("campaigns")
        if not isinstance(data, list) or len(data) > 1000 or any(not isinstance(item, dict) for item in data):
            raise IntegrationError("Campaign feed must contain at most 1000 campaign objects")
        return [dict(item, eligibility_verified=False, requirements_verified=False, rights_verified=False,
                     payout_eligibility_verified=False, automation_authorized=False, evidence_checked_at=None) for item in data]

    @asynccontextmanager
    async def _client(self):
        if self._http is not None:
            yield self._http
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                yield client
