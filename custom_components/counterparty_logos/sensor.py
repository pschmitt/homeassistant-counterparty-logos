"""Sensor exposing the counterparty name -> logo URL map."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import CounterpartyLogosConfigEntry
from .resolver import LogoResolver


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CounterpartyLogosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the logo map sensor."""
    async_add_entities([CounterpartyLogosSensor(entry.runtime_data, entry.entry_id)])


class CounterpartyLogosSensor(SensorEntity):
    """Number of counterparties with a logo; the map itself is an attribute.

    Dashboards look logos up by the raw (trimmed) counterparty name:
    ``states['sensor.counterparty_logos'].attributes.logos[name]``.
    """

    _attr_name = "Counterparty logos"
    _attr_icon = "mdi:domain"
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "logos"
    # The map can get large and only matters for the current state.
    _unrecorded_attributes = frozenset({"logos"})

    def __init__(self, resolver: LogoResolver, entry_id: str) -> None:
        """Initialize the sensor."""
        self._resolver = resolver
        self._attr_unique_id = f"{entry_id}_logos"

    async def async_added_to_hass(self) -> None:
        """Subscribe to logo map updates."""
        self.async_on_remove(self._resolver.async_add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> int:
        """Return the number of counterparties with a logo."""
        return len(self._resolver.logos)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the name -> logo URL map."""
        return {"logos": dict(self._resolver.logos)}
