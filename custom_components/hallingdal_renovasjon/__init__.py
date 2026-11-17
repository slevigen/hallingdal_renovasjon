"""The Hallingdal Renovasjon integration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig  # type: ignore[attr-defined]
from homeassistant.components.websocket_api.connection import ActiveConnection
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
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
    websocket_api.async_register_command(hass, _ws_status)
    return True


@websocket_api.websocket_command(  # type: ignore[attr-defined]
    {
        vol.Required("type"): f"{DOMAIN}/status",  # type: ignore[dict-item]
        vol.Optional("device_id"): str,  # type: ignore[dict-item]
    }
)
@callback
def _ws_status(hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]) -> None:
    """Tell the card why a property has no data. Open to every logged-in user."""
    entry = _entry_for_device(hass, msg.get("device_id"))
    connection.send_result(msg["id"], {"problem": _problem(entry) if entry else None})


def _entry_for_device(hass: HomeAssistant, device_id: str | None) -> ConfigEntry | None:
    """Return the entry behind a device; without a device, the first property."""
    if device_id is None:
        entries = hass.config_entries.async_entries(DOMAIN)
        return entries[0] if entries else None
    device = dr.async_get(hass).async_get(device_id)
    for entry_id in device.config_entries if device else ():
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is not None and entry.domain == DOMAIN:
            return entry
    return None


def _problem(entry: ConfigEntry) -> str | None:
    """Return the translation key of what keeps the schedule away, or None if all is well."""
    if entry.state is ConfigEntryState.LOADED:
        coordinator: HallingdalRenovasjonCoordinator = entry.runtime_data
        if coordinator.last_update_success:
            return None
        key = getattr(coordinator.last_exception, "translation_key", None)
    elif entry.state in (ConfigEntryState.SETUP_RETRY, ConfigEntryState.SETUP_ERROR):
        key = entry.error_reason_translation_key
    else:
        return None
    return key or "update_failed"


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
