"""Verified measurements and explicitly unconfirmed raw settings."""
from datetime import datetime
from homeassistant.components.sensor import (
    SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, VERSION

SENSORS = [
    SensorEntityDescription(
        key=k, name=label, native_unit_of_measurement="°C",
        device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
    )
    for k, label in (
        ("temperature_outdoor_air", "Ulkoilma"), ("temperature_supply_air", "Tuloilma"),
        ("temperature_extract_air", "Poistoilma"), ("temperature_exhaust_air", "Jäteilma"),
    )
] + [
    SensorEntityDescription(key="fan_speed", name="Puhallintaso"),
    SensorEntityDescription(key="supply_temperature_gain", name="Tuloilman lämpenemä", native_unit_of_measurement="°C", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="exhaust_temperature_drop", name="Poistoilman jäähtymä", native_unit_of_measurement="°C", state_class=SensorStateClass.MEASUREMENT),
    SensorEntityDescription(key="temperature_recovery_efficiency", name="Tuloilman lämpenemäsuhde (arvio)", native_unit_of_measurement="%", state_class=SensorStateClass.MEASUREMENT),
] + [
    SensorEntityDescription(key=k, name=label, entity_category=EntityCategory.DIAGNOSTIC)
    for k, label in (
        ("register_a9_raw", "Rekisteri 0xA9 (raaka-arvo, merkitys vahvistamatta)"),
        ("register_a5_raw", "Rekisteri 0xA5 (raaka-arvo, merkitys vahvistamatta)"),
        ("read_requests", "Lukupyyntöjä"), ("read_responses", "Lukuvastauksia"),
        ("read_timeouts", "Lukuaikakatkaisuja"), ("invalid_values", "Hylättyjä arvoja"),
        ("last_error", "Viimeisin yhteysvirhe"), ("connection_state", "Yhteyden tila"),
        ("fan_speed_changes", "Puhallintason muutoksia"), ("previous_fan_speed", "Edellinen puhallintaso"),
        ("received_bytes", "Vastaanotettuja tavuja"), ("received_frames", "Vastaanotettuja kehyksiä"),
        ("checksum_errors", "Tarkistussummavirheitä"), ("bus_busy", "Väylä varattuna"),
        ("last_remote_fan_speed", "Ohjaimen viimeisin nopeusviesti"),
        ("capture_status", "Väylätallennuksen tila"), ("capture_frames", "Tallennettuja kehyksiä"),
        ("control_status", "Viimeisin nopeusohjaus"),
        ("heating_status", "Viimeisin lämpötilaohjaus"),
    )
] + [
    SensorEntityDescription(key="last_success_age", name="Viimeisimmästä vastauksesta", native_unit_of_measurement="s", entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key="capture_remaining", name="Tallennusta jäljellä", native_unit_of_measurement="s", entity_category=EntityCategory.DIAGNOSTIC),
    SensorEntityDescription(key="fan_speed_last_change", name="Viimeisin puhallintason muutos", device_class=SensorDeviceClass.TIMESTAMP, entity_category=EntityCategory.DIAGNOSTIC),
]

SENSORS += [
    SensorEntityDescription(key=k, name=label, native_unit_of_measurement=unit,
                            state_class=SensorStateClass.MEASUREMENT, **({"device_class": kind} if kind else {}))
    for k, label, unit, kind in (
        ("temperature_balance", "Ilman lämpötase", "°C", None),
        ("exhaust_temperature_ratio", "LTO:n poistoilman lämpötilasuhde", "%", None),
        ("airflow_estimate", "Ilmavirta (arvio)", "m³/h", None),
        ("airflow_lps_estimate", "Ilmavirta litroina (arvio)", "L/s", None),
        ("fan_power_estimate", "Puhaltimien teho (arvio)", "W", "power"),
        ("air_changes_estimate", "Ilman vaihtuvuus (arvio)", "1/h", None),
        ("supply_heat_gain_estimate", "Tuloilmaan siirtyvä lämpöteho (arvio)", "W", "power"),
        ("exhaust_heat_recovered_estimate", "Poistoilmasta siirtyvä lämpöteho (arvio)", "W", "power"),
    )
] + [
    SensorEntityDescription(key="filter_days_remaining", name="Suodattimien huoltoon", native_unit_of_measurement="d"),
    SensorEntityDescription(key="filter_due_date", name="Suodattimien seuraava huolto", device_class="date"),
    SensorEntityDescription(key="fan_mode_name", name="Puhalluksen käyttötapa"),
    SensorEntityDescription(key="post_heating_target_estimate", name="Tuloilman lämpötilapyyntö (asteikkoarvio)", native_unit_of_measurement="°C"),
    SensorEntityDescription(key="profile_configured", name="Laskentaprofiili", entity_category=EntityCategory.DIAGNOSTIC),
] + [
    SensorEntityDescription(key="din_airflow_" + key, name="DIN-vertailuilmavirta · " + name,
                            native_unit_of_measurement="m³/h", entity_category=EntityCategory.DIAGNOSTIC)
    for key, name in (("moisture", "kosteussuoja"), ("reduced", "alennettu"), ("normal", "normaali"), ("boost", "tehostus"))
]


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DigitSSensor(coordinator, entry, description) for description in SENSORS)


