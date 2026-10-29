import asyncio
import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from content_rewards.oauth import (
    GOOGLE_TOKEN_ENDPOINT,
    YOUTUBE_SCOPES,
    GoogleAuthorizationSession,
    OAuthError,
    OAuthTokens,
    StaticTokenProvider,
    YouTubeTokenProvider,
)


def response_payload(**updates):
    return {"access_token": "refreshed-secret-token", "expires_in": 3600, "token_type": "Bearer"} | updates


async def test_refresh_uses_fixed_https_form_and_caches_until_early_expiry():
    now = [100.0]
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == GOOGLE_TOKEN_ENDPOINT
        assert request.method == "POST"
        assert request.headers["content-type"] == "application/x-www-form-urlencoded"
        body = parse_qs(request.content.decode())
        assert body == {"grant_type": ["refresh_token"], "client_id": ["public-client"],
                        "client_secret": ["private-client"], "refresh_token": ["private-refresh"]}
        assert "private-client" not in str(request.url) and "private-refresh" not in str(request.url)
        return httpx.Response(200, json=response_payload(access_token=f"access-{len(requests)}"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("public-client", "private-client", "private-refresh", client=client, clock=lambda: now[0])
        assert provider.renewable
        assert await provider.get_access_token() == "access-1"
        now[0] = 3639
        assert await provider.get_access_token() == "access-1"
        now[0] = 3640
        assert await provider.get_access_token() == "access-2"
        assert len(requests) == 2


async def test_concurrent_gets_share_one_refresh_request():
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0.01)
        return httpx.Response(200, json=response_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client)
        results = await asyncio.gather(*(provider.get_access_token() for _ in range(12)))
    assert results == ["refreshed-secret-token"] * 12
    assert len(calls) == 1


async def test_unknown_initial_expiry_forces_refresh_and_known_future_expiry_reuses_token():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        unknown = YouTubeTokenProvider("client", "client-secret", "refresh-secret", access_token="old-secret", client=client)
        assert await unknown.get_access_token() == "refreshed-secret-token"
        known = YouTubeTokenProvider("client", "client-secret", "refresh-secret", access_token="known-token",
                                     expires_at=datetime.now(UTC) + timedelta(hours=1), client=client)
        assert await known.get_access_token() == "known-token"
        assert len(calls) == 1
        known.invalidate()
        assert await known.get_access_token() == "refreshed-secret-token"
        assert len(calls) == 2


async def test_expired_initial_token_is_not_returned_when_refresh_fails():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(400, json={"error": "old-secret"}))) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", access_token="old-secret",
                                        expires_at=datetime.now(UTC) - timedelta(minutes=1), client=client)
        with pytest.raises(OAuthError) as error:
            await provider.get_access_token()
        assert "old-secret" not in str(error.value)
        assert provider._access_token is None


@pytest.mark.parametrize("payload", [
    {}, [], "token-secret", response_payload(access_token=""), response_payload(access_token="token with whitespace"),
    response_payload(access_token="token\r\nheader"), response_payload(expires_in=True),
    response_payload(expires_in=0), response_payload(expires_in=-1), response_payload(expires_in=1.5),
    response_payload(expires_in="3600"), response_payload(expires_in=10**100),
    response_payload(token_type="mac"), response_payload(token_type=None), response_payload(token_type=123),
    response_payload(scope=12), response_payload(refresh_token=""), response_payload(refresh_token="a\nb"),
])
async def test_malformed_success_does_not_cache_credentials(payload):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client)
        with pytest.raises(OAuthError, match="invalid token response") as error:
            await provider.get_access_token()
        assert "token-secret" not in str(error.value)
        assert provider._access_token is None


