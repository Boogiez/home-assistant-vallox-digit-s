"""Local diagnostic actions. Neither button changes Vallox settings."""
from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, VERSION
from homeassistant.util import dt as dt_util

BUTTONS = (
    ButtonEntityDescription(key="filter_changed_today", name="Suodattimet vaihdettu tänään", icon="mdi:air-filter"),
    ButtonEntityDescription(
        key="capture_bus", name="Tallenna väyläliikenne (120 s)",
        icon="mdi:record-circle-outline", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    ButtonEntityDescription(
        key="stop_capture", name="Keskeytä väylätallennus",
        icon="mdi:stop-circle-outline", entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DigitSButton(coordinator, entry, d) for d in BUTTONS)


class DigitSButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Vallox Digit S",
            "manufacturer": "Vallox", "model": "Ilmava Digit S (legacy active read)",
            "sw_version": VERSION,
        }

    @property
    def available(self):
        if self.coordinator._stopping:
            return False
        active = self.coordinator.capture_pending
        if self.entity_description.key == "filter_changed_today":
            return True
        return active if self.entity_description.key == "stop_capture" else not active

    async def async_press(self):
        if self.entity_description.key == "filter_changed_today":
            await self.coordinator.async_set_filter_date(dt_util.now().date())
        elif self.entity_description.key == "capture_bus":
            await self.coordinator.async_start_capture()
        else:
            await self.coordinator.async_cancel_capture()
