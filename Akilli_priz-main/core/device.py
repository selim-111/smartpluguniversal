"""
TP-Link HS110 Device Client
Communicates with the HS110 smart plug over TCP port 9999.
"""

import json
import socket
import logging
from datetime import datetime
from typing import Optional

from core.base_device import SmartDevice
from core.protocol import encrypt, decrypt
from core.models import DeviceInfo, EnergyInfo, DailyEnergyStat, DeviceStatus

logger = logging.getLogger(__name__)


class HS110Device(SmartDevice):
    """
    TCP client for TP-Link HS110 smart plug.

    Usage:
        device = HS110Device("192.168.1.100")
        info = device.get_sysinfo()
        device.turn_on()
        device.turn_off()
        energy = device.get_realtime_energy()
    """

    # TP-Link Smart Home protocol commands
    # Reference: https://github.com/softScheck/tplink-smartplug/blob/master/tplink-smarthome-commands.txt
    CMD_SYSINFO = {"system": {"get_sysinfo": {}}}
    CMD_ON = {"system": {"set_relay_state": {"state": 1}}}
    CMD_OFF = {"system": {"set_relay_state": {"state": 0}}}
    CMD_LED_ON = {"system": {"set_led_off": {"off": 0}}}
    CMD_LED_OFF = {"system": {"set_led_off": {"off": 1}}}
    CMD_EMETER_REALTIME = {"emeter": {"get_realtime": {}}}
    CMD_CLOUD_INFO = {"cnCloud": {"get_info": {}}}
    CMD_SCHEDULE_RULES = {"schedule": {"get_rules": {}}}

    def __init__(self, ip: str, port: int = 9999, timeout: float = 2.0):
        """
        Initialize HS110 device client.

        Args:
            ip: Device IP address on local network.
            port: TCP port (default 9999).
            timeout: Socket timeout in seconds (default 2.0).
        """
        super().__init__(ip=ip, port=port, timeout=timeout)

    def send_command(self, command: dict) -> dict:
        """
        Send a command to the device and return the parsed JSON response.

        Opens a new TCP connection for each command (stateless protocol).

        Args:
            command: Dictionary representing the TP-Link protocol command.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            ConnectionError: If cannot connect to device.
            TimeoutError: If device does not respond in time.
            ValueError: If response cannot be parsed as JSON.
        """
        message = json.dumps(command, separators=(",", ":"))
        logger.debug(f"Sending to {self.ip}:{self.port}: {message}")

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.ip, self.port))

            encrypted = encrypt(message)
            sock.sendall(encrypted)

            # Receive response — read until we have complete JSON
            response_data = b""
            while True:
                try:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                except socket.timeout:
                    break

            sock.close()

            if not response_data:
                raise ConnectionError(f"Empty response from {self.ip}")

            decrypted = decrypt(response_data)
            logger.debug(f"Received from {self.ip}: {decrypted}")

            return json.loads(decrypted)

        except socket.timeout:
            raise TimeoutError(
                f"Connection to {self.ip}:{self.port} timed out after {self.timeout}s"
            )
        except socket.error as e:
            raise ConnectionError(
                f"Cannot connect to {self.ip}:{self.port}: {e}"
            )

    # ─────────────────────────────────────────────
    # System commands
    # ─────────────────────────────────────────────

    def get_sysinfo(self) -> DeviceInfo:
        """Get device system information."""
        response = self.send_command(self.CMD_SYSINFO)
        raw = response.get("system", {}).get("get_sysinfo", {})
        return DeviceInfo.from_raw(self.ip, raw)

    def get_sysinfo_raw(self) -> dict:
        """Get raw system info response (unprocessed)."""
        response = self.send_command(self.CMD_SYSINFO)
        return response.get("system", {}).get("get_sysinfo", {})

    def turn_on(self) -> dict:
        """Turn the smart plug ON."""
        logger.info(f"Turning ON: {self.ip}")
        return self.send_command(self.CMD_ON)

    def turn_off(self) -> dict:
        """Turn the smart plug OFF."""
        logger.info(f"Turning OFF: {self.ip}")
        return self.send_command(self.CMD_OFF)

    def set_led(self, on: bool) -> dict:
        """
        Set the LED indicator state.

        Args:
            on: True to turn LED on, False to turn it off.
        """
        cmd = self.CMD_LED_ON if on else self.CMD_LED_OFF
        logger.info(f"Setting LED {'ON' if on else 'OFF'}: {self.ip}")
        return self.send_command(cmd)

    def set_alias(self, alias: str) -> dict:
        """Set device alias (display name)."""
        cmd = {"system": {"set_dev_alias": {"alias": alias}}}
        return self.send_command(cmd)

    @property
    def is_on(self) -> bool:
        """Check if the device relay is currently on."""
        info = self.get_sysinfo()
        return info.is_on

    # ─────────────────────────────────────────────
    # Energy metering commands
    # ─────────────────────────────────────────────

    def get_realtime_energy(self) -> EnergyInfo:
        """Get real-time energy measurements (voltage, current, power)."""
        response = self.send_command(self.CMD_EMETER_REALTIME)
        raw = response.get("emeter", {}).get("get_realtime", {})
        return EnergyInfo.from_raw(raw)

    def get_realtime_energy_raw(self) -> dict:
        """Get raw real-time energy response (unprocessed)."""
        response = self.send_command(self.CMD_EMETER_REALTIME)
        return response.get("emeter", {}).get("get_realtime", {})

    def get_daily_stats(self, year: int, month: int) -> list[DailyEnergyStat]:
        """
        Get daily energy statistics for a given month.

        Args:
            year: Year (e.g. 2026).
            month: Month (1-12).

        Returns:
            List of DailyEnergyStat for each day with data.
        """
        cmd = {"emeter": {"get_daystat": {"month": month, "year": year}}}
        response = self.send_command(cmd)
        days = (
            response
            .get("emeter", {})
            .get("get_daystat", {})
            .get("day_list", [])
        )
        return [DailyEnergyStat.from_raw(d) for d in days]

    def get_monthly_stats(self, year: int) -> list[dict]:
        """
        Get monthly energy statistics for a given year.

        Args:
            year: Year (e.g. 2026).

        Returns:
            List of monthly stats dicts.
        """
        cmd = {"emeter": {"get_monthstat": {"year": year}}}
        response = self.send_command(cmd)
        return (
            response
            .get("emeter", {})
            .get("get_monthstat", {})
            .get("month_list", [])
        )

    # ─────────────────────────────────────────────
    # Combined status (for polling)
    # ─────────────────────────────────────────────

    def get_device_status(self) -> DeviceStatus:
        """
        Fetch complete device status in one call — system info + energy.
        Used by the polling engine.

        Returns:
            DeviceStatus with all available data.
        """
        try:
            device_info = self.get_sysinfo()
            energy_info = self.get_realtime_energy()
            return DeviceStatus(
                online=True,
                device_info=device_info,
                energy_info=energy_info,
                timestamp=datetime.now(),
            )
        except Exception as e:
            logger.error(f"Failed to get status from {self.ip}: {e}")
            return DeviceStatus(
                online=False,
                timestamp=datetime.now(),
                error=str(e),
            )

    # ─────────────────────────────────────────────
    # Miscellaneous commands
    # ─────────────────────────────────────────────

    def get_cloud_info(self) -> dict:
        """Get cloud connection info."""
        return self.send_command(self.CMD_CLOUD_INFO)

    def get_schedule_rules(self) -> dict:
        """Get schedule rules."""
        return self.send_command(self.CMD_SCHEDULE_RULES)

    def set_countdown(self, seconds: int, action: int = 1, name: str = "rule") -> dict:
        """
        Set a countdown timer.

        Args:
            seconds: Delay in seconds before action triggers.
            action: 1 = turn on, 0 = turn off.
            name: Rule name.
        """
        cmd = {
            "count_down": {
                "add_rule": {
                    "enable": 1,
                    "delay": seconds,
                    "act": action,
                    "name": name,
                }
            }
        }
        return self.send_command(cmd)

    def scan_wifi(self) -> dict:
        """Scan for available WiFi networks."""
        cmd = {"netif": {"get_scaninfo": {"refresh": 1}}}
        return self.send_command(cmd)

    def get_scan_wifi_list(self) -> list[dict]:
        """
        Scan WiFi and return a clean list of networks.

        Returns:
            List of dicts with keys: ssid, key_type, rssi
        """
        raw = self.scan_wifi()
        ap_list = (
            raw
            .get("netif", {})
            .get("get_scaninfo", {})
            .get("ap_list", [])
        )
        return [
            {
                "ssid": ap.get("ssid", ""),
                "key_type": ap.get("key_type", 0),
                "rssi": ap.get("rssi", 0),
            }
            for ap in ap_list
        ]

    def set_wifi(self, ssid: str, password: str, key_type: int = 3) -> dict:
        """
        Connect the device to a WiFi network.

        This is the command that replaces the TAPO/Kasa mobile app's
        WiFi provisioning step. After reset, the device creates its own AP.
        Connect to that AP, then call this method to configure WiFi.

        Args:
            ssid: WiFi network name.
            password: WiFi password.
            key_type: Encryption type (0=none, 2=WEP, 3=WPA/WPA2).

        Returns:
            Device response dict.
        """
        cmd = {
            "netif": {
                "set_stainfo": {
                    "ssid": ssid,
                    "password": password,
                    "key_type": key_type,
                }
            }
        }
        logger.info(f"Setting WiFi to '{ssid}' on {self.ip}")
        return self.send_command(cmd)

    def __repr__(self) -> str:
        return f"HS110Device(ip='{self.ip}', port={self.port})"

