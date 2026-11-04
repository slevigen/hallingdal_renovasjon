"""Tests for the coordinator."""

from __future__ import annotations

import logging
from datetime import date

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.hallingdal_renovasjon.api import Pickup

from .conftest import PICKUPS_URL, PROPERTY_ID, load_fixture

pytestmark = pytest.mark.usefixtures("oslo_tz")

# The fixture was fetched on 2026-11-04 for 90 days.
FROZEN = "2026-11-06 10:00:00+01:00"


@pytest.fixture
async def coordinator(hass: HomeAssistant, config_entry, mock_api, freezer):
    freezer.move_to(FROZEN)
    mock_api.login()
    mock_api.pickups(load_fixture("tomminger.json"))
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data


async def test_setup_and_request(hass: HomeAssistant, config_entry, coordinator, mock_api) -> None:
    assert config_entry.state is ConfigEntryState.LOADED
    (_, url, _, _) = mock_api.calls(PICKUPS_URL)[0]
    assert dict(url.query) == {
        "eiendomId": PROPERTY_ID,
        "datoFra": "2026-11-06",
        "datoTil": "2027-02-04",
    }


async def test_groups_per_fraction(coordinator) -> None:
    data = coordinator.data
    assert list(data.fractions) == ["9999", "111106", "10095", "3200", "2612"]
    rest = data.fractions["9999"]
    assert rest.key == "restavfall"
    assert rest.name == "Restavfall"
    assert rest.known
    assert rest.dates == (date(2026, 11, 20), date(2026, 12, 11), date(2026, 12, 29))
    # API name wins over the static table name.
    assert data.fractions["10095"].name == "Papp, papir og drikkekartong"
    assert data.fractions["10095"].key == "papir"
    assert [p.date for p in data.pickups] == sorted(p.date for p in data.pickups)


async def test_today_is_kept_and_past_is_dropped(coordinator) -> None:
    # 2026-11-06 is a pickup day (food + paper) and must still count as upcoming.
    assert coordinator.data.pickups[0].date == date(2026, 11, 6)
    past = Pickup(date(2026, 11, 5), "9999", "Restavfall")
    today = Pickup(date(2026, 11, 6), "9999", "Restavfall")
    result = coordinator.normalize([past, today], date(2026, 11, 6))
    assert result.pickups == (today,)
    assert result.fractions["9999"].dates == (date(2026, 11, 6),)


async def test_duplicates_are_merged(coordinator) -> None:
    p = Pickup(date(2026, 11, 6), "9999", "Restavfall")
    result = coordinator.normalize([p, p], date(2026, 11, 6))
    assert result.pickups == (p,)


async def test_empty_response(coordinator) -> None:
    result = coordinator.normalize([], date(2026, 11, 6))
    assert result.pickups == ()
    assert result.fractions == {}


async def test_name_falls_back_to_table(coordinator) -> None:
    result = coordinator.normalize([Pickup(date(2026, 11, 6), "3200", None)], date(2026, 11, 6))
    assert result.fractions["3200"].name == "Plastemballasje"
    assert result.pickups[0].fraction_name == "Plastemballasje"


async def test_unknown_fraction_without_name_warns_once(
    coordinator, caplog: pytest.LogCaptureFixture
) -> None:
    pickups = [Pickup(date(2026, 11, 6), "42", None), Pickup(date(2026, 11, 13), "42", None)]
    with caplog.at_level(logging.WARNING):
        first = coordinator.normalize(pickups, date(2026, 11, 6))
        coordinator.normalize(pickups, date(2026, 11, 6))
    fraction = first.fractions["42"]
    assert fraction.name == "Fraksjon 42"
    assert fraction.key == "fraksjon_42"
    assert not fraction.known
    warnings = [r for r in caplog.records if "Unknown fraction id 42" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].levelno == logging.WARNING


async def test_connection_error_gives_update_failed(
    hass: HomeAssistant, coordinator, mock_api
) -> None:
    previous = coordinator.data
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(exc=TimeoutError())
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.data is previous  # old data is kept


async def test_auth_error_starts_reauth(
    hass: HomeAssistant, config_entry, coordinator, mock_api
) -> None:
    mock_api.reset(PICKUPS_URL)
    mock_api.pickups(status=500)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert not coordinator.last_update_success
    flows = hass.config_entries.flow.async_progress_by_handler("hallingdal_renovasjon")
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_first_refresh_failure_retries_setup(
    hass: HomeAssistant, config_entry, mock_api
) -> None:
    mock_api.login_error(TimeoutError())
    assert not await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(hass: HomeAssistant, config_entry, coordinator) -> None:
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED
