"""Tests for the 'Hentedag' binary sensor and the translation files."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hallingdal_renovasjon.const import UPDATE_INTERVAL

from .conftest import PICKUPS_URL, PROPERTY_ID

ENTITY_ID = "binary_sensor.testveien_1_hentedag"
TRANSLATIONS = (
    Path(__file__).parents[1] / "custom_components" / "hallingdal_renovasjon" / "translations"
)


async def _at(hass: HomeAssistant, freezer, when: str) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_off_before_pickup_day(hass: HomeAssistant, setup_integration) -> None:
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes["fractions"] == []
    assert state.attributes["matavfall"] == 2
    assert state.attributes["papir"] == 2
    assert state.attributes["restavfall"] == 16
    assert state.attributes["plast"] == 16
    assert state.attributes["glass_metall"] == 30
    assert state.attributes["friendly_name"] == "Testveien 1 Pickup day"
    entry = er.async_get(hass).async_get(ENTITY_ID)
    assert entry.unique_id == f"{PROPERTY_ID}_pickup_day"
    assert entry.translation_key == "hentedag"


async def test_on_all_pickup_day_then_off_at_midnight(
    hass: HomeAssistant, setup_integration, freezer
) -> None:
    # Midnight listener turns it on without a new fetch.
    await _at(hass, freezer, "2026-11-06 00:00:00+01:00")
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes["fractions"] == ["Matavfall", "Papp, papir og drikkekartong"]
    assert state.attributes["matavfall"] == 0
    assert state.attributes["restavfall"] == 14

    await _at(hass, freezer, "2026-11-07 00:00:00+01:00")
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF
    assert state.attributes["fractions"] == []
    assert state.attributes["matavfall"] == 20


async def test_unknown_fraction_and_empty_schedule(
    hass: HomeAssistant, setup_integration, mock_api, freezer
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(
        [{"dato": "2026-11-04T00:00:00", "fraksjonId": "42", "fraksjon": "Hageavfall"}]
    )
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_ON
    assert state.attributes["fractions"] == ["Hageavfall"]
    assert state.attributes["fraksjon_42"] == 0
    assert "restavfall" not in state.attributes

    mock_api.reset(PICKUPS_URL)
    mock_api.pickups([])
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_unavailable_on_network_error(
    hass: HomeAssistant, setup_integration, mock_api, freezer
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(exc=TimeoutError())
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE


def _keys(obj: object, prefix: str = "") -> set[str]:
    if not isinstance(obj, dict):
        return {prefix}
    return {k for key, value in obj.items() for k in _keys(value, f"{prefix}/{key}")}


def test_translation_files_have_the_same_keys() -> None:
    files = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in TRANSLATIONS.glob("*.json")}
    assert set(files) == {"en", "nb", "nn"}
    reference = _keys(files["en"])
    for lang, data in files.items():
        assert _keys(data) == reference, lang
