"""Config flow: search an address, pick the property, done."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import (
    ApiAuthError,
    HallingdalRenovasjonApiClient,
    HallingdalRenovasjonApiError,
    Property,
)
from .const import (
    CONF_ADDRESS,
    CONF_MUNICIPALITY_NUMBER,
    CONF_PROPERTY_ID,
    DOMAIN,
    HALLINGDAL,
    LOGGER,
)

ADDRESS_SCHEMA = vol.Schema({vol.Required(CONF_ADDRESS): TextSelector()})
_LIST_MODE_MAX = 8


def property_label(prop: Property) -> str:
    """E.g. ``Testveien 1 (Gol, gnr 900/bnr 10/fnr 2)``."""
    municipality = HALLINGDAL.municipalities.get(prop.municipality_number, prop.municipality_number)
    cadastre = f"gnr {prop.gnr}/bnr {prop.bnr}"
    if prop.fnr > 0:
        cadastre += f"/fnr {prop.fnr}"
    return f"{prop.address} ({municipality}, {cadastre})"


def filter_properties(properties: list[Property]) -> list[Property]:
    """Keep properties in the service area, one per address + gnr/bnr/fnr, sorted."""
    unique: dict[tuple[str, str, int, int, int], Property] = {}
    for prop in properties:
        if prop.municipality_number not in HALLINGDAL.municipalities:
            continue
        key = (prop.address.casefold(), prop.municipality_number, prop.gnr, prop.bnr, prop.fnr)
        # Sectioned properties (same cadastre, different sNr) are shown once.
        unique.setdefault(key, prop)
    return sorted(unique.values(), key=_natural_key)


def _natural_key(prop: Property) -> tuple[Any, ...]:
    municipality = HALLINGDAL.municipalities.get(prop.municipality_number, "")
    parts = re.split(r"(\d+)", prop.address.casefold())
    return (
        municipality,
        tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in parts),
        prop.gnr,
        prop.bnr,
        prop.fnr,
    )


class HallingdalRenovasjonConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Hallingdal Renovasjon."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._properties: dict[str, Property] = {}

    def _client(self) -> HallingdalRenovasjonApiClient:
        return HallingdalRenovasjonApiClient(async_get_clientsession(self.hass))

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Step 1: address search."""
        return await self._async_step_address("user", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Switch the entry to another property; same steps as setup."""
        return await self._async_step_address("reconfigure", user_input)

    async def _async_step_address(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip()
            try:
                found = await self._client().async_search_properties(address)
            except HallingdalRenovasjonApiError as err:
                LOGGER.debug("Address search failed: %s", err)
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - config flows must not crash on surprises
                LOGGER.exception("Unexpected error during address search")
                errors["base"] = "unknown"
            else:
                properties = filter_properties(found)
                if properties:
                    self._properties = {p.id: p for p in properties}
                    return await self.async_step_property()
                errors["base"] = "no_results"
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(ADDRESS_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_property(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Step 2: pick one of the matching properties."""
        if user_input is not None:
            prop = self._properties[user_input[CONF_PROPERTY_ID]]
            data = {
                CONF_PROPERTY_ID: prop.id,
                CONF_ADDRESS: prop.address,
                CONF_MUNICIPALITY_NUMBER: prop.municipality_number,
            }
            if self.source == SOURCE_RECONFIGURE:
                entry = self._get_reconfigure_entry()
                if prop.id != entry.unique_id:
                    await self.async_set_unique_id(prop.id)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    entry, unique_id=prop.id, title=prop.address, data=data
                )
            await self.async_set_unique_id(prop.id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=prop.address, data=data)

        options = [
            SelectOptionDict(value=p.id, label=property_label(p)) for p in self._properties.values()
        ]
        field = (
            vol.Required(CONF_PROPERTY_ID, default=options[0]["value"])
            if len(options) == 1
            else vol.Required(CONF_PROPERTY_ID)
        )
        mode = (
            SelectSelectorMode.LIST
            if len(options) <= _LIST_MODE_MAX
            else SelectSelectorMode.DROPDOWN
        )
        return self.async_show_form(
            step_id="property",
            data_schema=vol.Schema(
                {field: SelectSelector(SelectSelectorConfig(options=options, mode=mode))}
            ),
            description_placeholders={"count": str(len(options))},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """Login failed; there are no credentials, so this is just 'try again'."""
        del entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Retry logging in."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._client().async_login()
            except ApiAuthError:
                errors["base"] = "invalid_auth"
            except HallingdalRenovasjonApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(self._get_reauth_entry())
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({}), errors=errors
        )
