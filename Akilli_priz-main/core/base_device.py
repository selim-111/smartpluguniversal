"""
Abstract base class for smart plug devices.
Defines the common interface that all device drivers (Kasa, Tapo, etc.) must implement.
"""

from abc import ABC, abstractmethod
from core.models import DeviceInfo, EnergyInfo, DeviceStatus


class SmartDevice(ABC):
    """Common interface for all smart plug devices."""

    def __init__(self, ip: str, port: int, timeout: float):
        self.ip = ip
        self.port = port
        self.timeout = timeout

    @abstractmethod
    def get_sysinfo(self) -> DeviceInfo:
        """Get device system information."""
        ...

    @abstractmethod
    def turn_on(self) -> dict:
        """Turn the device ON."""
        ...

    @abstractmethod
    def turn_off(self) -> dict:
        """Turn the device OFF."""
        ...

    @abstractmethod
    def set_led(self, on: bool) -> dict:
        """Set the LED indicator state."""
        ...

    @abstractmethod
    def set_alias(self, alias: str) -> dict:
        """Set device display name."""
        ...

    def get_realtime_energy(self) -> EnergyInfo:
        """Get real-time energy — override in devices with emeter support."""
        raise NotImplementedError("Bu cihaz enerji ölçümünü desteklemiyor.")

    def get_device_status(self) -> DeviceStatus:
        """Get combined status snapshot — override for full support."""
        raise NotImplementedError("Bu cihaz durum sorgulamayı desteklemiyor.")
