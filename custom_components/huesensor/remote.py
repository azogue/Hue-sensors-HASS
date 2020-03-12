"""Hue remotes."""
from datetime import timedelta
import logging

from aiohue.sensors import (
    TYPE_ZGP_SWITCH,
    TYPE_ZLL_SWITCH,
)
from homeassistant.core import callback
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.components.hue.const import DOMAIN as HUE_DOMAIN
from homeassistant.components.hue.sensor_base import (
    SensorManager,
    GenericHueSensor,
    SENSOR_CONFIG_MAP,
)
from homeassistant.components.remote import (  # noqa: F401
    PLATFORM_SCHEMA,
    RemoteDevice,
)
from homeassistant.helpers.event import async_track_time_interval

from .hue_api_response import sensor_state, sensor_attributes

_LOGGER = logging.getLogger(__name__)

# Scan interval for remotes and binary sensors is set to < 1s
# just to ~ensure that an update is called for each HA tick,
# as using an exact 1s misses some of the ticks
DEFAULT_SCAN_INTERVAL = timedelta(seconds=0.5)

REMOTE_ICONS = {
    "RWL": "mdi:remote",
    "ROM": "mdi:remote",
    "ZGP": "mdi:remote",
    "FOH": "mdi:light-switch",
    "Z3-": "mdi:light-switch",
}


async def async_setup_platform(
    hass, config, async_add_entities, discovery_info=None
):
    """Initialise Hue Bridge connection."""
    for bridge_entry_id, bridge in hass.data[HUE_DOMAIN].items():
        sm: SensorManager = bridge.sensor_manager

        @callback
        def _check_new_remotes():
            """Check for new devices to be added to HA."""
            new_remotes = []
            api = bridge.api.sensors
            for item_id in api:
                sensor = api[item_id]
                if sensor.type not in (TYPE_ZGP_SWITCH, TYPE_ZLL_SWITCH):
                    continue

                existing = sm.current.get(sensor.uniqueid)
                if existing is not None:
                    continue

                sensor_config = SENSOR_CONFIG_MAP.get(sensor.type)
                if sensor_config is None:
                    continue

                base_name = sensor.name
                name = sensor_config["name_format"].format(base_name)

                new_remote = sensor_config["class"](sensor, name, bridge)
                sm.current[sensor.uniqueid] = new_remote
                new_remotes.append(new_remote)

                _LOGGER.debug(
                    "Setup remote %s: %s", sensor.type, sensor.uniqueid,
                )
            if new_remotes:
                async_add_entities(new_remotes)

        # Add listener to add discovered remotes
        sm.coordinator.async_add_listener(_check_new_remotes)
        bridge.reset_jobs.append(
            lambda: sm.coordinator.async_remove_listener(_check_new_remotes)
        )

        # await sm.coordinator.async_refresh()
        await sm.coordinator.async_request_refresh()

        # Set up updates at scan_interval
        async def _update_remotes(now=None):
            """Request a bridge data refresh to update states on remotes."""
            # TODO review why main integration is calling
            #  async_refresh instead of async_request_refresh
            await sm.coordinator.async_request_refresh()
            _LOGGER.debug("Update requested at %s", now)

        remote_sc = config.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        if remote_sc < sm.coordinator.update_interval:
            # Add listener to update remotes at high rate
            _update_listener = async_track_time_interval(
                hass, _update_remotes, remote_sc,
            )
            bridge.reset_jobs.append(
                lambda: sm.coordinator.async_remove_listener(_update_listener)
            )


class HueRemote(GenericHueSensor, RemoteDevice):
    """Class to hold Hue Remote entity info."""

    @property
    def state(self):
        """Return the state of the remote."""
        return sensor_state(self.sensor)

    @property
    def icon(self):
        """Icon to use in the frontend, if any."""
        return REMOTE_ICONS.get(self.sensor.type)

    @property
    def force_update(self):
        """Force update."""
        return True

    def turn_on(self, **kwargs):
        """Do nothing."""

    def turn_off(self, **kwargs):
        """Do nothing."""

    @property
    def device_state_attributes(self):
        """Return the device state attributes."""
        # TODO review attributes and device_info in UI
        return sensor_attributes(self.sensor)


SENSOR_CONFIG_MAP.update(
    {
        TYPE_ZLL_SWITCH: {"name_format": "{0}", "class": HueRemote},
        TYPE_ZGP_SWITCH: {"name_format": "{0}", "class": HueRemote},
    }
)
