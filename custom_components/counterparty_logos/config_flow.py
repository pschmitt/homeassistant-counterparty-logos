"""Config flow for Counterparty Logos."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_BRANDFETCH_CLIENT_ID,
    CONF_IMAGE_PROVIDER,
    CONF_LOGO_DEV_PUBLISHABLE_KEY,
    CONF_LOGO_DEV_SECRET_KEY,
    CONF_NAME_ATTRIBUTES,
    DEFAULT_NAME_ATTRIBUTES,
    DOMAIN,
    PROVIDER_BRANDFETCH,
    PROVIDER_LOGO_DEV,
    REQUEST_TIMEOUT,
)
from .providers import AuthError, SearchError, search_brandfetch, search_logo_dev

_LOGGER = logging.getLogger(__name__)

_SECRET = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_TEXT = TextSelector()


def _schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Optional(
                CONF_LOGO_DEV_PUBLISHABLE_KEY,
                description={"suggested_value": defaults.get(CONF_LOGO_DEV_PUBLISHABLE_KEY)},
            ): _TEXT,
            vol.Optional(
                CONF_LOGO_DEV_SECRET_KEY,
                description={"suggested_value": defaults.get(CONF_LOGO_DEV_SECRET_KEY)},
            ): _SECRET,
            vol.Optional(
                CONF_BRANDFETCH_CLIENT_ID,
                description={"suggested_value": defaults.get(CONF_BRANDFETCH_CLIENT_ID)},
            ): _TEXT,
            vol.Required(
                CONF_IMAGE_PROVIDER,
                default=defaults.get(CONF_IMAGE_PROVIDER, PROVIDER_LOGO_DEV),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=[PROVIDER_LOGO_DEV, PROVIDER_BRANDFETCH],
                    translation_key=CONF_IMAGE_PROVIDER,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_NAME_ATTRIBUTES,
                default=defaults.get(CONF_NAME_ATTRIBUTES, DEFAULT_NAME_ATTRIBUTES),
            ): TextSelector(TextSelectorConfig(multiple=True)),
        }
    )


async def _async_validate(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Check the credentials; return a field -> error key map."""
    errors: dict[str, str] = {}
    session = async_get_clientsession(hass)
    publishable_key = data.get(CONF_LOGO_DEV_PUBLISHABLE_KEY)
    secret_key = data.get(CONF_LOGO_DEV_SECRET_KEY)
    client_id = data.get(CONF_BRANDFETCH_CLIENT_ID)

    if not publishable_key and not client_id:
        return {"base": "no_image_provider"}
    if data[CONF_IMAGE_PROVIDER] == PROVIDER_LOGO_DEV and not publishable_key:
        errors[CONF_LOGO_DEV_PUBLISHABLE_KEY] = "required_for_provider"
    if data[CONF_IMAGE_PROVIDER] == PROVIDER_BRANDFETCH and not client_id:
        errors[CONF_BRANDFETCH_CLIENT_ID] = "required_for_provider"

    if publishable_key:
        if not publishable_key.startswith("pk_"):
            errors[CONF_LOGO_DEV_PUBLISHABLE_KEY] = "invalid_publishable_key"
        else:
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    resp = await session.head(
                        "https://img.logo.dev/google.com",
                        params={"token": publishable_key, "fallback": "404"},
                    )
                if resp.status in (401, 403):
                    errors[CONF_LOGO_DEV_PUBLISHABLE_KEY] = "invalid_auth"
            except (TimeoutError, aiohttp.ClientError):
                errors["base"] = "cannot_connect"

    checks = []
    if secret_key:
        checks.append((CONF_LOGO_DEV_SECRET_KEY, search_logo_dev, secret_key))
    if client_id:
        checks.append((CONF_BRANDFETCH_CLIENT_ID, search_brandfetch, client_id))
    for field, search_fn, credential in checks:
        try:
            await search_fn(session, credential, "google")
        except AuthError:
            errors[field] = "invalid_auth"
        except SearchError as exc:
            _LOGGER.warning("Credential check for %s failed: %s", field, exc)
            errors["base"] = "cannot_connect"
    return errors


def _clean(user_input: dict[str, Any], *, keep_empty: bool = False) -> dict[str, Any]:
    """Strip values; drop empty ones unless they must override older data."""
    data = {k: v.strip() if isinstance(v, str) else v for k, v in user_input.items()}
    data[CONF_NAME_ATTRIBUTES] = [
        a.strip() for a in data.get(CONF_NAME_ATTRIBUTES) or [] if a.strip()
    ] or DEFAULT_NAME_ATTRIBUTES
    if keep_empty:
        for key in (
            CONF_LOGO_DEV_PUBLISHABLE_KEY,
            CONF_LOGO_DEV_SECRET_KEY,
            CONF_BRANDFETCH_CLIENT_ID,
        ):
            data.setdefault(key, "")
        return data
    return {k: v for k, v in data.items() if v not in ("", None)}


class CounterpartyLogosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Counterparty Logos."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the provider credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _clean(user_input)
            errors = await _async_validate(self.hass, data)
            if not errors:
                return self.async_create_entry(title="Counterparty Logos", data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return CounterpartyLogosOptionsFlow()


class CounterpartyLogosOptionsFlow(OptionsFlow):
    """Change credentials and provider settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the settings form."""
        errors: dict[str, str] = {}
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            # Empty values are kept so they override the initial entry data.
            data = _clean(user_input, keep_empty=True)
            errors = await _async_validate(self.hass, data)
            if not errors:
                return self.async_create_entry(data=data)
            current = user_input
        return self.async_show_form(step_id="init", data_schema=_schema(current), errors=errors)
