"""Tests for the HA-independent API client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.hallingdal_renovasjon.api import (
    ApiAuthError,
    ApiConnectionError,
    ApiResponseError,
    HallingdalRenovasjonApiClient,
    Pickup,
    Property,
)
from custom_components.hallingdal_renovasjon.const import USER_AGENT, VERSION

from .conftest import LOGIN_URL, PICKUPS_URL, SEARCH_URL, MockApi, load_fixture

COMPONENT = Path(__file__).parents[1] / "custom_components/hallingdal_renovasjon"
D0, D1 = date(2026, 11, 4), date(2027, 2, 2)


@pytest.fixture
async def client(
    aioclient_mock: AiohttpClientMocker,
) -> AsyncIterator[HallingdalRenovasjonApiClient]:
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield HallingdalRenovasjonApiClient(session)
    await session.close()


def _tokens_sent(mock_api: MockApi, url: str) -> list[str]:
    return [headers["Token"] for _, _, _, headers in mock_api.calls(url)]


async def test_login_reads_token_from_header(client, mock_api) -> None:
    mock_api.login("abc")
    await client.async_login()
    assert client._token == "abc"
    ((_, _, body, headers),) = mock_api.calls(LOGIN_URL)
    assert body == {
        "applikasjonsId": "493dc350-a80a-4797-883b-56ae44fc7ff7",
        "oppdragsgiverId": "100",
    }
    assert headers["User-Agent"] == USER_AGENT


async def test_login_without_token_header_raises_auth_error(client, mock_api) -> None:
    mock_api.login(token=None, status=500)
    with pytest.raises(ApiAuthError):
        await client.async_login()


async def test_login_200_without_token_raises_auth_error(client, mock_api) -> None:
    mock_api.login(token=None, status=200)
    with pytest.raises(ApiAuthError):
        await client.async_login()


async def test_first_call_logs_in_lazily(client, mock_api) -> None:
    mock_api.login("lazy")
    mock_api.search(load_fixture("eiendommer.json"))
    await client.async_search_properties("Testveien 1")
    assert len(mock_api.calls(LOGIN_URL)) == 1
    assert _tokens_sent(mock_api, SEARCH_URL) == ["lazy"]
    (_, url, _, headers) = mock_api.calls(SEARCH_URL)[0]
    assert url.query["adresse"] == "Testveien 1"
    assert headers["User-Agent"] == USER_AGENT


async def test_token_is_reused(client, mock_api) -> None:
    mock_api.login("once")
    mock_api.search([])
    await client.async_search_properties("a")
    await client.async_search_properties("b")
    assert len(mock_api.calls(LOGIN_URL)) == 1


async def test_500_triggers_relogin_and_retry(client, mock_api) -> None:
    mock_api.login("old")
    mock_api.login("new")
    mock_api.search(status=500)
    mock_api.search(load_fixture("eiendommer.json"))
    result = await client.async_search_properties("Testveien 1")
    assert len(result) == 1
    assert _tokens_sent(mock_api, SEARCH_URL) == ["old", "new"]


async def test_401_triggers_relogin_and_retry(client, mock_api) -> None:
    mock_api.login("old")
    mock_api.login("new")
    mock_api.pickups(status=401)
    mock_api.pickups([])
    assert await client.async_get_pickups("x", D0, D1) == []
    assert _tokens_sent(mock_api, PICKUPS_URL) == ["old", "new"]


async def test_500_twice_raises_auth_error(client, mock_api) -> None:
    mock_api.login("one")
    mock_api.login("two")
    mock_api.search(status=500)
    with pytest.raises(ApiAuthError):
        await client.async_search_properties("Testveien 1")
    assert len(mock_api.calls(SEARCH_URL)) == 2


async def test_other_status_raises_response_error(client, mock_api) -> None:
    mock_api.login()
    mock_api.search({"message": "No HTTP resource was found"}, status=404)
    with pytest.raises(ApiResponseError):
        await client.async_search_properties("Testveien 1")


async def test_connection_error(client, mock_api) -> None:
    mock_api.login()
    mock_api.search(exc=aiohttp.ClientConnectionError("boom"))
    with pytest.raises(ApiConnectionError):
        await client.async_search_properties("Testveien 1")


async def test_timeout_is_connection_error(client, mock_api) -> None:
    mock_api.login()
    mock_api.pickups(exc=TimeoutError())
    with pytest.raises(ApiConnectionError):
        await client.async_get_pickups("x", D0, D1)


async def test_login_connection_error(client, mock_api) -> None:
    mock_api.login_error(aiohttp.ClientConnectorError(None, OSError("dns")))  # type: ignore[arg-type]
    with pytest.raises(ApiConnectionError):
        await client.async_login()


async def test_invalid_json_raises_response_error(client, mock_api) -> None:
    mock_api.login()
    mock_api.search(text="<html>")
    with pytest.raises(ApiResponseError):
        await client.async_search_properties("Testveien 1")


async def test_non_list_payload_raises_response_error(client, mock_api) -> None:
    mock_api.login()
    mock_api.search({"unexpected": True})
    with pytest.raises(ApiResponseError):
        await client.async_search_properties("Testveien 1")


async def test_parse_properties(client, mock_api) -> None:
    mock_api.login()
    mock_api.search(load_fixture("eiendommer_multiple.json"))
    result = await client.async_search_properties("Testveien")
    assert len(result) == 6
    assert result[1] == Property(
        id="0b7e2d4a-1c3f-4e5a-8b9c-0d1e2f3a4b02",
        address="Testveien 3",
        municipality_number="3324",
        gnr=900,
        bnr=11,
        fnr=2,
        snr=0,
    )
    assert result[3].snr == 2


async def test_parse_property_bad_number_raises(client, mock_api) -> None:
    mock_api.login()
    mock_api.search([{"id": "x", "adresse": "A", "kommuneNr": "3324", "gNr": "abc"}])
    with pytest.raises(ApiResponseError):
        await client.async_search_properties("A")


async def test_parse_pickups(client, mock_api) -> None:
    mock_api.login()
    mock_api.pickups(load_fixture("tomminger.json"))
    result = await client.async_get_pickups("some-id", D0, D1)
    assert len(result) == 13
    assert result[0] == Pickup(date(2026, 11, 6), "111106", "Matavfall")
    assert {p.fraction_id for p in result} == {"9999", "111106", "10095", "3200", "2612"}
    (_, url, _, _) = mock_api.calls(PICKUPS_URL)[0]
    assert dict(url.query) == {
        "eiendomId": "some-id",
        "datoFra": "2026-11-04",
        "datoTil": "2027-02-02",
    }


async def test_parse_pickup_without_name(client, mock_api) -> None:
    mock_api.login()
    mock_api.pickups([{"dato": "2026-11-06T00:00:00", "fraksjonId": "42", "fraksjon": " "}])
    (pickup,) = await client.async_get_pickups("x", D0, D1)
    assert pickup == Pickup(date(2026, 11, 6), "42", None)


async def test_parse_pickup_missing_field_raises(client, mock_api) -> None:
    mock_api.login()
    mock_api.pickups([{"fraksjonId": "42"}])
    with pytest.raises(ApiResponseError):
        await client.async_get_pickups("x", D0, D1)


async def test_concurrent_calls_log_in_once(client, mock_api) -> None:
    mock_api.login("shared")
    mock_api.search([])
    await asyncio.gather(client.async_search_properties("a"), client.async_search_properties("b"))
    assert len(mock_api.calls(LOGIN_URL)) == 1


async def test_concurrent_expiry_relogs_in_once(client, mock_api) -> None:
    """Two requests that both saw the same stale token trigger only one login."""
    client._token = "expired"
    mock_api.login("fresh")
    tokens = await asyncio.gather(
        client._refresh_token("expired"), client._refresh_token("expired")
    )
    assert tokens == ["fresh", "fresh"]
    assert len(mock_api.calls(LOGIN_URL)) == 1


def test_version_matches_manifest() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert manifest["version"] == VERSION


def test_api_and_const_have_no_homeassistant_imports() -> None:
    for module in ("api.py", "const.py"):
        assert "homeassistant" not in (COMPONENT / module).read_text()
