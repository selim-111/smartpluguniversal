"""
TP-Link Tapo Device Client — P100, P105, P110, L510, L530 ve diğer Tapo cihazlar.

Kasa cihazlarından farklı olarak HTTP/80 üzerinden iletişim kurar ve
TP-Link hesap bilgileri (e-posta + şifre) ile kimlik doğrulaması gerektirir.

Kullanım:
    device = TapoDevice("192.168.1.100", username="email@example.com", password="pass")
    device.connect()
    info = device.get_sysinfo()
    device.turn_on()
"""

import base64
import logging
from datetime import datetime
from typing import Optional

from core.base_device import SmartDevice
from core.tapo_protocol import TapoProtocol
from core.models import DeviceInfo, EnergyInfo, DeviceStatus

logger = logging.getLogger(__name__)


def _decode_nickname(value: str) -> str:
    """Tapo cihazlar nickname'i base64 ile gönderir."""
    if not value:
        return ""
    try:
        return base64.b64decode(value).decode("utf-8")
    except Exception:
        return value


class TapoDevice(SmartDevice):
    """
    HTTP client for TP-Link Tapo smart devices.

    Supports: P100, P105, P110, L510, L530, and other Tapo-series.
    """

    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        port: int = 80,
        timeout: float = 5.0,
    ):
        super().__init__(ip=ip, port=port, timeout=timeout)
        self.username = username
        self.password = password
        self._protocol: Optional[TapoProtocol] = None
        self._connected = False

    def connect(self) -> None:
        """Establish authenticated session with the device."""
        self._protocol = TapoProtocol(
            ip=self.ip, port=self.port, timeout=self.timeout
        )
        self._protocol.handshake()
        self._protocol.login(self.username, self.password)
        self._connected = True
        logger.info(f"Tapo cihaza bağlanıldı: {self.ip}")

    def _ensure_connected(self) -> None:
        """Reconnect if session expired."""
        if not self._connected:
            self.connect()

    def _send_command(self, method: str, params: dict = None) -> dict:
        """Send command with auto-reconnect on session expiry."""
        self._ensure_connected()
        try:
            return self._protocol.send_request(method, params)
        except (ConnectionError, Exception):
            # Session might have expired — reconnect once
            self.connect()
            return self._protocol.send_request(method, params)

    # ─────────────────────────────────────────────
    # SmartDevice interface
    # ─────────────────────────────────────────────

    def get_sysinfo(self) -> DeviceInfo:
        """Get device system information."""
        result = self._send_command("get_device_info")
        raw = result.get("result", {})

        return DeviceInfo(
            ip=self.ip,
            alias=_decode_nickname(raw.get("nickname", "")),
            model=raw.get("model", ""),
            mac=raw.get("mac", ""),
            device_id=raw.get("device_id", ""),
            hardware_id=raw.get("hw_id", ""),
            oem_id=raw.get("oem_id", ""),
            software_version=raw.get("fw_ver", ""),
            hardware_version=raw.get("hw_ver", ""),
            relay_state=1 if raw.get("device_on", False) else 0,
            rssi=raw.get("rssi", 0),
            on_time=raw.get("on_time", 0),
        )

    def turn_on(self) -> dict:
        """Turn the device ON."""
        logger.info(f"Turning ON (Tapo): {self.ip}")
        return self._send_command("set_device_info", {"device_on": True})

    def turn_off(self) -> dict:
        """Turn the device OFF."""
        logger.info(f"Turning OFF (Tapo): {self.ip}")
        return self._send_command("set_device_info", {"device_on": False})

    def set_led(self, on: bool) -> dict:
        """Set the LED indicator state."""
        logger.info(f"Setting LED {'ON' if on else 'OFF'} (Tapo): {self.ip}")
        return self._send_command("set_device_info", {"led_on": on})

    def set_alias(self, alias: str) -> dict:
        """Set device display name."""
        nickname_b64 = base64.b64encode(alias.encode("utf-8")).decode("utf-8")
        return self._send_command("set_device_info", {"nickname": nickname_b64})

    def get_realtime_energy(self) -> EnergyInfo:
        """Get real-time energy — only P110 and similar emeter-capable models."""
        result = self._send_command("get_energy_usage")
        raw = result.get("result", {})

        return EnergyInfo(
            voltage_mv=raw.get("voltage_mv", raw.get("voltage", 0)),
            current_ma=raw.get("current_ma", raw.get("current", 0)),
            power_mw=raw.get("power_mw", raw.get("power", 0)),
            total_wh=raw.get("total_wh", raw.get("total", 0)),
        )

    def get_device_status(self) -> DeviceStatus:
        """Fetch complete device status."""
        try:
            device_info = self.get_sysinfo()
            energy_info = None
            try:
                energy_info = self.get_realtime_energy()
            except Exception:
                pass  # Not all Tapo devices support energy metering

            return DeviceStatus(
                online=True,
                device_info=device_info,
                energy_info=energy_info,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Failed to get Tapo status from {self.ip}: {e}")
            return DeviceStatus(
                online=False,
                timestamp=datetime.now(),
                error=str(e),
            )
