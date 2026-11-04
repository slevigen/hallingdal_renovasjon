"""Tests for the calendar."""

from __future__ import annotations

from datetime import date, timedelta

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

ENTITY_ID = "calendar.testveien_1"


async def _events(hass: HomeAssistant, start: str, end: str) -> list[dict]:
    response = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {"entity_id": ENTITY_ID, "start_date_time": start, "end_date_time": end},
        blocking=True,
        return_response=True,
    )
    return response[ENTITY_ID]["events"]


async def test_state_and_next_event(hass: HomeAssistant, setup_integration) -> None:
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_OFF  # nothing today (4 Nov)
    assert state.attributes["friendly_name"] == "Testveien 1"
    assert state.attributes["message"] == "Matavfall"
    assert state.attributes["all_day"] is True
    assert state.attributes["start_time"] == "2026-11-06 00:00:00"
    assert state.attributes["description"] == "Hallingdal Renovasjon"


async def test_on_during_pickup_day(hass: HomeAssistant, setup_integration, freezer) -> None:
    freezer.move_to("2026-11-06 08:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    entity = hass.data["entity_components"][CALENDAR_DOMAIN].get_entity(ENTITY_ID)
    entity.async_write_ha_state()
    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_events_inside_range(hass: HomeAssistant, setup_integration) -> None:
    events = await _events(hass, "2026-11-06T00:00:00+01:00", "2026-11-21T00:00:00+01:00")
    assert [(e["start"], e["summary"]) for e in events] == [
        ("2026-11-06", "Matavfall"),
        ("2026-11-06", "Papp, papir og drikkekartong"),
        ("2026-11-20", "Restavfall"),
        ("2026-11-20", "Plastemballasje"),
    ]
    assert events[0]["end"] == "2026-11-07"
    assert events[0]["description"] == "Hallingdal Renovasjon"


async def test_range_boundaries(hass: HomeAssistant, setup_integration) -> None:
    # End is exclusive: a range ending at midnight 20 Nov excludes 20 Nov.
    events = await _events(hass, "2026-11-07T00:00:00+01:00", "2026-11-20T00:00:00+01:00")
    assert events == []
    # A range starting mid-day still includes that day's all-day events.
    events = await _events(hass, "2026-11-20T15:00:00+01:00", "2026-11-20T16:00:00+01:00")
    assert len(events) == 2


async def test_events_outside_range(hass: HomeAssistant, setup_integration) -> None:
    assert await _events(hass, "2026-10-01T00:00:00+02:00", "2026-11-01T00:00:00+01:00") == []
    assert await _events(hass, "2027-03-01T00:00:00+01:00", "2027-04-01T00:00:00+02:00") == []


async def test_all_events(hass: HomeAssistant, setup_integration) -> None:
    entity = hass.data["entity_components"][CALENDAR_DOMAIN].get_entity(ENTITY_ID)
    start = dt_util.start_of_local_day()
    events = await entity.async_get_events(hass, start, start + timedelta(days=90))
    assert len(events) == 13
    assert len({e.uid for e in events}) == 13
    assert all(type(e.start) is date for e in events)
