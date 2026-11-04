"""Tests for the config flow."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hallingdal_renovasjon.api import Property
from custom_components.hallingdal_renovasjon.config_flow import filter_properties, property_label
from custom_components.hallingdal_renovasjon.const import DOMAIN

from .conftest import ENTRY_DATA, LOGIN_URL, PROPERTY_ID, SEARCH_URL, load_fixture


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Iterator[AsyncMock]:
    with patch(
        "custom_components.hallingdal_renovasjon.async_setup_entry", return_value=True
    ) as mock:
        yield mock


async def _start(hass: HomeAssistant, address: str = "Testveien"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": f"  {address} "}
    )


def _options(result) -> list[dict[str, str]]:
    schema = result["data_schema"].schema
    (selector,) = schema.values()
    return selector.config["options"]


async def test_multiple_results_show_select_list(hass: HomeAssistant, mock_api) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer_multiple.json"))
    result = await _start(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "property"
    assert result["description_placeholders"] == {"count": "4"}
    labels = [o["label"] for o in _options(result)]
    # Out-of-area hit (Drammen) dropped, sectioned duplicate shown once, Flå sorted before Gol.
    assert labels == [
        "Testveien 7 (Flå, gnr 901/bnr 3)",
        "Testveien 1 (Gol, gnr 900/bnr 10)",
        "Testveien 3 (Gol, gnr 900/bnr 11/fnr 2)",
        "Testveien 5 (Gol, gnr 900/bnr 12)",
    ]
    (_, url, _, _) = mock_api.calls(SEARCH_URL)[0]
    assert url.query["adresse"] == "Testveien"

    chosen = "0b7e2d4a-1c3f-4e5a-8b9c-0d1e2f3a4b02"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": chosen}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Testveien 3"
    assert result["data"] == {"eiendom_id": chosen, "address": "Testveien 3", "kommune_nr": "3324"}
    assert result["result"].unique_id == chosen


async def test_single_result_is_preselected(hass: HomeAssistant, mock_api) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer.json"))
    result = await _start(hass, "Testveien 1")
    assert result["step_id"] == "property"
    (key,) = result["data_schema"].schema
    assert key.default() == PROPERTY_ID
    assert [o["label"] for o in _options(result)] == ["Testveien 1 (Krødsherad, gnr 999/bnr 1)"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": PROPERTY_ID}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA


async def test_no_results(hass: HomeAssistant, mock_api) -> None:
    mock_api.login()
    mock_api.search([])
    result = await _start(hass, "Testvegen 1")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_results"}

    # The user can correct the search in the same flow.
    mock_api.reset(SEARCH_URL)
    mock_api.search(load_fixture("eiendommer.json"))
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Testveien"}
    )
    assert result["step_id"] == "property"


async def test_only_out_of_area_results_is_no_results(hass: HomeAssistant, mock_api) -> None:
    mock_api.login()
    mock_api.search([load_fixture("eiendommer_multiple.json")[-1]])
    result = await _start(hass)
    assert result["errors"] == {"base": "no_results"}


async def test_network_error(hass: HomeAssistant, mock_api) -> None:
    mock_api.login_error(TimeoutError())
    result = await _start(hass)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_server_error_is_cannot_connect(hass: HomeAssistant, mock_api) -> None:
    mock_api.login()
    mock_api.search(status=500)
    result = await _start(hass)
    assert result["errors"] == {"base": "cannot_connect"}


async def test_unexpected_error(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.hallingdal_renovasjon.config_flow."
        "HallingdalRenovasjonApiClient.async_search_properties",
        side_effect=RuntimeError,
    ):
        result = await _start(hass)
    assert result["errors"] == {"base": "unknown"}


async def test_duplicate_property_aborts(hass: HomeAssistant, config_entry, mock_api) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer.json"))
    result = await _start(hass, "Testveien 1")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": PROPERTY_ID}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_switches_property(
    hass: HomeAssistant, config_entry, mock_api, mock_setup_entry
) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer_multiple.json"))
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Testveien"}
    )
    assert result["step_id"] == "property"
    new_id = "0b7e2d4a-1c3f-4e5a-8b9c-0d1e2f3a4b05"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": new_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.unique_id == new_id
    assert config_entry.title == "Testveien 7"
    assert config_entry.data == {
        "eiendom_id": new_id,
        "address": "Testveien 7",
        "kommune_nr": "3320",
    }


async def test_reconfigure_same_property(hass: HomeAssistant, config_entry, mock_api) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer.json"))
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Testveien 1"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": PROPERTY_ID}
    )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.unique_id == PROPERTY_ID


async def test_reconfigure_to_other_configured_property_aborts(
    hass: HomeAssistant, config_entry, mock_api
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: PLC0415

    other_id = "0b7e2d4a-1c3f-4e5a-8b9c-0d1e2f3a4b01"
    MockConfigEntry(domain=DOMAIN, unique_id=other_id, data={}).add_to_hass(hass)
    mock_api.login()
    mock_api.search(load_fixture("eiendommer_multiple.json"))
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"address": "Testveien"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"eiendom_id": other_id}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.unique_id == PROPERTY_ID


async def test_reauth(hass: HomeAssistant, config_entry, mock_api) -> None:
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    mock_api.login(token=None, status=500)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "invalid_auth"}

    mock_api.reset(LOGIN_URL)
    mock_api.login_error(TimeoutError())
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}

    mock_api.reset(LOGIN_URL)
    mock_api.login()
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


def test_label_with_festenummer() -> None:
    prop = Property("x", "Testveien 3", "3330", gnr=1, bnr=2, fnr=3, snr=0)
    assert property_label(prop) == "Testveien 3 (Hol, gnr 1/bnr 2/fnr 3)"


def test_natural_sort() -> None:
    props = [
        Property(str(n), f"Testveien {n}", "3324", gnr=1, bnr=n, fnr=0, snr=0) for n in (10, 2, 1)
    ]
    assert [p.address for p in filter_properties(props)] == [
        "Testveien 1",
        "Testveien 2",
        "Testveien 10",
    ]
