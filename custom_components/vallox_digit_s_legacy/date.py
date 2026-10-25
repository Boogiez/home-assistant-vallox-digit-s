"""Filter change date, optionally using the home's existing helper as authority."""
from homeassistant.components.date import DateEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN
from .entity import DigitSEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DigitSFilterDate(hass.data[DOMAIN][entry.entry_id], entry)])


class DigitSFilterDate(DigitSEntity, DateEntity):
    _attr_name = "Suodattimet vaihdettu"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, "filter_change_date")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("filter_last_changed")

    async def async_set_value(self, value):
        await self.coordinator.async_set_filter_date(value)
