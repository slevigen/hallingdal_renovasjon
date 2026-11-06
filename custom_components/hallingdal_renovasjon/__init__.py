"""The Hallingdal Renovasjon integration."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined]
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import HallingdalRenovasjonApiClient
from .const import CARD_URL, CONF_PROPERTY_ID, DOMAIN, IMAGES_URL, VERSION
from .coordinator import HallingdalRenovasjonConfigEntry, HallingdalRenovasjonCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.CALENDAR, Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:  # noqa: ARG001
    """Serve the fraction pictures and the Lovelace card, and load the card in the frontend."""
    here = Path(__file__).parent
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(IMAGES_URL, str(here / "images"), cache_headers=True),
            StaticPathConfig(
                CARD_URL,
                str(here / "frontend" / "hallingdal-renovasjon-card.js"),
                cache_headers=True,
            ),
        ]
    )
    # Versioned URL: a new release busts the browser cache for the card and its images.
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    return True


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
