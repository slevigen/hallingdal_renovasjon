"""Client for the Norconsult ISY ProAktiv API used by Hallingdal Renovasjon.

Independent of Home Assistant: only aiohttp and the standard library.
See docs/api.md for the verified API behaviour.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from http import HTTPStatus
from typing import Any

import aiohttp

from .const import HALLINGDAL, REQUEST_TIMEOUT, USER_AGENT, Provider

_LOGIN_PATH = "/api/v1/renovasjon/login"
_PROPERTIES_PATH = "/api/v1/renovasjon/eiendommer"
_PICKUPS_PATH = "/api/v1/renovasjon/tomminger"

# An expired or invalid token gives HTTP 500 (not 401).
_AUTH_RETRY_STATUSES = frozenset({HTTPStatus.UNAUTHORIZED, HTTPStatus.INTERNAL_SERVER_ERROR})


class HallingdalRenovasjonApiError(Exception):
    """Base class for API errors."""


class ApiConnectionError(HallingdalRenovasjonApiError):
    """Network problem: timeout, DNS, TLS, connection refused."""


class ApiAuthError(HallingdalRenovasjonApiError):
    """Login gave no token, or a fresh token was rejected."""


class ApiResponseError(HallingdalRenovasjonApiError):
    """Unexpected status code or payload."""


@dataclass(frozen=True)
class Property:
    """A property (eiendom) from the address search."""

    id: str
    address: str
    municipality_number: str
    gnr: int
    bnr: int
    fnr: int
    snr: int


@dataclass(frozen=True)
class Pickup:
    """One scheduled pickup of one fraction."""

    date: date
    fraction_id: str
    fraction_name: str | None


class HallingdalRenovasjonApiClient:
    """Async client with lazy login and one transparent re-login on token expiry."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        provider: Provider = HALLINGDAL,
    ) -> None:
        """Initialise the client. The session is owned by the caller."""
        self._session = session
        self._provider = provider
        self._token: str | None = None
        self._login_lock = asyncio.Lock()

    async def async_login(self) -> None:
        """Log in and store the token from the ``Token`` response header."""
        async with self._login_lock:
            await self._login()

    async def async_search_properties(self, address: str) -> list[Property]:
        """Search properties matching an address (prefix search)."""
        data = await self._get_json(_PROPERTIES_PATH, {"adresse": address})
        return [_parse_property(item) for item in _as_list(data)]

    async def async_get_pickups(
        self, eiendom_id: str, date_from: date, date_to: date
    ) -> list[Pickup]:
        """Get scheduled pickups for a property in an inclusive date range."""
        data = await self._get_json(
            _PICKUPS_PATH,
            {
                "eiendomId": eiendom_id,
                "datoFra": date_from.isoformat(),
                "datoTil": date_to.isoformat(),
            },
        )
        return [_parse_pickup(item) for item in _as_list(data)]

    async def _login(self) -> None:
        """Log in. Caller must hold the login lock."""
        body = {
            "applikasjonsId": self._provider.application_id,
            "oppdragsgiverId": self._provider.client_id,
        }
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.post(
                    self._provider.base_url + _LOGIN_PATH,
                    json=body,
                    headers={"User-Agent": USER_AGENT},
                ) as response,
            ):
                token = response.headers.get("Token")
                status = response.status
        except (TimeoutError, aiohttp.ClientError) as err:
            msg = f"Login request failed: {err!r}"
            raise ApiConnectionError(msg) from err
        if not token:
            self._token = None
            msg = f"Login gave no token (HTTP {status})"
            raise ApiAuthError(msg)
        self._token = token

    async def _ensure_token(self) -> str:
        async with self._login_lock:
            if self._token is None:
                await self._login()
            assert self._token is not None  # noqa: S101 - _login sets it or raises
            return self._token

    async def _refresh_token(self, stale_token: str) -> str:
        """Log in again unless another task already replaced the stale token."""
        async with self._login_lock:
            if self._token is None or self._token == stale_token:
                await self._login()
            assert self._token is not None  # noqa: S101
            return self._token

    async def _get_json(self, path: str, params: dict[str, str]) -> Any:
        token = await self._ensure_token()
        status, data = await self._get(path, params, token)
        if status in _AUTH_RETRY_STATUSES:
            token = await self._refresh_token(token)
            status, data = await self._get(path, params, token)
            if status in _AUTH_RETRY_STATUSES:
                msg = f"Request to {path} rejected after re-login (HTTP {status})"
                raise ApiAuthError(msg)
        if status != HTTPStatus.OK:
            msg = f"Unexpected HTTP {status} from {path}"
            raise ApiResponseError(msg)
        return data

    async def _get(self, path: str, params: dict[str, str], token: str) -> tuple[int, Any]:
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.get(
                    self._provider.base_url + path,
                    params=params,
                    headers={"Token": token, "User-Agent": USER_AGENT},
                ) as response,
            ):
                if response.status != HTTPStatus.OK:
                    return response.status, None
                try:
                    return response.status, await response.json(content_type=None)
                except ValueError as err:
                    msg = f"Invalid JSON from {path}"
                    raise ApiResponseError(msg) from err
        except (TimeoutError, aiohttp.ClientError) as err:
            msg = f"Request to {path} failed: {err!r}"
            raise ApiConnectionError(msg) from err


def _as_list(data: Any) -> list[Any]:
    if not isinstance(data, list):
        msg = f"Expected a JSON list, got {type(data).__name__}"
        raise ApiResponseError(msg)
    return data


def _parse_property(item: Any) -> Property:
    try:
        return Property(
            id=str(item["id"]),
            address=str(item["adresse"]).strip(),
            municipality_number=str(item["kommuneNr"]),
            gnr=_to_int(item.get("gNr")),
            bnr=_to_int(item.get("bNr")),
            fnr=_to_int(item.get("fNr")),
            snr=_to_int(item.get("sNr")),
        )
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        msg = f"Unexpected property payload: {item!r}"
        raise ApiResponseError(msg) from err


def _parse_pickup(item: Any) -> Pickup:
    try:
        name = item.get("fraksjon")
        return Pickup(
            # "2026-11-06T00:00:00": a local date at midnight, no timezone.
            date=date.fromisoformat(str(item["dato"])[:10]),
            fraction_id=str(item["fraksjonId"]),
            fraction_name=(str(name).strip() or None) if name is not None else None,
        )
    except (KeyError, TypeError, ValueError, AttributeError) as err:
        msg = f"Unexpected pickup payload: {item!r}"
        raise ApiResponseError(msg) from err


def _to_int(value: Any) -> int:
    """Convert numeric strings such as ``"12"``; missing or empty means 0."""
    if value is None or value == "":
        return 0
    return int(value)
