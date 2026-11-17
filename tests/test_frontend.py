"""Tests for the bundled card and pictures."""

from __future__ import annotations

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.hallingdal_renovasjon.const import CARD_URL, DOMAIN, VERSION

from .conftest import PICKUPS_URL, PROPERTY_ID, certificate_error

KEYS = ("restavfall", "matavfall", "papir", "plast", "glass_metall")


async def test_card_is_served_and_registered(
    hass: HomeAssistant, setup_integration, hass_client
) -> None:
    assert f"{CARD_URL}?v={VERSION}" in hass.data[DATA_EXTRA_MODULE_URL].urls
    client = await hass_client()
    response = await client.get(f"{CARD_URL}?v={VERSION}")
    assert response.status == 200
    body = await response.text()
    assert "customElements.define(CARD, HallingdalRenovasjonCard)" in body


async def test_card_pictures_are_served(
    hass: HomeAssistant, setup_integration, hass_client
) -> None:
    client = await hass_client()
    for key in KEYS:
        response = await client.get(f"/hallingdal_renovasjon/images/card/{key}.png")
        assert response.status == 200, key
        assert (await response.read()).startswith(b"\x89PNG")


async def _status(hass: HomeAssistant, hass_ws_client, **extra) -> dict:
    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/status", **extra})
    response = await client.receive_json()
    assert response["success"], response
    return response["result"]


async def test_status_is_clean_when_loaded(
    hass: HomeAssistant, setup_integration, hass_ws_client
) -> None:
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), setup_integration.entry_id)
    assert (DOMAIN, PROPERTY_ID) in device.identifiers
    assert await _status(hass, hass_ws_client, device_id=device.id) == {"problem": None}
    assert await _status(hass, hass_ws_client) == {"problem": None}


async def test_status_reports_expired_certificate_during_setup(
    hass: HomeAssistant, config_entry, mock_api, hass_ws_client
) -> None:
    mock_api.login_error(certificate_error())
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert await _status(hass, hass_ws_client) == {"problem": "certificate_expired"}


async def test_status_reports_failed_refresh(
    hass: HomeAssistant, setup_integration, mock_api, hass_ws_client
) -> None:
    coordinator = setup_integration.runtime_data
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(exc=certificate_error())
    await coordinator.async_refresh()
    assert await _status(hass, hass_ws_client) == {"problem": "certificate_expired"}

    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(exc=TimeoutError())
    await coordinator.async_refresh()
    assert await _status(hass, hass_ws_client) == {"problem": "update_failed"}


async def test_status_for_unknown_device(
    hass: HomeAssistant, setup_integration, hass_ws_client
) -> None:
    assert await _status(hass, hass_ws_client, device_id="nope") == {"problem": None}
