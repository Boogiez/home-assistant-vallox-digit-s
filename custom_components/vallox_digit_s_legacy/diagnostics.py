"""Downloadable diagnostics. Never include the serial URL or config-entry data."""
from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return {"status": "integration_not_loaded"}
    return coordinator.reader.diagnostics()
