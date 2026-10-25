"""Meaningful manual speed names and discrete Celsius-labelled requests."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import DigitSEntity
from .features import FAN_NAMES, TEMPERATURE_NAMES, minimum_speed
from .speed_control import SpeedControlError


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DigitSSelect(coordinator, entry, False), DigitSSelect(coordinator, entry, True)])


class DigitSSelect(DigitSEntity, SelectEntity):
    def __init__(self, coordinator, entry, heating):
        super().__init__(coordinator, entry, "temperature_select" if heating else "fan_mode_select")
        self.heating = heating
        self._attr_name = "Tuloilman lämpötilapyyntö" if heating else "Puhalluksen käsisäätö"
        self._attr_icon = "mdi:thermometer" if heating else "mdi:fan"

    @property
    def mapping(self):
        return TEMPERATURE_NAMES if self.heating else {k: v for k, v in FAN_NAMES.items() if k >= minimum_speed(self.entry.options)}

    @property
    def options(self):
        return list(self.mapping.values())

    @property
    def current_option(self):
        return self.mapping.get((self.coordinator.data or {}).get("heating_level" if self.heating else "fan_speed"))

    @property
    def available(self):
        return self.can_control and self.current_option is not None

    @property
    def extra_state_attributes(self):
        return ({"approximate_values": "≈ values inferred from contemporary LED-panel scale; not calibrated on this S unit",
                 "confirmed_steps": [1, 5, 8], "heater_enable_control": False}
                if self.heating else {})

    async def async_select_option(self, option):
        level = next((k for k, v in self.mapping.items() if v == option), None)
        if level is None:
            raise HomeAssistantError("Unsupported selection")
        try:
            if self.heating:
                await self.coordinator.async_set_heating_level(level)
            else:
                await self.coordinator.async_set_fan_speed(level)
        except SpeedControlError as exc:
            raise HomeAssistantError(str(exc)) from None
