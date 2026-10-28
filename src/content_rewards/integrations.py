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
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise IntegrationError("YouTube authorization did not identify a channel")
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
        try:
            result = {"views": int(stats["viewCount"])}
            for source, target in (("likeCount", "likes"), ("commentCount", "comments")):
                if source in stats:
                    result[target] = int(stats[source])
            if any(value < 0 for value in result.values()):
                raise ValueError
            return result
        except (ValueError, TypeError):
            raise IntegrationError("YouTube returned invalid statistics") from None


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
        response = await self._request("GET", self.api_base + "/" + self.account_id, params={"fields": "id,username,account_type"})
        result = self._json(response)
        if str(result.get("id", "")) != self.account_id:
            raise IntegrationError("Instagram authorization did not match the configured account")
        if result.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR", "CREATOR"):
            raise IntegrationError("Instagram publishing requires a professional account")
        return result

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
                     payout_eligibility_verified=False, evidence_checked_at=None) for item in data]

    @asynccontextmanager
    async def _client(self):
        if self._http is not None:
            yield self._http
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
                yield client
