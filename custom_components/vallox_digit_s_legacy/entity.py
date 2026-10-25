"""Common identity for newly added native entities."""
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, VERSION


class DigitSEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)}, "name": "Vallox Digit S",
            "manufacturer": "Vallox", "model": "Ilmava Digit S (legacy active read)",
            "sw_version": VERSION,
        }

    @property
    def can_control(self):
        return (self.coordinator.reader.control_enabled and not self.coordinator._stopping
                and not self.coordinator.capture_pending and not self.coordinator._wire_lock.locked())
