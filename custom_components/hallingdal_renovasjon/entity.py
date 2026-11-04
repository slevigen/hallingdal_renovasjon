"""Shared base entity."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import HallingdalRenovasjonCoordinator


class HallingdalRenovasjonEntity(CoordinatorEntity[HallingdalRenovasjonCoordinator]):
    """Base for all entities of one property (one device)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: HallingdalRenovasjonCoordinator,
        unique_suffix: str,
        object_id: str,
        platform: str,
    ) -> None:
        """Set ids and device info.

        ``object_id`` is appended to the address slug so entity ids look like
        ``sensor.testveien_1_restavfall`` regardless of the UI language.
        """
        super().__init__(coordinator)
        property_id = coordinator.property_id
        address = coordinator.config_entry.data[CONF_ADDRESS]
        provider = coordinator.provider
        self._attr_unique_id = f"{property_id}_{unique_suffix}"
        self.entity_id = f"{platform}.{slugify(address)}{'_' + object_id if object_id else ''}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, property_id)},
            name=address,
            manufacturer=provider.name,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=provider.configuration_url,
        )

    @staticmethod
    def today() -> date:
        """Today's date in Home Assistant's time zone (not UTC)."""
        return dt_util.now().date()

    async def async_added_to_hass(self) -> None:
        """Refresh state at local midnight so 'next' and days_until roll over."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._async_midnight, hour=0, minute=0, second=0)
        )

    @callback
    def _async_midnight(self, _now: datetime) -> None:
        self.async_write_ha_state()
