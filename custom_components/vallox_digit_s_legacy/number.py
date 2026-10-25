"""Manual 5–8 speed selection; displayed state is the mainboard readback."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, VERSION
from .speed_control import MIN_SPEED, MAX_SPEED, SpeedControlError, validate_speed
from .entity import DigitSEntity
from .features import minimum_speed


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DigitSSpeed(coordinator, entry), DigitSHeating(coordinator, entry), DigitSFilterInterval(coordinator, entry)])


class DigitSSpeed(CoordinatorEntity, NumberEntity):
    _attr_has_entity_name = True
    _attr_name = "Puhallintason asetus"
    _attr_icon = "mdi:fan"
    _attr_native_min_value = MIN_SPEED
    _attr_native_max_value = MAX_SPEED
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_fan_speed_control"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Vallox Digit S",
            "manufacturer": "Vallox", "model": "Ilmava Digit S (legacy active read)",
            "sw_version": VERSION,
        }

    @property
    def native_min_value(self):
        return minimum_speed(self.entry.options)

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("fan_speed")

    @property
    def available(self):
        return (self.coordinator.reader.control_enabled
                and not self.coordinator._stopping
                and not self.coordinator.capture_pending
                and not self.coordinator._wire_lock.locked()
                and self.native_value is not None)

    @property
    def extra_state_attributes(self):
        return {
            "state_source": "Koneelta luettu puhallintaso; ei oletettu komennon perusteella",
            "minimum_level": self.native_min_value,
            "last_command": (self.coordinator.data or {}).get("control_status"),
        }

    async def async_set_native_value(self, value):
        # HA's number service supplies floats even for whole-number steps.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HomeAssistantError("Valitse kokonaisluku väliltä 5–8.")
        if value not in range(MIN_SPEED, MAX_SPEED + 1):
            raise HomeAssistantError("Valitse kokonaisluku väliltä 5–8.")
        try:
            validate_speed(int(value))
            await self.coordinator.async_set_fan_speed(int(value))
        except SpeedControlError as exc:
            raise HomeAssistantError(str(exc)) from None


class DigitSHeating(DigitSSpeed):
    """Actual mainboard A4 readback; intentionally no guessed Celsius scale."""
    _attr_name = "Lämpötilaportaan asetus"
    _attr_icon = "mdi:thermometer-chevron-up"
    _attr_native_min_value = 1
    _attr_native_max_value = 8

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_heating_level_control"

    @property
    def native_min_value(self):
        return 1

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("heating_level")

    @property
    def extra_state_attributes(self):
        return {
            "state_source": "Emokortilta luettu A4-lämpötilaporras; ei mitattu tuloilma",
            "confirmed_celsius_anchors": {"1": 10, "5": 20, "8": 27},
            "scale": "Kahdeksan paneeliporrasta. Muiden portaiden tarkkoja asteita ei interpoloida.",
            "last_command": (self.coordinator.data or {}).get("heating_status"),
            "limits": "Ei ohjaa lämmityksen käyttökytkintä, vastustehoa tai suojauksia",
        }

    async def async_set_native_value(self, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in range(1, 9):
            raise HomeAssistantError("Valitse lämpötilaporras väliltä 1–8.")
        try:
            await self.coordinator.async_set_heating_level(int(value))
        except SpeedControlError as exc:
            raise HomeAssistantError(str(exc)) from None


class DigitSFilterInterval(DigitSEntity, NumberEntity):
    _attr_name = "Suodattimien huoltoväli"
    _attr_native_unit_of_measurement = "d"
    _attr_native_min_value = 1
    _attr_native_max_value = 730
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:calendar-range"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "filter_interval")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("filter_interval_days")

    async def async_set_native_value(self, value):
        await self.coordinator.async_set_filter_interval(value)
