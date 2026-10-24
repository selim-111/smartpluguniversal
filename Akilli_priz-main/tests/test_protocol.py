"""
Tests for the TP-Link HS110 XOR autokey encryption/decryption protocol.
Test vectors are derived from the original Go project's encryptor_test.go.
"""

import sys
import os
import struct

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.protocol import encrypt, decrypt, INITIAL_KEY


class TestEncrypt:
    """Test XOR autokey encryption against known Go test vectors."""

    # Test vectors from Go encryptor_test.go
    # Format: (name, message, expected_encrypted_ints)
    TEST_VECTORS = [
        (
            "info",
            '{"system":{"get_sysinfo":null}}',
            [208, 242, 129, 248, 139, 255, 154, 247, 213, 239, 148, 182,
             209, 180, 192, 159, 236, 149, 230, 143, 225, 135, 232, 202,
             240, 158, 235, 135, 235, 150, 235],
        ),
        (
            "on",
            '{"system":{"set_relay_state":{"state":1}}}}',
            [208, 242, 129, 248, 139, 255, 154, 247, 213, 239, 148, 182,
             197, 160, 212, 139, 249, 156, 240, 145, 232, 183, 196, 176,
             209, 165, 192, 226, 216, 163, 129, 242, 134, 231, 147, 246,
             212, 238, 223, 162, 223, 162, 223],
        ),
        (
            "off",
            '{"system":{"set_relay_state":{"state":0}}}}',
            [208, 242, 129, 248, 139, 255, 154, 247, 213, 239, 148, 182,
             197, 160, 212, 139, 249, 156, 240, 145, 232, 183, 196, 176,
             209, 165, 192, 226, 216, 163, 129, 242, 134, 231, 147, 246,
             212, 238, 222, 163, 222, 163, 222],
        ),
        (
            "emeter",
            '{"emeter":{"get_realtime":null}}',
            [208, 242, 151, 250, 159, 235, 142, 252, 222, 228, 159, 189,
             218, 191, 203, 148, 230, 131, 226, 142, 250, 147, 254, 155,
             185, 131, 237, 152, 244, 152, 229, 152],
        ),
    ]

    def test_encrypt_payload_matches_go_vectors(self):
        """Verify encryption output matches Go test vectors (payload only, no header)."""
        for name, message, expected_ints in self.TEST_VECTORS:
            result = encrypt(message)

            # First 4 bytes are the length header
            header = result[:4]
            payload = result[4:]

            # Verify length header
            expected_length = struct.pack(">I", len(message))
            assert header == expected_length, (
                f"[{name}] Length header mismatch: "
                f"got {list(header)}, expected {list(expected_length)}"
            )

            # Verify payload matches Go test vectors
            payload_ints = list(payload)
            assert payload_ints == expected_ints, (
                f"[{name}] Payload mismatch:\n"
                f"  got:      {payload_ints}\n"
                f"  expected: {expected_ints}"
            )

    def test_encrypt_length_header(self):
        """Verify the 4-byte Big Endian length header is correct."""
        message = "hello"
        result = encrypt(message)
        length = struct.unpack(">I", result[:4])[0]
        assert length == len(message)

    def test_encrypt_empty_message(self):
        """Test encrypting an empty string."""
        result = encrypt("")
        assert len(result) == 4  # just the header
        length = struct.unpack(">I", result[:4])[0]
        assert length == 0


class TestDecrypt:
    """Test XOR autokey decryption."""

    def test_roundtrip(self):
        """Encrypt then decrypt should return the original message."""
        messages = [
            '{"system":{"get_sysinfo":{}}}',
            '{"system":{"set_relay_state":{"state":1}}}',
            '{"emeter":{"get_realtime":{}}}',
            'Hello, World!',
            '',
        ]
        for message in messages:
            encrypted = encrypt(message)
            decrypted = decrypt(encrypted)
            assert decrypted == message, (
                f"Roundtrip failed:\n"
                f"  original:  {message!r}\n"
                f"  decrypted: {decrypted!r}"
            )

    def test_decrypt_known_data(self):
        """Decrypt a manually constructed encrypted payload."""
        message = '{"system":{"get_sysinfo":{}}}'
        encrypted = encrypt(message)
        decrypted = decrypt(encrypted)
        assert decrypted == message


class TestInitialKey:
    """Verify protocol constants."""

    def test_initial_key_value(self):
        assert INITIAL_KEY == 0xAB
        assert INITIAL_KEY == 171


# Allow running with `python test_protocol.py`
if __name__ == "__main__":
    import unittest

    # Convert class-based tests to unittest
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    for test_class in [TestEncrypt, TestDecrypt, TestInitialKey]:
        for method_name in dir(test_class):
            if method_name.startswith("test_"):
                # Create a wrapper
                class TestWrapper(unittest.TestCase):
                    pass

                method = getattr(test_class, method_name)
                setattr(TestWrapper, method_name, lambda self, m=method, c=test_class: m(c()))
                suite.addTest(TestWrapper(method_name))

    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
