"""Calendar with every upcoming pickup as an all-day event."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Pickup
from .coordinator import HallingdalRenovasjonConfigEntry, HallingdalRenovasjonCoordinator
from .entity import HallingdalRenovasjonEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HallingdalRenovasjonConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the calendar."""
    del hass
    async_add_entities([HallingdalRenovasjonCalendar(entry.runtime_data)])


class HallingdalRenovasjonCalendar(HallingdalRenovasjonEntity, CalendarEntity):
    """One event per pickup; several fractions on one day give several events."""

    _attr_name = None  # the device (address) name

    def __init__(self, coordinator: HallingdalRenovasjonCoordinator) -> None:
        """Initialise."""
        super().__init__(coordinator, "calendar", "", Platform.CALENDAR)

    def _event(self, pickup: Pickup) -> CalendarEvent:
        return CalendarEvent(
            summary=pickup.fraction_name or pickup.fraction_id,
            start=pickup.date,
            end=pickup.date + timedelta(days=1),
            description=self.coordinator.provider.name.removesuffix(" IKS"),
            uid=f"{self.coordinator.property_id}_{pickup.fraction_id}_{pickup.date.isoformat()}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """The next (or today's) pickup."""
        upcoming = self.coordinator.data.upcoming(self.today())
        return self._event(upcoming[0]) if upcoming else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Pickups whose (local) day overlaps [start_date, end_date)."""
        del hass
        return [
            self._event(p)
            for p in self.coordinator.data.pickups
            if dt_util.start_of_local_day(p.date) < end_date
            and dt_util.start_of_local_day(p.date + timedelta(days=1)) > start_date
        ]
