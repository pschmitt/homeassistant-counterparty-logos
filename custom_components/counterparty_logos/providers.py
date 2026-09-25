"""Brand search and logo URL builders for logo.dev and Brandfetch."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .const import (
    LOGO_SIZE,
    PROVIDER_BRANDFETCH,
    PROVIDER_LOGO_DEV,
    REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_BRANDFETCH_SEARCH_URL = "https://api.brandfetch.io/v2/search/{query}"
_LOGO_DEV_SEARCH_URL = "https://api.logo.dev/search"
_LOGO_DEV_IMAGE_URL = "https://img.logo.dev/{domain}"
_BRANDFETCH_IMAGE_URL = (
    "https://cdn.brandfetch.io/domain/{domain}/w/{size}/h/{size}/fallback/lettermark/icon.png"
)


class SearchError(Exception):
    """A search request failed; the name should be retried later."""


class RateLimitedError(SearchError):
    """The provider refused the request because of rate limits."""


class AuthError(SearchError):
    """The provider rejected the credentials."""


@dataclass(frozen=True)
class Candidate:
    """One brand search hit."""

    name: str
    domain: str
    quality: float
    source: str


async def _get_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    try:
        async with asyncio.timeout(REQUEST_TIMEOUT):
            resp = await session.get(url, params=params, headers=headers)
            if resp.status == 429:
                raise RateLimitedError(f"{url}: rate limited")
            if resp.status in (401, 403):
                raise AuthError(f"{url}: HTTP {resp.status}")
            if resp.status == 404:
                return []
            if resp.status >= 400:
                raise SearchError(f"{url}: HTTP {resp.status}")
            return await resp.json(content_type=None)
    except (TimeoutError, aiohttp.ClientError) as exc:
        raise SearchError(f"{url}: {exc}") from exc


async def search_brandfetch(
    session: aiohttp.ClientSession, client_id: str, query: str
) -> list[Candidate]:
    """Search Brandfetch's Brand Search API."""
    data = await _get_json(
        session,
        _BRANDFETCH_SEARCH_URL.format(query=quote(query, safe="")),
        params={"c": client_id},
    )
    results: list[Candidate] = []
    for item in data if isinstance(data, list) else []:
        # A result without an icon has no logo to show.
        if not item.get("domain") or not item.get("name") or not item.get("icon"):
            continue
        results.append(
            Candidate(
                name=str(item["name"]),
                domain=str(item["domain"]).lower(),
                quality=float(item.get("qualityScore") or 0),
                source=PROVIDER_BRANDFETCH,
            )
        )
    return results


async def search_logo_dev(
    session: aiohttp.ClientSession, secret_key: str, query: str
) -> list[Candidate]:
    """Search logo.dev's Search API (requires the secret sk_ key)."""
    data = await _get_json(
        session,
        _LOGO_DEV_SEARCH_URL,
        params={"q": query, "strategy": "match"},
        headers={"Authorization": f"Bearer {secret_key}"},
    )
    results: list[Candidate] = []
    for rank, item in enumerate(data if isinstance(data, list) else []):
        if not item.get("domain") or not item.get("name"):
            continue
        # logo.dev returns no quality score; results are ranked best first.
        results.append(
            Candidate(
                name=str(item["name"]),
                domain=str(item["domain"]).lower(),
                quality=max(0.8 - 0.1 * rank, 0.3),
                source=PROVIDER_LOGO_DEV,
            )
        )
    return results


def logo_url(provider: str, domain: str, *, publishable_key: str, client_id: str) -> str:
    """Build a hotlinkable logo URL.

    Both providers require logos to be hotlinked rather than downloaded and
    re-served, so only URLs are handed out. Both fall back to a lettermark when
    they have no logo for the domain, so the URL never renders as broken.
    """
    if provider == PROVIDER_BRANDFETCH:
        base = _BRANDFETCH_IMAGE_URL.format(domain=quote(domain), size=LOGO_SIZE)
        return f"{base}?{urlencode({'c': client_id})}"
    params = {
        "token": publishable_key,
        "size": str(LOGO_SIZE),
        "format": "png",
        "retina": "true",
    }
    return f"{_LOGO_DEV_IMAGE_URL.format(domain=quote(domain))}?{urlencode(params)}"
