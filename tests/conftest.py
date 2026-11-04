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

    def calls(self, url: str) -> list[tuple[str, URL, Any, dict[str, str]]]:
        return [c for c in self.mocker.mock_calls if str(c[1]).split("?")[0] == url]


@pytest.fixture
def mock_api(aioclient_mock: AiohttpClientMocker) -> MockApi:
    """Return a fake API bound to HA's aiohttp mocker."""
    return MockApi(aioclient_mock)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow Home Assistant to load the custom integration in every test."""
