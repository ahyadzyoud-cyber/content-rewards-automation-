"""Feed imports fail closed on host changes, private addresses and oversized data."""
import json
import socket

import httpx
import pytest

from content_rewards import feeds


def public_dns(monkeypatch):
    monkeypatch.setattr(feeds.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
    ])


def mock_client(monkeypatch, handler):
    original = httpx.AsyncClient

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(feeds.httpx, "AsyncClient", factory)


@pytest.mark.parametrize("url", [
    "http://feed.example.com/campaigns", "https://other.example.com/campaigns",
    "https://user:secret@feed.example.com/campaigns", "https://feed.example.com:8443/campaigns",
    "https://feed.example.com/campaigns?token=secret", "https://feed.example.com/campaigns#fragment",
])
def test_invalid_feed_urls_are_rejected_before_dns_or_http(monkeypatch, url):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid feed URLs must fail before DNS lookup")

    monkeypatch.setattr(feeds.socket, "getaddrinfo", unexpected)
    with pytest.raises(ValueError, match="explicitly allowed"):
        feeds.validate_feed_url(url, "feed.example.com")


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.3", "169.254.169.254", "::1", "fc00::1"])
def test_feed_host_must_resolve_exclusively_to_public_addresses(monkeypatch, address):
    monkeypatch.setattr(feeds.socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
    ])
    with pytest.raises(ValueError, match="exclusively to public"):
        feeds.validate_feed_url("https://feed.example.com/campaigns", "feed.example.com")


async def test_explicit_public_json_feed_returns_records(monkeypatch):
    public_dns(monkeypatch)
    requests = []
    records = [{"id": "campaign1", "title": "Imported but not yet verified"}]

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://feed.example.com/campaigns"
        return httpx.Response(200, json=records)

    mock_client(monkeypatch, handler)
    assert await feeds.fetch_campaigns("https://feed.example.com/campaigns", "feed.example.com") == records
    assert len(requests) == 1


async def test_redirect_is_never_followed(monkeypatch):
    public_dns(monkeypatch)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://169.254.169.254/private"})

    mock_client(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError):
        await feeds.fetch_campaigns("https://feed.example.com/campaigns", "feed.example.com")
    assert len(calls) == 1


async def test_feed_size_limit_applies_to_decoded_response(monkeypatch):
    public_dns(monkeypatch)
    monkeypatch.setattr(feeds, "MAX_FEED_BYTES", 100)
    mock_client(monkeypatch, lambda _: httpx.Response(200, content=b" " * 101))
    with pytest.raises(ValueError, match="size limit"):
        await feeds.fetch_campaigns("https://feed.example.com/campaigns", "feed.example.com")


@pytest.mark.parametrize("body", [b"not JSON", b'{"campaigns": []}', json.dumps([{}] * 1001).encode()])
async def test_malformed_or_unbounded_record_sets_are_rejected(monkeypatch, body):
    public_dns(monkeypatch)
    mock_client(monkeypatch, lambda _: httpx.Response(200, content=body))
    with pytest.raises(ValueError):
        await feeds.fetch_campaigns("https://feed.example.com/campaigns", "feed.example.com")
