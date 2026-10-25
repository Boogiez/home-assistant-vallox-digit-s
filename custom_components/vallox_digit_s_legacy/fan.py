"""Native fan speed for Assist and standard HA cards; never advertises power off."""
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .entity import DigitSEntity
from .features import minimum_speed, percentage_from_speed, speed_from_percentage
from .speed_control import SpeedControlError


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DigitSFan(hass.data[DOMAIN][entry.entry_id], entry)])


class DigitSFan(DigitSEntity, FanEntity):
    _attr_name = "Ilmanvaihto"
    _attr_supported_features = FanEntityFeature.SET_SPEED

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "fan")

    @property
    def available(self):
        return self.can_control and (self.coordinator.data or {}).get("fan_speed") is not None

    @property
    def is_on(self):
        value = (self.coordinator.data or {}).get("fan_speed")
        return value > 0 if value is not None else None

    @property
    def percentage(self):
        return percentage_from_speed((self.coordinator.data or {}).get("fan_speed"), minimum_speed(self.entry.options))

    @property
    def speed_count(self):
        return 9 - minimum_speed(self.entry.options)

    @property
    def extra_state_attributes(self):
        return {"speed_level": (self.coordinator.data or {}).get("fan_speed"),
                "percentage_meaning": "Position among allowed speeds, not airflow or electrical power",
                "minimum_level": minimum_speed(self.entry.options), "shutdown_supported": False}

    async def async_set_percentage(self, percentage):
        try:
            level = speed_from_percentage(percentage, minimum_speed(self.entry.options))
            await self.coordinator.async_set_fan_speed(level)
        except (ValueError, SpeedControlError) as exc:
            raise HomeAssistantError(str(exc)) from None
