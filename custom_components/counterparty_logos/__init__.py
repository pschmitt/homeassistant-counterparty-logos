"""Logos for bank transaction counterparties via logo.dev and Brandfetch."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import (
    ATTR_CLEAR_CACHE,
    ATTR_NAME,
    ATTR_RETRY_UNMATCHED,
    DOMAIN,
    PLATFORMS,
    SCAN_DEBOUNCE_SECONDS,
    SERVICE_LOOKUP,
    SERVICE_REFRESH,
)
from .resolver import LogoResolver

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

# Picks up names whose cached misses have expired.
_RESCAN_INTERVAL = timedelta(hours=12)

type CounterpartyLogosConfigEntry = ConfigEntry[LogoResolver]

LOOKUP_SCHEMA = vol.Schema({vol.Required(ATTR_NAME): vol.All(cv.ensure_list, [cv.string])})
REFRESH_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_RETRY_UNMATCHED, default=False): cv.boolean,
        vol.Optional(ATTR_CLEAR_CACHE, default=False): cv.boolean,
    }
)


def _resolver(hass: HomeAssistant) -> LogoResolver:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError("Counterparty Logos is not set up")
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""

    async def _lookup(call: ServiceCall) -> ServiceResponse:
        resolver = _resolver(hass)
        return {
            "logos": {name: await resolver.async_resolve(name) for name in call.data[ATTR_NAME]}
        }

    async def _refresh(call: ServiceCall) -> None:
        resolver = _resolver(hass)
        if call.data[ATTR_CLEAR_CACHE] or call.data[ATTR_RETRY_UNMATCHED]:
            await resolver.async_clear_cache(unmatched_only=not call.data[ATTR_CLEAR_CACHE])
        hass.async_create_background_task(resolver.async_scan(), f"{DOMAIN} scan")

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOOKUP,
        _lookup,
        schema=LOOKUP_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, SERVICE_REFRESH, _refresh, schema=REFRESH_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CounterpartyLogosConfigEntry) -> bool:
    """Set up Counterparty Logos from a config entry."""
    resolver = LogoResolver(hass, {**entry.data, **entry.options})
    await resolver.async_load()
    entry.runtime_data = resolver

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    debouncer = Debouncer(
        hass,
        _LOGGER,
        cooldown=SCAN_DEBOUNCE_SECONDS,
        immediate=False,
        function=resolver.async_scan,
        background=True,
    )
    entry.async_on_unload(debouncer.async_shutdown)

    @callback
    def _transactions_changed(event_data: EventStateChangedData) -> bool:
        new_state = event_data["new_state"]
        if new_state is None or "transactions" not in new_state.attributes:
            return False
        old_state = event_data["old_state"]
        return old_state is None or old_state.attributes.get(
            "transactions"
        ) != new_state.attributes.get("transactions")

    @callback
    def _schedule_scan(_: Event[EventStateChangedData] | object = None) -> None:
        hass.async_create_task(debouncer.async_call())

    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_STATE_CHANGED, _schedule_scan, event_filter=_transactions_changed
        )
    )
    entry.async_on_unload(async_track_time_interval(hass, _schedule_scan, _RESCAN_INTERVAL))
    entry.async_on_unload(async_at_started(hass, _schedule_scan))
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CounterpartyLogosConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