async def test_invalid_json_and_large_payload_are_redacted():
    for content in (b"not-json-secret", b"x" * 65_537):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content))) as client:
            with pytest.raises(OAuthError, match="invalid token response"):
                await YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client).get_access_token()


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500])
async def test_errors_and_redirects_never_echo_provider_credentials(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error_description": "private-client private-refresh token-secret"},
                              headers={"location": "https://attacker.example/private-refresh"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        with pytest.raises(OAuthError) as error:
            await YouTubeTokenProvider("client", "private-client", "private-refresh", client=client).get_access_token()
    assert len(calls) == 1
    for secret in ("private-client", "private-refresh", "token-secret", "attacker.example"):
        assert secret not in str(error.value)


async def test_network_error_is_sanitized_and_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        raise httpx.ConnectError("private-client private-refresh token-secret")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OAuthError, match="HTTPS connectivity") as error:
            await YouTubeTokenProvider("client", "private-client", "private-refresh", client=client).get_access_token()
    assert len(calls) == 1
    assert "private" not in str(error.value) and "token-secret" not in str(error.value)


async def test_refresh_rotation_used_only_for_later_refresh_in_memory():
    requests = []

    def handler(request):
        requests.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json=response_payload(refresh_token="rotated-refresh"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "initial-refresh", client=client)
        await provider.get_access_token()
        provider.invalidate()
        await provider.get_access_token()
    assert requests[0]["refresh_token"] == ["initial-refresh"]
    assert requests[1]["refresh_token"] == ["rotated-refresh"]
    assert "rotated-refresh" not in repr(provider)


@pytest.mark.parametrize("scope", ["", YOUTUBE_SCOPES[0], YOUTUBE_SCOPES[1], "unrelated"])
async def test_refresh_rejects_explicitly_reduced_scopes_without_caching(scope):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=response_payload(scope=scope)))) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client)
        with pytest.raises(OAuthError, match="no longer confirms"):
            await provider.get_access_token()
        assert provider._access_token is None


async def test_refresh_accepts_confirmed_scopes():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(
            200, json=response_payload(scope=" ".join(YOUTUBE_SCOPES))))) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client)
        assert await provider.get_access_token() == "refreshed-secret-token"


async def test_short_lived_valid_token_is_usable_without_immediate_hot_loop():
    calls = []
    now = [0.0]

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=response_payload(expires_in=1))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client, clock=lambda: now[0])
        await provider.get_access_token()
        await provider.get_access_token()
        now[0] = 0.9
        await provider.get_access_token()
    assert len(calls) == 2


async def test_invalid_clock_is_rejected():
    provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", clock=lambda: float("nan"))
    with pytest.raises(OAuthError, match="clock"):
        await provider.get_access_token()


async def test_response_delay_cannot_make_an_expired_token_look_fresh():
    now = [100.0]
    def handler(request):
        now[0] = 120.0
        return httpx.Response(200, json=response_payload(expires_in=10))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client, clock=lambda: now[0])
        with pytest.raises(OAuthError, match="too late"):
            await provider.get_access_token()
    assert provider._access_token is None


async def test_clock_cannot_move_backwards_during_token_exchange():
    now = [100.0]
    def handler(request):
        now[0] = 90.0
        return httpx.Response(200, json=response_payload())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = YouTubeTokenProvider("client", "client-secret", "refresh-secret", client=client, clock=lambda: now[0])
        with pytest.raises(OAuthError, match="clock"):
            await provider.get_access_token()


@pytest.mark.parametrize("values", [("", "secret", "refresh"), ("client", "", "refresh"),
                                   ("client", "secret", ""), ("client", "secret with space", "refresh")])
def test_missing_or_header_unsafe_credentials_fail_before_network(values):
    with pytest.raises(OAuthError, match="secure configuration"):
        YouTubeTokenProvider(*values)


@pytest.mark.parametrize("provider", [StaticTokenProvider, YouTubeTokenProvider])
def test_naive_expiry_is_rejected(provider):
    args = ["access-token"] if provider is StaticTokenProvider else ["client", "secret", "refresh"]
    with pytest.raises(OAuthError, match="timezone-aware"):
        provider(*args, expires_at=datetime(2026, 1, 1))


