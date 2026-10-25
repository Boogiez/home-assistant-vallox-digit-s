"""Retire only known obsolete entities belonging to this exact config entry.

No deletion of entities, recorder history, device records or configuration.
A user-disabled entity remains user-disabled. Current measurement IDs are kept.
"""
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN

RETIRED_KEYS = frozenset({
    "basic_fan_speed", "maximum_fan_speed",  # Unsupported semantics in 0.4.0
    "legacy_telegrams", "valid_telegrams",  # Orphans from passive 0.1.0
    "new_temperature_telegrams", "invalid_legacy_temperatures",
})


def retire_obsolete_entities(hass, entry):
    registry = er.async_get(hass)
    retired = {f"{entry.entry_id}_{key}" for key in RETIRED_KEYS}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (entity.platform == DOMAIN and entity.unique_id in retired
                and entity.disabled_by is None):
            registry.async_update_entity(entity.entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
