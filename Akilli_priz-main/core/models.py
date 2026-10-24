"""
Data models for TP-Link HS110 device information and energy readings.
Uses dataclasses for clean, typed data structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DeviceInfo:
    """System information returned by get_sysinfo command."""
    ip: str = ""
    alias: str = ""
    model: str = ""
    mac: str = ""
    device_id: str = ""
    hardware_id: str = ""
    oem_id: str = ""
    software_version: str = ""
    hardware_version: str = ""
    relay_state: int = 0      # 0 = OFF, 1 = ON
    led_off: int = 0          # 0 = LED on, 1 = LED off
    rssi: int = 0             # WiFi signal strength
    on_time: int = 0          # seconds device has been on
    active_mode: str = ""
    feature: str = ""
    dev_name: str = ""

    @property
    def is_on(self) -> bool:
        """Whether the relay (power switch) is on."""
        return self.relay_state == 1

    @property
    def is_led_on(self) -> bool:
        """Whether the LED indicator is on."""
        return self.led_off == 0

    @classmethod
    def from_raw(cls, ip: str, raw: dict) -> "DeviceInfo":
        """Create DeviceInfo from raw get_sysinfo response dict."""
        return cls(
            ip=ip,
            alias=raw.get("alias", ""),
            model=raw.get("model", ""),
            mac=raw.get("mac", ""),
            device_id=raw.get("deviceId", ""),
            hardware_id=raw.get("hwId", ""),
            oem_id=raw.get("oemId", ""),
            software_version=raw.get("sw_ver", ""),
            hardware_version=raw.get("hw_ver", ""),
            relay_state=raw.get("relay_state", 0),
            led_off=raw.get("led_off", 0),
            rssi=raw.get("rssi", 0),
            on_time=raw.get("on_time", 0),
            active_mode=raw.get("active_mode", ""),
            feature=raw.get("feature", ""),
            dev_name=raw.get("dev_name", ""),
        )


@dataclass
class EnergyInfo:
    """Real-time energy measurement from emeter get_realtime command."""
    voltage_mv: int = 0       # millivolts
    current_ma: int = 0       # milliamps
    power_mw: int = 0         # milliwatts
    total_wh: int = 0         # total watt-hours since device powered on
    error_code: int = 0

    @property
    def voltage_v(self) -> float:
        """Voltage in volts."""
        return self.voltage_mv / 1000.0

    @property
    def current_a(self) -> float:
        """Current in amps."""
        return self.current_ma / 1000.0

    @property
    def power_w(self) -> float:
        """Power in watts."""
        return self.power_mw / 1000.0

    @classmethod
    def from_raw(cls, raw: dict) -> "EnergyInfo":
        """Create EnergyInfo from raw get_realtime response dict."""
        return cls(
            voltage_mv=raw.get("voltage_mv", 0),
            current_ma=raw.get("current_ma", 0),
            power_mw=raw.get("power_mw", 0),
            total_wh=raw.get("total_wh", 0),
            error_code=raw.get("err_code", 0),
        )


@dataclass
class DailyEnergyStat:
    """Daily energy consumption from emeter get_daystat command."""
    year: int = 0
    month: int = 0
    day: int = 0
    energy_wh: int = 0        # watt-hours for the day

    @classmethod
    def from_raw(cls, raw: dict) -> "DailyEnergyStat":
        return cls(
            year=raw.get("year", 0),
            month=raw.get("month", 0),
            day=raw.get("day", 0),
            energy_wh=raw.get("energy_wh", 0),
        )


@dataclass
class DeviceStatus:
    """Combined device status snapshot — used by the poller."""
    online: bool = False
    device_info: Optional[DeviceInfo] = None
    energy_info: Optional[EnergyInfo] = None
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Serialize to a simple dict for display or logging."""
        data = {
            "online": self.online,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.error:
            data["error"] = self.error
        if self.device_info:
            di = self.device_info
            data.update({
                "alias": di.alias,
                "model": di.model,
                "mac": di.mac,
                "power_state": "ON" if di.is_on else "OFF",
                "led": "ON" if di.is_led_on else "OFF",
                "rssi": di.rssi,
                "on_time_seconds": di.on_time,
            })
        if self.energy_info:
            ei = self.energy_info
            data.update({
                "voltage_v": ei.voltage_v,
                "current_a": ei.current_a,
                "power_w": ei.power_w,
                "total_wh": ei.total_wh,
            })
        return data
