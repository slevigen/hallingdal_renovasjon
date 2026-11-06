"""Binary sensor 'Hentedag': on when something is collected today."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import HallingdalRenovasjonConfigEntry, HallingdalRenovasjonCoordinator
from .entity import HallingdalRenovasjonEntity

PICKUP_DAY_KEY = "hentedag"

PARALLEL_UPDATES = 0  # read-only from the coordinator


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: HallingdalRenovasjonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the pickup-day sensor."""
    async_add_entities([PickupDaySensor(entry.runtime_data)])


class PickupDaySensor(HallingdalRenovasjonEntity, BinarySensorEntity):
    """On when at least one fraction is collected today (local date).

    Attributes, for automations without templates over several sensors:
    ``fractions`` (collected today) and one ``<fraction key>: days until next``
    per fraction in the schedule, e.g. ``matavfall: 1``.
    """

    _attr_translation_key = PICKUP_DAY_KEY

    def __init__(self, coordinator: HallingdalRenovasjonCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "pickup_day", PICKUP_DAY_KEY, Platform.BINARY_SENSOR)

    def _today_fractions(self) -> list[str]:
        today = self.today()
        return [
            p.fraction_name or p.fraction_id
            for p in self.coordinator.data.upcoming(today)
            if p.date == today
        ]

    @property
    def is_on(self) -> bool:
        """True on a pickup day, all day."""
        return bool(self._today_fractions())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Fractions collected today, and days until next pickup per fraction."""
        today = self.today()
        attrs: dict[str, Any] = {"fractions": self._today_fractions()}
        for schedule in self.coordinator.data.fractions.values():
            upcoming = [d for d in schedule.dates if d >= today]
            attrs[schedule.key] = (upcoming[0] - today).days if upcoming else None
        return attrs
