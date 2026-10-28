"""Explicitly authorized, no-cost normalized feeds; never guessed provider endpoints."""
import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

MAX_FEED_BYTES = 2 * 1024 * 1024


def validate_feed_url(url: str, allowed_host: str):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != allowed_host or parsed.port not in {None, 443}
            or parsed.username or parsed.password or parsed.fragment or parsed.query):
        raise ValueError("Feed must be an explicitly allowed public HTTPS host without URL credentials or query secrets")
    addresses = socket.getaddrinfo(allowed_host, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(addr[4][0]).is_global for addr in addresses):
        raise ValueError("Feed host must resolve exclusively to public IP addresses")


async def fetch_campaigns(url: str, allowed_host: str) -> list[dict]:
    validate_feed_url(url, allowed_host)
    # Trust the platform HTTPS egress proxy; never follow redirects to another origin.
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_FEED_BYTES:
                    raise ValueError("Campaign feed exceeds size limit")
    import json
    records = json.loads(data)
    if not isinstance(records, list) or len(records) > 1000:
        raise ValueError("Campaign feed must contain a JSON list of at most 1000 normalized campaigns")
    return records
