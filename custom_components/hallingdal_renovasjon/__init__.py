"""The Hallingdal Renovasjon integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import HallingdalRenovasjonApiClient
from .const import CONF_PROPERTY_ID, DOMAIN
from .coordinator import HallingdalRenovasjonConfigEntry, HallingdalRenovasjonCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: HallingdalRenovasjonConfigEntry) -> bool:
    """Set up one property from a config entry."""
    _async_remove_stale_devices(hass, entry)
    client = HallingdalRenovasjonApiClient(async_get_clientsession(hass))
    coordinator = HallingdalRenovasjonCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HallingdalRenovasjonConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_remove_stale_devices(
    hass: HomeAssistant, entry: HallingdalRenovasjonConfigEntry
) -> None:
    """Drop the old device (and its entities) after reconfigure switched property."""
    registry = dr.async_get(hass)
    current = (DOMAIN, entry.data[CONF_PROPERTY_ID])
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if current not in device.identifiers:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
