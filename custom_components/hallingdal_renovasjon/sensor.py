"""Date sensors: one per fraction plus 'Neste henting'."""

from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import (
    FractionSchedule,
    HallingdalRenovasjonConfigEntry,
    HallingdalRenovasjonCoordinator,
)
from .entity import HallingdalRenovasjonEntity

UPCOMING_COUNT = 5
NEXT_KEY = "neste_henting"
_UNKNOWN_PREFIX = "fraksjon_"

PARALLEL_UPDATES = 0  # read-only from the coordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HallingdalRenovasjonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for fractions in the data, and keep earlier ones across restarts."""
    coordinator = entry.runtime_data
    added: set[str] = set()

    @callback
    def _async_add(fraction_ids: list[str]) -> None:
        new = [fid for fid in fraction_ids if fid not in added]
        added.update(new)
        if new:
            async_add_entities(FractionSensor(coordinator, fid) for fid in new)

    # Fractions seen before but outside the current 90-day window stay (state unknown).
    _async_add(_registered_fraction_ids(hass, coordinator, entry))
    _async_add(list(coordinator.data.fractions))
    entry.async_on_unload(
        coordinator.async_add_listener(lambda: _async_add(list(coordinator.data.fractions)))
    )
    async_add_entities([NextPickupSensor(coordinator)])


def _registered_fraction_ids(
    hass: HomeAssistant,
    coordinator: HallingdalRenovasjonCoordinator,
    entry: HallingdalRenovasjonConfigEntry,
) -> list[str]:
    by_key = {f.key: fid for fid, f in coordinator.provider.fractions.items()}
    prefix = f"{coordinator.property_id}_"
    ids: list[str] = []
    for reg in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if reg.domain != Platform.SENSOR or not reg.unique_id.startswith(prefix):
            continue
        key = reg.unique_id.removeprefix(prefix)
        if key in by_key:
            ids.append(by_key[key])
        elif key.startswith(_UNKNOWN_PREFIX):
            ids.append(key.removeprefix(_UNKNOWN_PREFIX))
    return ids


class FractionSensor(HallingdalRenovasjonEntity, SensorEntity):
    """Next pickup date for one fraction."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: HallingdalRenovasjonCoordinator, fraction_id: str) -> None:
        """Initialise from the provider table, or from the data for unknown fractions."""
        known = coordinator.provider.fractions.get(fraction_id)
        key = known.key if known else f"{_UNKNOWN_PREFIX}{fraction_id}"
        super().__init__(coordinator, key, key, Platform.SENSOR)
        self._fraction_id = fraction_id
        if known:
            self._attr_translation_key = key
        else:
            schedule = coordinator.data.fractions.get(fraction_id)
            self._attr_name = schedule.name if schedule else f"Fraksjon {fraction_id}"
            self._attr_icon = "mdi:trash-can-outline"

    def _schedule(self) -> FractionSchedule | None:
        return self.coordinator.data.fractions.get(self._fraction_id)

    def _upcoming(self) -> list[date]:
        schedule = self._schedule()
        if schedule is None:
            return []
        today = self.today()
        return [d for d in schedule.dates if d >= today]

    @property
    def native_value(self) -> date | None:
        """Next date, or None (unknown) if nothing is scheduled."""
        upcoming = self._upcoming()
        return upcoming[0] if upcoming else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """days_until, fraction_id and the next few dates."""
        upcoming = self._upcoming()
        return {
            "days_until": (upcoming[0] - self.today()).days if upcoming else None,
            "fraction_id": self._fraction_id,
            "upcoming": [d.isoformat() for d in upcoming[:UPCOMING_COUNT]],
        }


class NextPickupSensor(HallingdalRenovasjonEntity, SensorEntity):
    """Next pickup of any fraction."""

    _attr_device_class = SensorDeviceClass.DATE
    _attr_translation_key = NEXT_KEY

    def __init__(self, coordinator: HallingdalRenovasjonCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "next", NEXT_KEY, Platform.SENSOR)

    def _next(self) -> tuple[date | None, list[str]]:
        upcoming = self.coordinator.data.upcoming(self.today())
        if not upcoming:
            return None, []
        first = upcoming[0].date
        return first, [p.fraction_name or p.fraction_id for p in upcoming if p.date == first]

    @property
    def native_value(self) -> date | None:
        """Next date regardless of fraction."""
        return self._next()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """days_until and the fractions collected that day."""
        first, fractions = self._next()
        return {
            "days_until": (first - self.today()).days if first else None,
            "fractions": fractions,
        }
