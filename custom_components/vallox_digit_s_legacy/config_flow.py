"""Select a serial port without querying or writing to Vallox on setup."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.selector import SerialPortSelector
from homeassistant.core import callback
from .const import DOMAIN, CONF_CONNECTION
from .features import DEFAULT_MINIMUM_FAN_LEVEL, checked_options


class DigitSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(_entry):
        return DigitSOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            connection = str(user_input.get(CONF_CONNECTION, "")).strip()
            if not connection.startswith(("esphome-hass://", "socket://", "/dev/")):
                errors[CONF_CONNECTION] = "invalid_connection"
            else:
                await self.async_set_unique_id(connection)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Vallox Digit S", data={CONF_CONNECTION: connection})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_CONNECTION): SerialPortSelector()}),
            errors=errors,
        )


class DigitSOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                checked_options(user_input)
            except (ValueError, TypeError):
                errors["base"] = "invalid_profile"
            else:
                return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        current = dict(self.config_entry.options)
        if user_input:
            current.update(user_input)
        fields = {
            vol.Optional("house_area", default=current.get("house_area", 0)): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
            vol.Optional("house_volume", default=current.get("house_volume", 0)): vol.All(vol.Coerce(float), vol.Range(min=0, max=100000)),
            vol.Optional("isolation_factor", default=current.get("isolation_factor", .4)): vol.All(vol.Coerce(float), vol.Range(min=0, max=1)),
            vol.Optional("airflow_per_mode", default=current.get("airflow_per_mode", "")): str,
            vol.Optional("power_per_mode", default=current.get("power_per_mode", "")): str,
            vol.Optional("heating_power", default=current.get("heating_power", 0)): vol.All(vol.Coerce(float), vol.Range(min=0, max=10000)),
            vol.Optional("minimum_fan_level", default=current.get("minimum_fan_level", DEFAULT_MINIMUM_FAN_LEVEL)): vol.All(vol.Coerce(float), vol.Range(min=1, max=8), vol.In(range(1, 9)), vol.Coerce(int)),
            vol.Optional("filter_date_entity", default=current.get("filter_date_entity", "")): str,
            vol.Optional("filter_interval_entity", default=current.get("filter_interval_entity", "")): str,
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields), errors=errors)
