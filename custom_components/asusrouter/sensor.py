"""Asusrouter status sensors."""
import logging
import math
import ast
from datetime import datetime
from re import compile
from homeassistant.helpers.entity import Entity
from . import AsusRouter
from . import DATA_ASUSWRT

_LOGGER = logging.getLogger(__name__)

_IP_WAN_CMD = 'nvram get wan0_ipaddr'
_WIFI_NAME_CMD = 'nvram get wl1_ssid'
_IP_REBOOT_CMD = 'reboot'
_CONNECT_STATE_WAN_CMD = 'nvram get wan0_state_t'

_ROUTER_WAN_PROTO_COMMAND = 'nvram get wan0_proto'

_ROUTER_IS_INITED_COMMAND = 'find /etc/inited'
_RET_IS_INITED = '/etc/inited'

_ROUTER_RX_COMMAND = 'cat /sys/class/net/ppp0/statistics/rx_bytes'
_ROUTER_TX_COMMAND = 'cat /sys/class/net/ppp0/statistics/tx_bytes'

CHANGE_TIME_CACHE_DEFAULT = 5  # Default 60s

async def async_setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the asusrouter."""

    asusrouters = hass.data[DATA_ASUSWRT]

    devices = []
    for router in asusrouters:
        devices.append(AsuswrtRouterSensor(router.device_name, router))
        if router.add_attribute:
            devices.append(RouterWanIpSensor(router.device_name, router))
            devices.append(RouterConnectStateSensor(router.device_name, router))
            devices.append(RouterDownloadSensor(router.device_name, router))
            devices.append(RouterUploadSensor(router.device_name, router))
            devices.append(RouterDownloadSpeedSensor(router.device_name, router))
            devices.append(RouterUploadSpeedSensor(router.device_name, router))

    add_entities(devices, True)


class AsuswrtSensor(Entity):
    """Representation of a asusrouter."""

    def __init__(self, name, asusrouter):
        """Initialize the router."""
        self._name = name
        self._connected = False
        self._initialized = False
        self._asusrouter = asusrouter
        self._reboot = asusrouter.reboot
        self._wan_ip = None
        self._public_ip = None
        self._state = None
        self._rates = None
        self._speed = None
        self._rx_latest = None
        self._tx_latest = None
        self._cache_time = CHANGE_TIME_CACHE_DEFAULT
        self._latest_transfer_check = None
        self._transfer_rates_cache = None
        self._trans_cache_timer = None
        self._connect_state = None
        self._latest_transfer_data = 0, 0


    @property
    def state(self):
        """Return the state of the router."""
        return self._state

    @property
    def connect_state(self):
        """Return the link  state of the router."""
        return self._connect_state

    async def async_get_bytes_total(self):
        """Retrieve total bytes (rx an tx) from ASUSROUTER."""
        now = datetime.utcnow()
        if self._trans_cache_timer and self._cache_time > \
                (now - self._trans_cache_timer).total_seconds():
            return self._transfer_rates_cache

        rx = await self.async_get_rx()
        tx = await self.async_get_tx()
        return rx, tx
        
    async def async_get_rx(self):
        """Get current RX total given in bytes."""
        data = await self._asusrouter.connection.async_run_command(_ROUTER_RX_COMMAND)
        if data[0].isdigit():
            return int(data[0])
        return 0

    async def async_get_tx(self):
        """Get current RX total given in bytes."""
        data = await self._asusrouter.connection.async_run_command(_ROUTER_TX_COMMAND)
        if data[0].isdigit():
            return int(data[0])
        return 0
        
    async def async_get_current_transfer_rates(self):
        """Gets current transfer rates calculated in per second in bytes."""
        now = datetime.utcnow()
        data = await self.async_get_bytes_total()
        if self._rx_latest is None or self._tx_latest is None:
            self._latest_transfer_check = now
            self._rx_latest = data[0]
            self._tx_latest = data[1]
            return self._latest_transfer_data

        time_diff = now - self._latest_transfer_check
        if time_diff.total_seconds() < 30:
            return self._latest_transfer_data

        if data[0] < self._rx_latest:
            rx = data[0]
        else:
            rx = data[0] - self._rx_latest
        if data[1] < self._tx_latest:
            tx = data[1]
        else:
            tx = data[1] - self._tx_latest
        self._latest_transfer_check = now

        self._rx_latest = data[0]
        self._tx_latest = data[1]

        self._latest_transfer_data = (
            math.ceil(rx / time_diff.total_seconds()) if rx > 0 else 0,
            math.ceil(tx / time_diff.total_seconds()) if tx > 0 else 0)
        return self._latest_transfer_data

    async def async_get_public_ip(self):
        """Get current public ip."""
        ip_content = await self._asusrouter.connection.async_run_command(
            'wget -q -O getip pv.sohu.com/cityjson?ie=utf-8 ; cat getip')

        ip_dict = ast.literal_eval(compile(r'{[^}]+}').findall(ip_content[0])[0])
        ip = ip_dict.get('cip')
        location = ip_dict.get('cname')

        public_ip = None
        if ip:
            public_ip = "%s    %s" % (ip,location)
        else:
            ip_content = await self._asusrouter.connection.async_run_command(
                'wget -q -O getip http://members.3322.org/dyndns/getip ; cat getip')
            if ip_content:
                public_ip = ip_content[0]

        return public_ip

    async def async_update(self):
        """Fetch status from router."""
        if self._asusrouter.connect_failed:
            self._connected = False

        try:
            inited = await self._asusrouter.connection.async_run_command(
                _ROUTER_IS_INITED_COMMAND)
            if inited[0] == _RET_IS_INITED:
                self._initialized = True
            else:
                self._initialized = False

            lines = await self._asusrouter.connection.async_run_command(_IP_WAN_CMD)
            if lines:
                self._wan_ip = lines[0]

            connect = await self._asusrouter.connection.async_run_command(
                _CONNECT_STATE_WAN_CMD)
            if connect:
                self._connect_state = connect[0]

            ssid = await self._asusrouter.connection.async_run_command(
                _WIFI_NAME_CMD)
            if ssid:
                await self._asusrouter.set_ssid(ssid[0])

            self._public_ip = await self.async_get_public_ip()

            wan_proto = await self._asusrouter.connection.async_run_command(
                _ROUTER_WAN_PROTO_COMMAND)
            if wan_proto[0] == 'dhcp' or wan_proto[0] == 'static':
                self._rates = await self._asusrouter.async_get_bytes_total()
                self._speed = await self._asusrouter.async_get_current_transfer_rates()
            else:
                self._rates = await self.async_get_bytes_total()
                self._speed = await self.async_get_current_transfer_rates()

            self._connected = True
        except  Exception as e:
            self._connected = False
            _LOGGER.error(e)


class AsuswrtRouterSensor(AsuswrtSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "asusrouter_%s" % (self._name)

    @property
    def wan_ip(self):
        """Return the wan ip of router."""
        return self._wan_ip

    @property
    def download(self):
        """Return the total download."""
        if self._rates:
            return round(self._rates[0]/1000000000, 2)
        return 0

    @property
    def upload(self):
        """Return the total upload."""
        if self._rates:
            return round(self._rates[1]/1000000000, 2)
        return 0

    @property
    def download_speed(self):
        """Return the download speed."""
        if self._speed:
            return round(self._speed[0]/1000, 2)
        return 0

    @property
    def upload_speed(self):
        """Return the upload speed."""
        if self._speed:
            return round(self._speed[1]/1000, 2)
        return 0
      
    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {
            'initialized': self._initialized,
            'wan_ip': self._wan_ip,
            'public_ip': self._public_ip,
            'download': self.download,
            'upload': self.upload,
            'download_speed': self.download_speed,
            'upload_speed': self.upload_speed,
            'connect_state': self._connected,
            'ssid': self._asusrouter.ssid,
            'host': self._asusrouter.host,
        }

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state = self._connect_state


class RouterWanIpSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_wan_ip" % (self._name)

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state = self._wan_ip

class RouterConnectStateSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_connect_state" % (self._name)

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state = self._connected

class RouterDownloadSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_download" % (self._name)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "GiB"

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state =  super().download

class RouterUploadSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_upload" % (self._name)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "GiB"

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state =  super().upload

class RouterDownloadSpeedSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_download_speed" % (self._name)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "'KiB/s"

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state =  super().download_speed

class RouterUploadSpeedSensor(AsuswrtRouterSensor):
    """This is the interface class."""

    @property
    def name(self):
        """Return the name of the router."""
        return "%s_upload_speed" % (self._name)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "'KiB/s"

    @property  
    def device_state_attributes(self):
        """Return the state attributes."""	
        return {}

    async def async_update(self):
        """Fetch new state data for the sensor."""
        await super().async_update()
        self._state =  super().upload_speed