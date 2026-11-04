"""Shared fixtures.

HTTP is mocked with Home Assistant's ``AiohttpClientMocker`` (``aioclient_mock``).
aioresponses 0.7.9 is incompatible with aiohttp 3.14, which HA 2026.10 ships.
No test talks to the live service.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://tommeplan.vkr.no:9002"
LOGIN_URL = f"{BASE}/api/v1/renovasjon/login"
SEARCH_URL = f"{BASE}/api/v1/renovasjon/eiendommer"
PICKUPS_URL = f"{BASE}/api/v1/renovasjon/tomminger"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture (anonymised live responses, see docs/api.md)."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class MockApi:
    """Queue-based fake of the three endpoints.

    Each endpoint returns its queued responses in order; the last one repeats.
    """

    def __init__(self, mocker: AiohttpClientMocker) -> None:
        self.mocker = mocker
        self._queues: dict[str, deque[AiohttpClientMockResponse]] = {}
        for method, url in (("post", LOGIN_URL), ("get", SEARCH_URL), ("get", PICKUPS_URL)):
            self._queues[url] = deque()
            mocker.request(method, url, side_effect=self._side_effect(url))

    def _side_effect(
        self, url: str
    ) -> Callable[[str, URL, Any], Awaitable[AiohttpClientMockResponse]]:
        async def side_effect(method: str, req_url: URL, data: Any) -> AiohttpClientMockResponse:
            queue = self._queues[url]
            if not queue:
                msg = f"No queued response for {method} {req_url}"
                raise AssertionError(msg)
            return queue.popleft() if len(queue) > 1 else queue[0]

        return side_effect

    def _queue(self, url: str, method: str, **kwargs: Any) -> None:
        self._queues[url].append(AiohttpClientMockResponse(method, URL(url), **kwargs))

    def login(self, token: str | None = "token-1", status: int = 200) -> None:
        headers = {"Token": token, "tokenexpiry": "0"} if token else {}
        self._queue(LOGIN_URL, "post", status=status, headers=headers)

    def login_error(self, exc: Exception) -> None:
        self._queue(LOGIN_URL, "post", exc=exc)

    def search(self, json: Any = None, *, status: int = 200, **kwargs: Any) -> None:
        self._queue(SEARCH_URL, "get", status=status, json=json, **kwargs)

    def pickups(self, json: Any = None, *, status: int = 200, **kwargs: Any) -> None:
        self._queue(PICKUPS_URL, "get", status=status, json=json, **kwargs)

    def reset(self, url: str) -> None:
        """Forget queued responses for one endpoint."""
        self._queues[url].clear()

    def calls(self, url: str) -> list[tuple[str, URL, Any, dict[str, str]]]:
        return [c for c in self.mocker.mock_calls if str(c[1]).split("?")[0] == url]


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> MockApi:
    """Return a fake API bound to HA's aiohttp mocker."""
    return MockApi(aioclient_mock)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration in every test."""


PROPERTY_ID = "2f6c1a9e-7b3d-4c58-9e21-5a0d8f4b6c13"  # from fixtures/eiendommer.json
ENTRY_DATA = {"eiendom_id": PROPERTY_ID, "address": "Testveien 1", "kommune_nr": "3318"}


@pytest.fixture
async def oslo_tz(hass: Any) -> None:
    """Run HA in Norwegian local time (the default test zone is US/Pacific)."""
    await hass.config.async_set_time_zone("Europe/Oslo")


@pytest.fixture
def config_entry(hass: Any) -> Any:
    """Return a config entry for the anonymised test property, added to hass."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: PLC0415

    entry = MockConfigEntry(
        domain="hallingdal_renovasjon",
        title="Testveien 1",
        unique_id=PROPERTY_ID,
        data=ENTRY_DATA,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(hass: Any, config_entry: Any, mock_api: MockApi, freezer: Any) -> Any:
    """Set up the integration on 2026-11-04 10:00 Oslo time with the pickup fixture."""
    await hass.config.async_set_time_zone("Europe/Oslo")
    freezer.move_to("2026-11-04 10:00:00+01:00")
    mock_api.login()
    mock_api.pickups(load_fixture("tomminger.json"))
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
