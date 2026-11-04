"""Data update coordinator for Hallingdal Renovasjon."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ApiAuthError,
    HallingdalRenovasjonApiClient,
    HallingdalRenovasjonApiError,
    Pickup,
)
from .const import (
    CONF_ADDRESS,
    CONF_PROPERTY_ID,
    DOMAIN,
    HALLINGDAL,
    LOGGER,
    LOOKAHEAD,
    UPDATE_INTERVAL,
    Provider,
)

type HallingdalRenovasjonConfigEntry = ConfigEntry[HallingdalRenovasjonCoordinator]


@dataclass(frozen=True)
class FractionSchedule:
    """Upcoming pickups of one fraction at one property."""

    fraction_id: str
    key: str  # used in unique_id, entity_id and as translation_key when known
    name: str
    known: bool  # listed in the provider's fraction table
    dates: tuple[date, ...]


@dataclass(frozen=True)
class WasteSchedule:
    """Normalised schedule. Entities only ever read this."""

    pickups: tuple[Pickup, ...]  # sorted by date; fraction_name is always set
    fractions: dict[str, FractionSchedule]  # by fraction_id, in provider table order

    def upcoming(self, today: date) -> list[Pickup]:
        """Pickups on or after ``today``.

        Filtered at read time too, since data can be up to 6 hours old.
        """
        return [p for p in self.pickups if p.date >= today]


class HallingdalRenovasjonCoordinator(DataUpdateCoordinator[WasteSchedule]):
    """Fetch the schedule for one property every 6 hours."""

    config_entry: HallingdalRenovasjonConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: HallingdalRenovasjonConfigEntry,
        client: HallingdalRenovasjonApiClient,
        provider: Provider = HALLINGDAL,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_ADDRESS]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.provider = provider
        self.property_id: str = entry.data[CONF_PROPERTY_ID]
        self._warned_fractions: set[str] = set()

    async def _async_update_data(self) -> WasteSchedule:
        today = dt_util.now().date()
        try:
            pickups = await self.client.async_get_pickups(
                self.property_id, today, today + LOOKAHEAD
            )
        except ApiAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except HallingdalRenovasjonApiError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        return self.normalize(pickups, today)

    def normalize(self, pickups: list[Pickup], today: date) -> WasteSchedule:
        """Drop past and duplicate pickups, resolve names and group per fraction."""
        table = self.provider.fractions
        order = {fraction_id: index for index, fraction_id in enumerate(table)}

        def sort_key(fraction_id: str) -> tuple[int, str]:
            return (order.get(fraction_id, len(order)), fraction_id)

        names: dict[str, str] = {}
        unique: dict[tuple[date, str], Pickup] = {}
        for pickup in pickups:
            if pickup.date < today:
                continue
            fraction_id = pickup.fraction_id
            if fraction_id not in names:
                names[fraction_id] = self._resolve_name(pickup)
            unique.setdefault(
                (pickup.date, fraction_id), replace(pickup, fraction_name=names[fraction_id])
            )

        normalized = tuple(
            sorted(unique.values(), key=lambda p: (p.date, *sort_key(p.fraction_id)))
        )
        fractions: dict[str, FractionSchedule] = {}
        for fraction_id in sorted(names, key=sort_key):
            known = table.get(fraction_id)
            fractions[fraction_id] = FractionSchedule(
                fraction_id=fraction_id,
                key=known.key if known else f"fraksjon_{fraction_id}",
                name=names[fraction_id],
                known=known is not None,
                dates=tuple(p.date for p in normalized if p.fraction_id == fraction_id),
            )
        return WasteSchedule(pickups=normalized, fractions=fractions)

    def _resolve_name(self, pickup: Pickup) -> str:
        """Prefer the API's name, then the provider table, then ``Fraksjon <id>``."""
        known = self.provider.fractions.get(pickup.fraction_id)
        if known is None and pickup.fraction_id not in self._warned_fractions:
            self._warned_fractions.add(pickup.fraction_id)
            LOGGER.warning(
                "Unknown fraction id %s (%s) for %s; please report it at the issue tracker",
                pickup.fraction_id,
                pickup.fraction_name or "no name from API",
                self.config_entry.title,
            )
        if pickup.fraction_name:
            return pickup.fraction_name
        if known is not None:
            return known.name
        return f"Fraksjon {pickup.fraction_id}"
