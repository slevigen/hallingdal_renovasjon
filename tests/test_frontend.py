"""Tests for the bundled card and pictures."""

from __future__ import annotations

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant

from custom_components.hallingdal_renovasjon.const import CARD_URL, VERSION

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
