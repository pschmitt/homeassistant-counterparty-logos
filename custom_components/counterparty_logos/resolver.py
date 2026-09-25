"""Resolve counterparty names to brand domains and logo URLs, with caching."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Iterable, Mapping
from difflib import SequenceMatcher
from typing import Any

import yaml
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BRANDFETCH_CLIENT_ID,
    CONF_IMAGE_PROVIDER,
    CONF_LOGO_DEV_PUBLISHABLE_KEY,
    CONF_LOGO_DEV_SECRET_KEY,
    CONF_NAME_ATTRIBUTES,
    DEFAULT_NAME_ATTRIBUTES,
    DOMAIN_MATCH_BONUS,
    EXACT_MATCH_BONUS,
    EXACT_MATCH_RATIO,
    MIN_PREFIX_QUALITY,
    MIN_PREFIX_QUERY_LENGTH,
    MIN_QUALITY,
    NEGATIVE_CACHE_TTL,
    OVERRIDES_FILE,
    PROVIDER_BRANDFETCH,
    PROVIDER_LOGO_DEV,
    PROVIDER_OVERRIDE,
    SEARCH_DELAY_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .normalize import (
    brand_name_key,
    domain_label_key,
    extract_domain,
    fold,
    match_key,
    search_query,
)
from .providers import (
    AuthError,
    Candidate,
    RateLimitedError,
    SearchError,
    logo_url,
    search_brandfetch,
    search_logo_dev,
)

_LOGGER = logging.getLogger(__name__)

_RATE_LIMIT_BACKOFF_SECONDS = 300
_MIN_QUERY_LENGTH = 3


def pick_candidate(query: str, candidates: Iterable[Candidate]) -> Candidate | None:
    """Pick the search hit that plausibly is the queried brand, if any.

    A hit must carry (nearly) the query as its name or as its domain label
    ("BVG" -> bvg.de), or have a name starting with all query words ("EDEKA" ->
    "EDEKA ZENTRALE Stiftung"). Prefix hits are riskier, so they need a higher
    quality and a query that is not a short acronym. Among the remaining hits,
    the highest quality wins, with bonuses for exact name and domain matches.
    """
    query_key = match_key(query)
    query_words = fold(query).split()
    best: tuple[float, Candidate] | None = None
    for cand in candidates:
        name_key = brand_name_key(cand.name)
        if not name_key or cand.quality < MIN_QUALITY:
            continue
        name_match = (
            name_key == query_key
            or SequenceMatcher(None, query_key, name_key).ratio() >= EXACT_MATCH_RATIO
        )
        domain_match = domain_label_key(cand.domain) == query_key
        prefix_match = (
            len(query_key) >= MIN_PREFIX_QUERY_LENGTH
            and cand.quality >= MIN_PREFIX_QUALITY
            and fold(cand.name).split()[: len(query_words)] == query_words
        )
        if not (name_match or domain_match or prefix_match):
            continue
        score = (
            cand.quality
            + (EXACT_MATCH_BONUS if name_match else 0)
            + (DOMAIN_MATCH_BONUS if domain_match else 0)
        )
        if best is None or score > best[0]:
            best = (score, cand)
    return best[1] if best else None


class LogoResolver:
    """Map counterparty names to logo URLs.

    Search results are cached persistently per normalized search query, so each
    distinct counterparty costs one search request. Misses are cached as well
    and retried after NEGATIVE_CACHE_TTL.
    """

    def __init__(self, hass: HomeAssistant, config: Mapping[str, Any]) -> None:
        """Initialize the resolver."""
        self.hass = hass
        self._config = config
        self._session = async_get_clientsession(hass)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._cache: dict[str, dict[str, Any]] = {}
        self._overrides: list[tuple[str, str | None]] = []
        self._overrides_mtime: float | None = None
        self._scan_lock = asyncio.Lock()
        self._search_lock = asyncio.Lock()
        self._next_search_at = 0.0
        self._searches_paused_until = 0.0
        self._listeners: list[Callable[[], None]] = []
        self.logos: dict[str, str] = {}

    @property
    def name_attributes(self) -> list[str]:
        """Transaction keys holding counterparty names."""
        return list(self._config.get(CONF_NAME_ATTRIBUTES) or DEFAULT_NAME_ATTRIBUTES)

    async def async_load(self) -> None:
        """Load the persistent cache and overrides."""
        data = await self._store.async_load() or {}
        self._cache = dict(data.get("names") or {})
        await self._async_load_overrides()

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register a callback for when the logo map changes."""
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    @callback
    def _save(self) -> None:
        self._store.async_delay_save(lambda: {"names": self._cache}, 30)

    async def async_clear_cache(self, *, unmatched_only: bool) -> None:
        """Drop cached search results so they are searched again."""
        if unmatched_only:
            self._cache = {k: v for k, v in self._cache.items() if v.get("domain")}
        else:
            self._cache = {}
        self._save()

    async def _async_load_overrides(self) -> None:
        path = self.hass.config.path(OVERRIDES_FILE)

        def _load() -> tuple[float | None, Any]:
            try:
                mtime = os.stat(path).st_mtime
            except FileNotFoundError:
                return None, None
            if mtime == self._overrides_mtime:
                return mtime, ...
            with open(path, encoding="utf-8") as fh:
                return mtime, yaml.safe_load(fh)

        try:
            mtime, raw = await self.hass.async_add_executor_job(_load)
        except (OSError, yaml.YAMLError) as exc:
            _LOGGER.error("Failed to load %s: %s", path, exc)
            return
        if raw is ...:
            return
        self._overrides_mtime = mtime
        overrides: list[tuple[str, str | None]] = []
        if isinstance(raw, dict):
            for keyword, domain in raw.items():
                key = fold(str(keyword))
                if key:
                    overrides.append((key, str(domain).strip().lower() if domain else None))
        elif raw is not None:
            _LOGGER.error("%s must contain a mapping of keyword: domain", path)
        # Most specific keyword first.
        self._overrides = sorted(overrides, key=lambda item: len(item[0]), reverse=True)

    def _match_override(self, name: str) -> tuple[bool, str | None]:
        padded = f" {fold(name)} "
        for keyword, domain in self._overrides:
            if f" {keyword} " in padded:
                return True, domain
        return False, None

    async def async_resolve(self, name: str, *, search: bool = True) -> dict[str, Any] | None:
        """Resolve a raw counterparty name to {domain, source, url}, or None."""
        overridden, domain = self._match_override(name)
        if overridden:
            return self._result(domain, PROVIDER_OVERRIDE) if domain else None

        if domain := extract_domain(name):
            return self._result(domain, "name")

        query = search_query(name)
        key = match_key(query)
        if len(key) < _MIN_QUERY_LENGTH:
            return None

        cached = self._cache.get(key)
        if cached is not None:
            if cached.get("domain"):
                return self._result(cached["domain"], cached.get("source"))
            checked = dt_util.parse_datetime(cached.get("checked") or "")
            if checked and dt_util.utcnow() - checked < NEGATIVE_CACHE_TTL:
                return None

        if not search:
            return None

        try:
            candidate = await self._async_search(query)
        except SearchError as exc:
            _LOGGER.debug("Search for %r failed, will retry later: %s", query, exc)
            return None

        self._cache[key] = {
            "query": query,
            "domain": candidate.domain if candidate else None,
            "brand": candidate.name if candidate else None,
            "source": candidate.source if candidate else None,
            "checked": dt_util.utcnow().isoformat(),
        }
        self._save()
        _LOGGER.debug(
            "Resolved %r (query %r) to %s",
            name,
            query,
            f"{candidate.domain} via {candidate.source}" if candidate else "nothing",
        )
        return self._result(candidate.domain, candidate.source) if candidate else None

    async def _async_search(self, query: str) -> Candidate | None:
        """Search the configured providers in order until one has a match."""
        loop = asyncio.get_running_loop()
        searches: list[tuple[str, Callable[..., Any], str]] = []
        if secret := self._config.get(CONF_LOGO_DEV_SECRET_KEY):
            searches.append((PROVIDER_LOGO_DEV, search_logo_dev, secret))
        if client_id := self._config.get(CONF_BRANDFETCH_CLIENT_ID):
            searches.append((PROVIDER_BRANDFETCH, search_brandfetch, client_id))
        if not searches:
            return None

        async with self._search_lock:
            if loop.time() < self._searches_paused_until:
                raise SearchError("searches paused after rate limit")
            errors = 0
            for provider, search_fn, credential in searches:
                await asyncio.sleep(max(0.0, self._next_search_at - loop.time()))
                self._next_search_at = loop.time() + SEARCH_DELAY_SECONDS
                try:
                    candidates = await search_fn(self._session, credential, query)
                except RateLimitedError:
                    _LOGGER.warning(
                        "%s rate limit hit, pausing searches for %ss",
                        provider,
                        _RATE_LIMIT_BACKOFF_SECONDS,
                    )
                    self._searches_paused_until = loop.time() + _RATE_LIMIT_BACKOFF_SECONDS
                    raise
                except AuthError as exc:
                    _LOGGER.error("%s rejected the configured credentials: %s", provider, exc)
                    errors += 1
                    continue
                except SearchError:
                    errors += 1
                    continue
                if match := pick_candidate(query, candidates):
                    return match
            # Only record a miss when every provider actually answered.
            if errors:
                raise SearchError(f"{errors} provider(s) failed")
            return None

    def _result(self, domain: str, source: str | None) -> dict[str, Any]:
        return {"domain": domain, "source": source, "url": self.url_for(domain)}

    def url_for(self, domain: str) -> str:
        """Build the logo URL for a domain with the configured image provider."""
        provider = self._config.get(CONF_IMAGE_PROVIDER) or PROVIDER_LOGO_DEV
        publishable_key = self._config.get(CONF_LOGO_DEV_PUBLISHABLE_KEY) or ""
        client_id = self._config.get(CONF_BRANDFETCH_CLIENT_ID) or ""
        if provider == PROVIDER_LOGO_DEV and not publishable_key:
            provider = PROVIDER_BRANDFETCH
        elif provider == PROVIDER_BRANDFETCH and not client_id:
            provider = PROVIDER_LOGO_DEV
        return logo_url(provider, domain, publishable_key=publishable_key, client_id=client_id)

    @callback
    def _collect_names(self) -> set[str]:
        attributes = self.name_attributes
        names: set[str] = set()
        for state in self.hass.states.async_all():
            transactions = state.attributes.get("transactions")
            if not isinstance(transactions, list):
                continue
            for txn in transactions:
                if not isinstance(txn, dict):
                    continue
                for attr in attributes:
                    value = txn.get(attr)
                    if isinstance(value, str) and value.strip():
                        names.add(value.strip())
        return names

    async def async_scan(self) -> None:
        """Resolve every counterparty found in transaction attributes."""
        async with self._scan_lock:
            await self._async_load_overrides()
            names = sorted(self._collect_names())
            # Publish cached results right away, then search the rest.
            for search in (False, True):
                logos: dict[str, str] = {}
                for name in names:
                    if result := await self.async_resolve(name, search=search):
                        logos[name] = result["url"]
                self._publish(logos)

    @callback
    def _publish(self, logos: dict[str, str]) -> None:
        if logos == self.logos:
            return
        self.logos = logos
        for update_callback in list(self._listeners):
            update_callback()