class DigitSSensor(CoordinatorEntity, SensorEntity):
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
    def native_value(self):
        value = (self.coordinator.data or {}).get(self.entity_description.key)
        if self.entity_description.device_class == SensorDeviceClass.TIMESTAMP:
            return datetime.fromisoformat(value) if value else None
        return value

    @property
    def extra_state_attributes(self):
        key = self.entity_description.key
        data = self.coordinator.data or {}
        result = dict(data.get("_sample_times", {}).get(key, {}))
        # Do not rewrite every temperature's recorder row every five seconds.
        # The dedicated last_success_age sensor carries the live age instead.
        result.pop("age_seconds", None)
        raw = data.get("raw_" + key)
        if raw is not None:
            result.update(last_raw_byte=f"0x{raw:02X}", raw_decimal=raw)
        if key in ("register_a9_raw", "register_a5_raw"):
            result["interpretation"] = "Merkitystä ja asteikkoa ei ole vahvistettu tälle DIGIT S:lle. Ei puhallintaso."
        if key == "last_remote_fan_speed":
            result.update(
                sender=data.get("last_remote_fan_sender"),
                meaning="Ohjaimen lähettämä arvo, ei vahvistus emokortin käyttämästä tasosta",
            )
        if key == "temperature_recovery_efficiency":
            result["calculation"] = "100 * (tuloilma - ulkoilma) / (poistoilma - ulkoilma)"
            result["limitation"] = "Jälkilämmitys voi sisältyä arvoon. Ei LTO:n vuosihyötysuhde."
        if key in ("airflow_estimate", "airflow_lps_estimate", "fan_power_estimate", "air_changes_estimate", "supply_heat_gain_estimate", "exhaust_heat_recovered_estimate"):
            result["measurement_type"] = "configured_curve_estimate"
            result["limitation"] = "Ei ilmavirran tai sähkönkulutuksen mittaus; erillisten puhaltimien tilaa tai tasapainoa ei tunneta."
        if key in ("exhaust_temperature_ratio", "exhaust_heat_recovered_estimate", "temperature_balance"):
            result["limitation"] = "Lämpötilavertailu. Ilmavirtojen tasapaino, puhallinlämpö ja häviöt vaikuttavat; ei vuosihyötysuhde eikä vastuksen tehomittaus."
        if key.startswith("din_airflow_"):
            result["basis"] = "Upstream DIN reference formula; not Finnish design airflow or an automatic control limit"
        if key == "post_heating_target_estimate":
            result["approximate"] = data.get("heating_level") not in (1, 5, 8)
            result["confirmed_steps"] = [1, 5, 8]
        if key == "profile_configured":
            options = self.coordinator.entry.options
            for name in ("house_area", "house_volume", "isolation_factor", "airflow_per_mode", "power_per_mode", "heating_power"):
                result[name] = options.get(name)
            result["bus_features_verified"] = ["four_temperatures", "fan_level_read", "fan_5_to_8_write", "temperature_step_read_write"]
            result["bus_features_unverified"] = ["heater_enable", "heater_active", "bypass", "faults", "device_service_interval", "fan_limits", "frost_thresholds"]
        return result
