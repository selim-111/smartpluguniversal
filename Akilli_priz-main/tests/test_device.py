"""
Tests for HS110Device client.
Uses mock sockets to test command formatting and response parsing.
"""

import json
import sys
import os
import struct
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.protocol import encrypt, decrypt
from core.device import HS110Device
from core.models import DeviceInfo, EnergyInfo


def create_mock_response(response_dict: dict) -> bytes:
    """Create an encrypted response as the HS110 would send it."""
    response_json = json.dumps(response_dict, separators=(",", ":"))
    return encrypt(response_json)


class TestDeviceCommands:
    """Test that device methods send correct commands."""

    FAKE_IP = "192.168.1.100"

    SAMPLE_SYSINFO_RESPONSE = {
        "system": {
            "get_sysinfo": {
                "sw_ver": "1.5.6 Build 20180130",
                "hw_ver": "4.0",
                "model": "HS110(EU)",
                "deviceId": "ABCDEF1234567890",
                "oemId": "OEM123",
                "hwId": "HW123",
                "rssi": -55,
                "longitude_i": 0,
                "latitude_i": 0,
                "alias": "Test Plug",
                "status": "new",
                "mic_type": "IOT.SMARTPLUGSWITCH",
                "feature": "TIM:ENE",
                "mac": "AA:BB:CC:DD:EE:FF",
                "updating": 0,
                "led_off": 0,
                "relay_state": 1,
                "on_time": 3600,
                "active_mode": "schedule",
                "icon_hash": "",
                "dev_name": "Smart Wi-Fi Plug With Energy Monitoring",
                "err_code": 0,
            }
        }
    }

    SAMPLE_ENERGY_RESPONSE = {
        "emeter": {
            "get_realtime": {
                "voltage_mv": 230500,
                "current_ma": 195,
                "power_mw": 45200,
                "total_wh": 98500,
                "err_code": 0,
            }
        }
    }

    def _create_device_with_mock(self, response_dict: dict) -> tuple:
        """Create a device with mocked socket returning the given response."""
        device = HS110Device(self.FAKE_IP)
        mock_response = create_mock_response(response_dict)

        mock_socket = MagicMock()
        mock_socket.recv.side_effect = [mock_response, b""]

        return device, mock_socket

    @patch("core.device.socket.socket")
    def test_get_sysinfo(self, mock_socket_class):
        device, mock_sock = self._create_device_with_mock(
            self.SAMPLE_SYSINFO_RESPONSE
        )
        mock_socket_class.return_value = mock_sock

        info = device.get_sysinfo()

        assert isinstance(info, DeviceInfo)
        assert info.alias == "Test Plug"
        assert info.model == "HS110(EU)"
        assert info.mac == "AA:BB:CC:DD:EE:FF"
        assert info.is_on is True
        assert info.is_led_on is True
        assert info.rssi == -55
        assert info.on_time == 3600

    @patch("core.device.socket.socket")
    def test_get_realtime_energy(self, mock_socket_class):
        device, mock_sock = self._create_device_with_mock(
            self.SAMPLE_ENERGY_RESPONSE
        )
        mock_socket_class.return_value = mock_sock

        energy = device.get_realtime_energy()

        assert isinstance(energy, EnergyInfo)
        assert energy.voltage_mv == 230500
        assert energy.current_ma == 195
        assert energy.power_mw == 45200
        assert energy.total_wh == 98500
        assert energy.voltage_v == 230.5
        assert abs(energy.current_a - 0.195) < 0.001
        assert energy.power_w == 45.2

    @patch("core.device.socket.socket")
    def test_turn_on_sends_correct_command(self, mock_socket_class):
        device, mock_sock = self._create_device_with_mock(
            {"system": {"set_relay_state": {"err_code": 0}}}
        )
        mock_socket_class.return_value = mock_sock

        device.turn_on()

        # Verify sendall was called with encrypted data
        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]

        # Decrypt the sent data to verify the command
        decrypted = decrypt(sent_data)
        parsed = json.loads(decrypted)
        assert parsed == {"system": {"set_relay_state": {"state": 1}}}

    @patch("core.device.socket.socket")
    def test_turn_off_sends_correct_command(self, mock_socket_class):
        device, mock_sock = self._create_device_with_mock(
            {"system": {"set_relay_state": {"err_code": 0}}}
        )
        mock_socket_class.return_value = mock_sock

        device.turn_off()

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        decrypted = decrypt(sent_data)
        parsed = json.loads(decrypted)
        assert parsed == {"system": {"set_relay_state": {"state": 0}}}

    @patch("core.device.socket.socket")
    def test_set_led_on(self, mock_socket_class):
        device, mock_sock = self._create_device_with_mock(
            {"system": {"set_led_off": {"err_code": 0}}}
        )
        mock_socket_class.return_value = mock_sock

        device.set_led(True)

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        decrypted = decrypt(sent_data)
        parsed = json.loads(decrypted)
        assert parsed == {"system": {"set_led_off": {"off": 0}}}

    @patch("core.device.socket.socket")
    def test_connection_error(self, mock_socket_class):
        device = HS110Device(self.FAKE_IP)
        mock_sock = MagicMock()
        mock_sock.connect.side_effect = OSError("Connection refused")
        mock_socket_class.return_value = mock_sock

        try:
            device.get_sysinfo()
            assert False, "Should have raised ConnectionError"
        except ConnectionError:
            pass

    def test_device_repr(self):
        device = HS110Device("10.0.0.1", port=9999)
        assert repr(device) == "HS110Device(ip='10.0.0.1', port=9999)"


class TestDeviceInfo:
    """Test DeviceInfo model."""

    def test_from_raw(self):
        raw = {
            "alias": "Test",
            "model": "HS110",
            "mac": "AA:BB:CC:DD:EE:FF",
            "relay_state": 1,
            "led_off": 0,
            "rssi": -40,
            "on_time": 100,
        }
        info = DeviceInfo.from_raw("192.168.1.1", raw)
        assert info.alias == "Test"
        assert info.is_on is True
        assert info.is_led_on is True

    def test_from_raw_device_off(self):
        raw = {"relay_state": 0, "led_off": 1}
        info = DeviceInfo.from_raw("192.168.1.1", raw)
        assert info.is_on is False
        assert info.is_led_on is False


class TestEnergyInfo:
    """Test EnergyInfo model."""

    def test_from_raw(self):
        raw = {
            "voltage_mv": 220000,
            "current_ma": 500,
            "power_mw": 110000,
            "total_wh": 5000,
        }
        energy = EnergyInfo.from_raw(raw)
        assert energy.voltage_v == 220.0
        assert energy.current_a == 0.5
        assert energy.power_w == 110.0

    def test_from_raw_empty(self):
        energy = EnergyInfo.from_raw({})
        assert energy.voltage_mv == 0
        assert energy.power_w == 0.0


# Allow running with `python test_device.py`
if __name__ == "__main__":
    import unittest

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_class in [TestDeviceCommands, TestDeviceInfo, TestEnergyInfo]:
        for method_name in dir(test_class):
            if method_name.startswith("test_"):

                class TestWrapper(unittest.TestCase):
                    pass

                method = getattr(test_class, method_name)
                setattr(
                    TestWrapper,
                    method_name,
                    lambda self, m=method, c=test_class: m(c()),
                )
                suite.addTest(TestWrapper(method_name))

    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
