"""Support for ASUSROUTER devices."""
import logging

import voluptuous as vol

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PORT,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from aioasuswrt.asuswrt import AsusWrt

_LOGGER = logging.getLogger(__name__)

CONF_PUB_KEY = "pub_key"
CONF_SENSORS = "sensors"
CONF_SSH_KEY = "ssh_key"
CONF_ADD_ATTR = "add_attribute"
CONF_PUB_MQTT = "pub_mqtt"
CONF_SSID = "ssid"
CONF_TARGETHOST = "target_host"
CONF_PORT_EXTER = "external_port"
CONF_PORT_INNER = "internal_port"
CONF_PROTOCOL = "protocol"


CONF_COMMAND_LINE = "command_line"

DEFAULT_RETRY = 3

DOMAIN = "asusrouter"
CONF_ROUTERS = "routers"
DATA_ASUSWRT = DOMAIN
DEFAULT_SSH_PORT = 22



SERVICE_REBOOT = "reboot"
SERVICE_RUNCOMMAND = "run_command"
SERVICE_INITDEVICE = "init_device"
SERVICE_SET_PORT_FORWARD = "set_port_forward"
_IP_REBOOT_CMD = "reboot"
_SET_INITED_FLAG_CMD = "touch /etc/inited ; service restart_firewall"

SECRET_GROUP = "Password or SSH Key"

ROUTER_CONFIG = vol.Schema(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_USERNAME): cv.string,
        vol.Optional(CONF_PORT, default=DEFAULT_SSH_PORT): cv.port,
        vol.Exclusive(CONF_PASSWORD, SECRET_GROUP): cv.string,
        vol.Exclusive(CONF_SSH_KEY, SECRET_GROUP): cv.isfile,
        vol.Exclusive(CONF_PUB_KEY, SECRET_GROUP): cv.isfile,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_ROUTERS, default={}): vol.All(
                    cv.ensure_list,
                    vol.All([ROUTER_CONFIG]),
                ),
                vol.Optional(CONF_ADD_ATTR, default=False): cv.boolean,
                vol.Optional(CONF_PUB_MQTT, default=False): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


SERVICE_REBOOT_SCHEMA = vol.Schema({vol.Required(CONF_HOST): cv.string})

SERVICE_RUN_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_COMMAND_LINE): cv.string,
        vol.Required(CONF_HOST): cv.string,
    }
)

SERVICE_INIT_DEVICE_SCHEMA = SERVICE_RUN_COMMAND_SCHEMA

SERVICE_SET_PORTFORWARD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SSID): cv.string,
        vol.Optional(CONF_PORT_EXTER, default=5555): cv.port,
        vol.Optional(CONF_PORT_INNER, default=5555): cv.port,
        vol.Optional(CONF_PROTOCOL, default="TCP"): cv.string,
        vol.Required(CONF_TARGETHOST): cv.string,
    }
)

class AsusRouter(AsusWrt):
    """interface of a asusrouter."""

    def __init__(self, host, port, devicename, username, password, ssh_key):
        """Init function."""
        super().__init__(host, port, False, username, password, ssh_key)
        self._device_name = devicename
        self._host = host
        self._connect_failed = False
        self._add_attribute = False
        self._pub_mqtt = False
        self._ssid = None

    @property
    def device_name(self):
        """Return the device name of the router."""
        return self._device_name

    @property
    def host(self):
        """Return the host ip of the router."""
        return self._host

    @property
    def connect_failed(self):
        """Return the host ip of the router."""
        return self._connect_failed

    @property
    def pub_mqtt(self):
        """Return the host ip of the router."""
        return  self._pub_mqtt

    @property
    def add_attribute(self):
        """Return the host ip of the router."""
        return self._add_attribute

    @property
    def ssid(self):
        """Return the host ip of the router."""
        return self._ssid

    async def set_ssid(self, ssid):
        self._ssid = ssid

    async def set_add_attribute(self, add_attribute):
        self._add_attribute = add_attribute

    async def set_pub_mqtt(self, pub_mqtt):
        self._pub_mqtt = pub_mqtt

    async def run_cmdline(self, command_line):
        self._connect_failed = False
        try:
            await self.connection.async_run_command(command_line)
        except  Exception as e:
            self._connect_failed = True
            _LOGGER.error(e)

    async def reboot(self):
        await self.run_cmdline(_IP_REBOOT_CMD)

    async def run_command(self, command_line):
        await self.run_cmdline(command_line)

    async def set_port_forward(self, external_port, internal_port, protocol ,target_host):
        cmd = "nvram set vts_enable_x=1 ; nvram set vts_rulelist='<ruler>%s>%s>%s>%s>' ; "\
                   "nvram commit ; service restart_firewall" % (external_port,target_host,internal_port,protocol)
        await self.run_command(cmd)