async def test_static_tokens_never_claim_renewal_or_reuse_known_expired_value():
    token = StaticTokenProvider("valid-static-token")
    assert not token.renewable
    assert await token.get_access_token() == "valid-static-token"
    expired = StaticTokenProvider("expired-static-token", expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(OAuthError, match="expired") as error:
        await expired.get_access_token()
    assert "expired-static-token" not in str(error.value)


def test_token_objects_never_represent_secret_values():
    tokens = OAuthTokens("private-access", 3600, "private-refresh", "private-provider-scope")
    assert repr(tokens) == "OAuthTokens(expires_in=3600)"
    assert "private" not in repr(StaticTokenProvider("private-access"))


def authorization_parameters(session):
    return parse_qs(urlsplit(session.authorization_url).query)


def callback(session, **updates):
    values = {"state": authorization_parameters(session)["state"][0], "code": "private-authorization-code"} | updates
    return session.redirect_uri + "?" + urlencode(values)


def test_initial_consent_url_has_random_state_pkce_and_minimum_scopes():
    first = GoogleAuthorizationSession("public-client")
    second = GoogleAuthorizationSession("public-client")
    url = urlsplit(first.authorization_url)
    values = authorization_parameters(first)
    assert url.scheme == "https" and url.hostname == "accounts.google.com"
    assert values["client_id"] == ["public-client"]
    assert values["scope"][0].split() == list(YOUTUBE_SCOPES)
    assert values["access_type"] == ["offline"] and values["prompt"] == ["consent"]
    assert values["code_challenge_method"] == ["S256"]
    assert values["state"] != authorization_parameters(second)["state"]
    assert values["code_challenge"] != authorization_parameters(second)["code_challenge"]
    assert first._verifier not in first.authorization_url
    assert "client_secret" not in first.authorization_url and "access_token" not in first.authorization_url


async def test_initial_exchange_verifies_callback_and_sends_matching_pkce_only_in_body():
    session = GoogleAuthorizationSession("public-client")
    parameters = authorization_parameters(session)
    requests = []

    def handler(request):
        requests.append(request)
        values = parse_qs(request.content.decode())
        assert values["grant_type"] == ["authorization_code"]
        assert values["code"] == ["private-authorization-code"]
        assert values["client_secret"] == ["private-client-secret"]
        assert values["redirect_uri"] == [session.redirect_uri]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(values["code_verifier"][0].encode()).digest()).rstrip(b"=").decode()
        assert parameters["code_challenge"] == [challenge]
        assert str(request.url) == GOOGLE_TOKEN_ENDPOINT
        return httpx.Response(200, json=response_payload(refresh_token="offline-refresh", scope=" ".join(YOUTUBE_SCOPES)))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        tokens = await session.exchange(callback(session), "private-client-secret", client=client)
        assert tokens.refresh_token == "offline-refresh" and tokens.access_token == "refreshed-secret-token"
        with pytest.raises(OAuthError, match="already used"):
            await session.exchange(callback(session), "private-client-secret", client=client)
    assert len(requests) == 1


@pytest.mark.parametrize("alter", ["state", "target", "duplicate_state", "fragment", "unicode_state"])
async def test_initial_callback_tampering_never_calls_token_endpoint(alter):
    session = GoogleAuthorizationSession("client")
    url = callback(session)
    if alter == "state":
        url = callback(session, state="attacker-state")
    elif alter == "target":
        url = url.replace("127.0.0.1", "attacker.example")
    elif alter == "duplicate_state":
        url += "&state=another-state"
    elif alter == "fragment":
        url += "#private-token"
    else:
        url = callback(session, state="حالة")
    def handler(request):
        pytest.fail("Tampered callback must not send credentials")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OAuthError, match="match"):
            await session.exchange(url, "secret", client=client)


async def test_owner_denial_and_missing_code_are_sanitized():
    session = GoogleAuthorizationSession("client")
    state = authorization_parameters(session)["state"][0]
    with pytest.raises(OAuthError, match="not completed") as error:
        await session.exchange(session.redirect_uri + "?" + urlencode({"state": state, "error": "private-account-error"}), "secret")
    assert "private-account-error" not in str(error.value)
    missing = GoogleAuthorizationSession("client")
    with pytest.raises(OAuthError, match="single authorization code"):
        await missing.exchange(missing.redirect_uri + "?state=" + authorization_parameters(missing)["state"][0], "secret")


@pytest.mark.parametrize("payload", [response_payload(scope=" ".join(YOUTUBE_SCOPES)),
                                   response_payload(refresh_token="refresh", scope=YOUTUBE_SCOPES[0]),
                                   response_payload(refresh_token="refresh")])
async def test_initial_exchange_requires_offline_token_and_confirmed_scopes(payload):
    session = GoogleAuthorizationSession("client")
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        with pytest.raises(OAuthError):
            await session.exchange(callback(session), "secret", client=client)


@pytest.mark.parametrize("redirect", ["https://attacker.example/callback", "http://localhost/callback",
                                    "http://user:secret@localhost:8765/callback", "http://localhost:8765/callback?token=secret",
                                    "http://localhost:8765/callback#secret", "http://localhost:bad/callback"])
def test_consent_helper_accepts_only_registered_loopback_redirect_shapes(redirect):
    with pytest.raises(OAuthError, match="loopback"):
        GoogleAuthorizationSession("client", redirect_uri=redirect)
