"""In-memory OAuth lifecycle helpers. Credentials never appear in URLs or logs.

Google's authorization URL includes its public client ID, state and PKCE
challenge. Client secrets, authorization codes, refresh tokens and access tokens
are sent only in HTTPS form bodies to Google's fixed token endpoint.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import secrets
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .integrations import IntegrationError

GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
)


class OAuthError(IntegrationError):
    """A sanitized authorization/configuration error, safe for status output."""


def _credential(value: str, label: str) -> str:
    if (not isinstance(value, str) or not value or len(value) > 32_768
            or any(character.isspace() for character in value)):
        raise OAuthError(f"A valid {label} is required through secure configuration")
    return value


def _aware_expiry(value: datetime | None) -> datetime | None:
    if value is not None and (not isinstance(value, datetime) or value.tzinfo is None
                              or value.utcoffset() is None):
        raise OAuthError("Credential expiry must be a timezone-aware datetime")
    return value


@dataclass(frozen=True)
class OAuthTokens:
    """Sensitive fields are deliberately omitted from repr; never serialize to logs."""

    access_token: str = field(repr=False)
    expires_in: int
    refresh_token: str | None = field(default=None, repr=False)
    scope: str | None = field(default=None, repr=False)


def _parse_tokens(response: httpx.Response, *, require_refresh: bool = False,
                  required_scopes: tuple[str, ...] = ()) -> OAuthTokens:
    if not 200 <= response.status_code < 300:
        # Bodies may contain credentials, account information or echoed requests.
        if response.status_code in (400, 401, 403):
            raise OAuthError("Google authorization was rejected; check secure bindings or reconnect the account")
        raise OAuthError("Google token request failed; check connectivity and service availability")
    if len(response.content) > 65_536:
        raise OAuthError("Google returned an invalid token response")
    try:
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError
        access_token = _credential(payload["access_token"], "access token")
        expires_in = payload["expires_in"]
        if (isinstance(expires_in, bool) or not isinstance(expires_in, int)
                or not 0 < expires_in <= 31_536_000
                or payload.get("token_type", "").lower() != "bearer"):
            raise ValueError
        refresh_token = payload.get("refresh_token")
        if refresh_token is not None:
            refresh_token = _credential(refresh_token, "refresh token")
        scope = payload.get("scope")
        if scope is not None and not isinstance(scope, str):
            raise TypeError
    except (KeyError, TypeError, ValueError, AttributeError, OAuthError):
        raise OAuthError("Google returned an invalid token response") from None
    if require_refresh and not refresh_token:
        raise OAuthError("Google did not return offline access; reconnect with owner consent")
    if required_scopes and (not scope or not set(required_scopes).issubset(scope.split())):
        raise OAuthError("Google did not confirm the requested YouTube upload and readonly permissions")
    return OAuthTokens(access_token=access_token, expires_in=expires_in,
                       refresh_token=refresh_token, scope=scope)


@asynccontextmanager
async def _http_client(client: httpx.AsyncClient | None):
    if client is not None:
        yield client
    else:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as owned:
            yield owned


async def _token_request(data: dict[str, str], client: httpx.AsyncClient | None) -> httpx.Response:
    try:
        async with _http_client(client) as http:
            return await http.post(GOOGLE_TOKEN_ENDPOINT, data=data, follow_redirects=False, timeout=30)
    except httpx.HTTPError:
        raise OAuthError("Google token request could not complete; check HTTPS connectivity") from None


class StaticTokenProvider:
    """An existing owner-authorized token; unknown expiry is not a renewal claim."""

    renewable = False

    def __init__(self, access_token: str, *, expires_at: datetime | None = None):
        self._access_token = _credential(access_token, "access token")
        self.expires_at = _aware_expiry(expires_at)

    async def get_access_token(self) -> str:
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            raise OAuthError("The configured access token expired; renew authorization through secure settings")
        return self._access_token


class YouTubeTokenProvider:
    """Refresh offline Google authorization before expiry, with one refresh in flight.

    The cache exists only in this process. No credential values are written to
    the database, filesystem, command output, request URL or exception text.
    Failed refreshes are never silently replaced by an expired/unknown token.
    """

    renewable = True

    def __init__(self, client_id: str, client_secret: str, refresh_token: str, *,
                 access_token: str | None = None, expires_at: datetime | None = None,
                 client: httpx.AsyncClient | None = None, clock: Callable[[], float] = time.monotonic):
        self._client_id = _credential(client_id, "Google client ID")
        self._client_secret = _credential(client_secret, "Google client secret")
        self._refresh_token = _credential(refresh_token, "Google refresh token")
        self._access_token = _credential(access_token, "access token") if access_token else None
        self._http = client
        self._clock = clock
        self._lock = asyncio.Lock()
        self._valid_until = 0.0
        expires_at = _aware_expiry(expires_at)
        if self._access_token and expires_at:
            remaining = (expires_at - datetime.now(UTC)).total_seconds()
            if remaining > 0:
                self._valid_until = clock() + remaining - min(60, remaining * 0.1)

    def invalidate(self):
        """Discard a cached token; never retry a publication write automatically."""
        self._access_token = None
        self._valid_until = 0.0

    def _cached(self) -> bool:
        instant = self._clock()
        if not math.isfinite(instant):
            raise OAuthError("Credential cache clock is invalid")
        return bool(self._access_token and instant < self._valid_until)

    async def get_access_token(self) -> str:
        if self._cached():
            return self._access_token
        async with self._lock:
            if self._cached():
                return self._access_token
            # Never use the old token after this point if refreshing fails.
            self.invalidate()
            request_started = self._clock()
            response = await _token_request({
                "grant_type": "refresh_token", "client_id": self._client_id,
                "client_secret": self._client_secret, "refresh_token": self._refresh_token,
            }, self._http)
            tokens = _parse_tokens(response)
            # A refresh response may omit scope when it is unchanged. When it
            # explicitly returns scope, never cache a reduced authorization.
            if tokens.scope is not None and not set(YOUTUBE_SCOPES).issubset(tokens.scope.split()):
                raise OAuthError("Google no longer confirms the requested YouTube upload and readonly permissions")
            received = self._clock()
            if not math.isfinite(received) or received < request_started:
                raise OAuthError("Credential cache clock is invalid")
            valid_until = request_started + tokens.expires_in - min(60, tokens.expires_in * 0.1)
            if received >= valid_until:
                raise OAuthError("Google token response arrived too late for safe use; authorization was not cached")
            # Google normally does not rotate this refresh token. If it returns
            # one, use it for this process only; don't silently persist secrets.
            if tokens.refresh_token:
                self._refresh_token = tokens.refresh_token
            self._access_token = tokens.access_token
            self._valid_until = valid_until
            return self._access_token


class GoogleAuthorizationSession:
    """Single-use PKCE/state consent session for an owner-operated loopback flow.

    A caller must run the legitimate loopback callback capture in the SAME
    process. Do not paste authorization codes or callback URLs into chat.
    This helper never opens a browser or starts a server by itself.
    """

    def __init__(self, client_id: str, *, redirect_uri: str = "http://127.0.0.1:8765/oauth/callback"):
        self._client_id = _credential(client_id, "Google client ID")
        try:
            parsed = urlsplit(redirect_uri)
            port = parsed.port
        except ValueError:
            raise OAuthError("A registered loopback redirect URI is required") from None
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or port is None or parsed.username or parsed.password or parsed.query or parsed.fragment
                or not parsed.path.startswith("/")):
            raise OAuthError("A registered loopback redirect URI is required")
        self.redirect_uri = redirect_uri
        self._redirect = (parsed.scheme, parsed.netloc, parsed.path)
        self._state = secrets.token_urlsafe(32)
        self._verifier = secrets.token_urlsafe(64)
        self._consumed = False

    @property
    def authorization_url(self) -> str:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(self._verifier.encode()).digest()).rstrip(b"=").decode()
        return GOOGLE_AUTHORIZATION_ENDPOINT + "?" + urlencode({
            "client_id": self._client_id, "redirect_uri": self.redirect_uri,
            "response_type": "code", "scope": " ".join(YOUTUBE_SCOPES),
            "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
            "state": self._state, "code_challenge": challenge, "code_challenge_method": "S256",
        })

    async def exchange(self, callback_url: str, client_secret: str, *,
                       client: httpx.AsyncClient | None = None) -> OAuthTokens:
        if self._consumed:
            raise OAuthError("This authorization session was already used; start a new consent session")
        client_secret = _credential(client_secret, "Google client secret")
        try:
            callback = urlsplit(callback_url)
            values = parse_qs(callback.query, keep_blank_values=True, strict_parsing=True)
        except (ValueError, TypeError):
            raise OAuthError("The OAuth callback is invalid") from None
        if ((callback.scheme, callback.netloc, callback.path) != self._redirect or callback.fragment
                or len(values.get("state", [])) != 1
                or not secrets.compare_digest(values["state"][0].encode(), self._state.encode())):
            raise OAuthError("The OAuth callback did not match the active consent session")
        self._consumed = True
        if "error" in values:
            raise OAuthError("Google consent was not completed; start a new owner authorization session")
        codes = values.get("code", [])
        if len(codes) != 1:
            raise OAuthError("The OAuth callback did not contain a single authorization code")
        code = _credential(codes[0], "authorization code")
        response = await _token_request({
            "grant_type": "authorization_code", "client_id": self._client_id,
            "client_secret": client_secret, "code": code, "redirect_uri": self.redirect_uri,
            "code_verifier": self._verifier,
        }, client)
        return _parse_tokens(response, require_refresh=True, required_scopes=YOUTUBE_SCOPES)
