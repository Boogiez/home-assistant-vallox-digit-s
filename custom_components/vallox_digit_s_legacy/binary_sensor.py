"""Actual communication and local maintenance, not unverified machine alarms."""
from homeassistant.components.binary_sensor import BinarySensorEntity
from .const import DOMAIN
from .entity import DigitSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DigitSBinary(coordinator, entry, key, name, kind) for key, name, kind in (
        ("connection_ok", "Mittausyhteys", "connectivity"),
        ("filter_due", "Suodattimien huolto ajankohtainen", "problem"),
    ))


class DigitSBinary(DigitSEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, key, name, kind):
        super().__init__(coordinator, entry, key)
        self.key = key
        self._attr_name = name
        self._attr_device_class = kind

    @property
    def is_on(self):
        return (self.coordinator.data or {}).get(self.key)

    @property
    def available(self):
        return self.is_on is not None
