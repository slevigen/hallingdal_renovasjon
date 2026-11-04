"""Tests for the sensors."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import ATTR_DEVICE_CLASS, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.hallingdal_renovasjon.const import DOMAIN, UPDATE_INTERVAL

from .conftest import PICKUPS_URL, PROPERTY_ID

FRACTION_SENSORS = {
    "sensor.testveien_1_restavfall": "2026-11-20",
    "sensor.testveien_1_matavfall": "2026-11-06",
    "sensor.testveien_1_papir": "2026-11-06",
    "sensor.testveien_1_plast": "2026-11-20",
    "sensor.testveien_1_glass_metall": "2026-12-04",
}


async def test_entities_and_ids(hass: HomeAssistant, setup_integration) -> None:
    registry = er.async_get(hass)
    for entity_id, value in FRACTION_SENSORS.items():
        state = hass.states.get(entity_id)
        assert state is not None, entity_id
        assert state.state == value
        assert state.attributes[ATTR_DEVICE_CLASS] == SensorDeviceClass.DATE
    entry = registry.async_get("sensor.testveien_1_restavfall")
    assert entry.unique_id == f"{PROPERTY_ID}_restavfall"
    assert entry.translation_key == "restavfall"
    assert registry.async_get("sensor.testveien_1_neste_henting").unique_id == f"{PROPERTY_ID}_next"

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), setup_integration.entry_id)
    assert device.identifiers == {(DOMAIN, PROPERTY_ID)}
    assert device.name == "Testveien 1"
    assert device.manufacturer == "Hallingdal Renovasjon IKS"
    assert device.configuration_url.startswith("https://www.hallingdalrenovasjon.no/")
    assert {
        e.device_id for e in er.async_entries_for_config_entry(registry, setup_integration.entry_id)
    } == {device.id}


async def test_native_value_is_a_date(hass: HomeAssistant, setup_integration) -> None:
    entity = hass.data["entity_components"]["sensor"].get_entity("sensor.testveien_1_restavfall")
    assert entity.native_value == date(2026, 11, 20)
    assert type(entity.native_value) is not str


async def test_fraction_attributes(hass: HomeAssistant, setup_integration) -> None:
    attrs = hass.states.get("sensor.testveien_1_restavfall").attributes
    assert attrs["days_until"] == 16
    assert attrs["fraction_id"] == "9999"
    assert attrs["upcoming"] == ["2026-11-20", "2026-12-11", "2026-12-29"]
    assert attrs["friendly_name"] == "Testveien 1 Residual waste"


async def test_next_pickup_with_two_fractions_same_day(
    hass: HomeAssistant, setup_integration
) -> None:
    state = hass.states.get("sensor.testveien_1_neste_henting")
    assert state.state == "2026-11-06"
    assert state.attributes["days_until"] == 2
    assert state.attributes["fractions"] == ["Matavfall", "Papp, papir og drikkekartong"]


async def test_pickup_today_is_still_next_and_rolls_over_at_midnight(
    hass: HomeAssistant, setup_integration, freezer
) -> None:
    # Late on pickup day (local time): still "next", 0 days.
    freezer.move_to("2026-11-06 23:30:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    for entity_id in ("sensor.testveien_1_neste_henting", "sensor.testveien_1_matavfall"):
        entity = hass.data["entity_components"]["sensor"].get_entity(entity_id)
        entity.async_write_ha_state()
    state = hass.states.get("sensor.testveien_1_neste_henting")
    assert state.state == "2026-11-06"
    assert state.attributes["days_until"] == 0

    # Midnight local time: the listener rewrites state without a new fetch.
    freezer.move_to("2026-11-07 00:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.testveien_1_neste_henting")
    assert state.state == "2026-11-20"
    assert state.attributes["days_until"] == 13
    assert state.attributes["fractions"] == ["Restavfall", "Plastemballasje"]
    assert hass.states.get("sensor.testveien_1_matavfall").state == "2026-11-27"


async def test_days_until_uses_local_date(hass: HomeAssistant, setup_integration, freezer) -> None:
    # 23:30 UTC on 5 Nov is already 6 Nov in Oslo.
    freezer.move_to("2026-11-05 23:30:00+00:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    entity = hass.data["entity_components"]["sensor"].get_entity("sensor.testveien_1_neste_henting")
    assert entity.extra_state_attributes["days_until"] == 0


async def test_empty_schedule_gives_unknown(
    hass: HomeAssistant, setup_integration, mock_api, freezer
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups([])
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Sensors created earlier stay, now unknown rather than an error.
    assert hass.states.get("sensor.testveien_1_restavfall").state == STATE_UNKNOWN
    state = hass.states.get("sensor.testveien_1_neste_henting")
    assert state.state == STATE_UNKNOWN
    assert state.attributes["days_until"] is None
    assert state.attributes["fractions"] == []


async def test_network_error_makes_entities_unavailable(
    hass: HomeAssistant, setup_integration, mock_api, freezer
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(exc=TimeoutError())
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.testveien_1_neste_henting").state == STATE_UNAVAILABLE

    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(
        [{"dato": "2026-11-27T00:00:00", "fraksjonId": "9999", "fraksjon": "Restavfall"}]
    )
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.testveien_1_neste_henting").state == "2026-11-27"


async def test_missing_fraction_not_created(
    hass: HomeAssistant, config_entry, mock_api, freezer
) -> None:
    await hass.config.async_set_time_zone("Europe/Oslo")
    freezer.move_to("2026-11-04 10:00:00+01:00")
    mock_api.login()
    mock_api.pickups(
        [{"dato": "2026-11-20T00:00:00", "fraksjonId": "9999", "fraksjon": "Restavfall"}]
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.testveien_1_restavfall") is not None
    assert hass.states.get("sensor.testveien_1_glass_metall") is None


async def test_new_and_unknown_fractions_are_added_later(
    hass: HomeAssistant, setup_integration, mock_api, freezer
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(
        [{"dato": "2026-11-21T00:00:00", "fraksjonId": "42", "fraksjon": "Hageavfall"}]
    )
    freezer.tick(UPDATE_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.testveien_1_fraksjon_42")
    assert state.state == "2026-11-21"
    assert state.attributes["friendly_name"] == "Testveien 1 Hageavfall"
    entry = er.async_get(hass).async_get("sensor.testveien_1_fraksjon_42")
    assert entry.unique_id == f"{PROPERTY_ID}_fraksjon_42"


async def test_entities_survive_restart(hass: HomeAssistant, setup_integration, mock_api) -> None:
    """Reloading keeps ids; a fraction outside the new window stays as unknown."""
    entry = setup_integration
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(
        [{"dato": "2026-11-20T00:00:00", "fraksjonId": "9999", "fraksjon": "Restavfall"}]
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.testveien_1_restavfall").state == "2026-11-20"
    assert hass.states.get("sensor.testveien_1_glass_metall").state == STATE_UNKNOWN
    assert not [s.entity_id for s in hass.states.async_all("sensor") if s.entity_id.endswith("_2")]


async def test_switching_property_replaces_device(hass: HomeAssistant, setup_integration) -> None:
    """After reconfigure picks another property, the old device and entities go away."""
    entry = setup_integration
    new_id = "0b7e2d4a-1c3f-4e5a-8b9c-0d1e2f3a4b05"
    hass.config_entries.async_update_entry(
        entry,
        unique_id=new_id,
        title="Testveien 7",
        data={"eiendom_id": new_id, "address": "Testveien 7", "kommune_nr": "3320"},
    )
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [d.identifiers for d in devices] == [{(DOMAIN, new_id)}]
    entity_ids = {
        e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    }
    assert "sensor.testveien_7_neste_henting" in entity_ids
    assert "calendar.testveien_7" in entity_ids
    assert not any(e.startswith(("sensor.testveien_1", "calendar.testveien_1")) for e in entity_ids)
