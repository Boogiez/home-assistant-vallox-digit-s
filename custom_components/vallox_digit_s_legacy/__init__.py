"""Vallox Digit S: measurements and explicitly requested fan level 1–8."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from .const import CONF_CONNECTION, DOMAIN
from .coordinator import DigitSCoordinator
from .reader import ActiveReader
from .migration import retire_obsolete_entities

PLATFORMS = ["sensor", "button", "number", "fan", "select", "binary_sensor", "date"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    retire_obsolete_entities(hass, entry)
    reader = ActiveReader(entry.data[CONF_CONNECTION], control_enabled=True)
    coordinator = DigitSCoordinator(hass, entry, reader)

    @callback
    def on_stop(_event):
        coordinator.signal_stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_stop))
    try:
        await coordinator.async_config_entry_first_refresh()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        entry.async_on_unload(entry.add_update_listener(coordinator.async_options_updated))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        # Also stop an executor worker when setup is cancelled or the initial
        # refresh fails, before HA can start another instance on the same bus.
        await coordinator.async_stop()
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = hass.data[DOMAIN][entry.entry_id]
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await coordinator.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