async def async_setup(hass, config):
    """Set up the asusrouter component."""

    routers_conf = []

    if DOMAIN in config:
        routers_conf = config[DOMAIN][CONF_ROUTERS]

    routers = []
    for conf in routers_conf:
        router = AsusRouter(
            conf[CONF_HOST],
            conf[CONF_PORT],
            conf[CONF_NAME],
            conf[CONF_USERNAME],
            conf.get(CONF_PASSWORD, ""),
            conf.get(CONF_SSH_KEY, conf.get("pub_key", ""))
        )
        await router.set_add_attribute(config[DOMAIN][CONF_ADD_ATTR])
        await router.set_pub_mqtt(config[DOMAIN][CONF_PUB_MQTT])

#        await router.connection.async_connect()
#        if not router.is_connected:
#            _LOGGER.error("Unable to setup asusrouter component")
#            continue

        routers.append(router)

    hass.data[DATA_ASUSWRT] = routers

    hass.async_create_task(
        async_load_platform(hass, "sensor", DOMAIN, {}, config)
    )
#    hass.async_create_task(
#        async_load_platform(hass, "device_tracker", DOMAIN, {}, config)
#    )
    
    
    async def _reboot(call):
        """Restart a router."""
        devices = hass.data[DOMAIN]
        for device in devices:
            if device.host == call.data[CONF_HOST]:
                await device.reboot()
            
    hass.services.async_register(
        DOMAIN, SERVICE_REBOOT, _reboot, schema=SERVICE_REBOOT_SCHEMA
    )

    async def _run_command(call):
        """Restart a router."""
        devices = hass.data[DOMAIN]
        for device in devices:
            if device.host == call.data[CONF_HOST] or call.data[CONF_HOST] == "ALL":
                await device.run_command(call.data[CONF_COMMAND_LINE])

    hass.services.async_register(
        DOMAIN, SERVICE_RUNCOMMAND, _run_command, schema=SERVICE_RUN_COMMAND_SCHEMA
    )

    async def _init_device(call):
        """Restart a router."""
        devices = hass.data[DOMAIN]
        for device in devices:
            if device.host == call.data[CONF_HOST] or call.data[CONF_HOST] == "ALL":
                await device.run_command(call.data[CONF_COMMAND_LINE])
                await device.run_command(_SET_INITED_FLAG_CMD)

    hass.services.async_register(
        DOMAIN, SERVICE_INITDEVICE, _init_device, schema=SERVICE_INIT_DEVICE_SCHEMA
    )

    async def _set_port_forward(call):
        """Restart a router."""
        devices = hass.data[DOMAIN]
        for device in devices:
            if device.ssid == call.data[CONF_SSID]:
                await device.set_port_forward(
                    call.data[CONF_PORT_EXTER],
                    call.data[CONF_PORT_INNER],
                    call.data[CONF_PROTOCOL],
                    call.data[CONF_TARGETHOST]
                )

    hass.services.async_register(
        DOMAIN, SERVICE_SET_PORT_FORWARD, _set_port_forward, schema=SERVICE_SET_PORTFORWARD_SCHEMA
    )

    return True
          
