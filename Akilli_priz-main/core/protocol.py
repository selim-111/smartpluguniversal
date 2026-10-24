"""
TP-Link HS110 Smart Plug Protocol
XOR autokey encryption/decryption for TP-Link Smart Home protocol.
Runs on TCP port 9999 with a trivial XOR autokey cipher (initial key: 0xAB).
"""

import struct

INITIAL_KEY = 0xAB


def encrypt(message: str) -> bytes:
    """
    Encrypt a JSON command string for TP-Link Smart Home protocol.

    Format:
        [4-byte Big Endian length header] + [XOR autokey encrypted payload]

    XOR Autokey:
        - Start with key = 0xAB
        - For each character: encrypted = char XOR key, then key = encrypted

    Args:
        message: JSON command string (e.g. '{"system":{"get_sysinfo":{}}}')

    Returns:
        Encrypted bytes ready to send over TCP socket.
    """
    key = INITIAL_KEY
    result = struct.pack(">I", len(message))  # 4-byte Big Endian length

    for char in message:
        encrypted_byte = ord(char) ^ key
        key = encrypted_byte
        result += bytes([encrypted_byte & 0xFF])

    return result


def decrypt(data: bytes) -> str:
    """
    Decrypt a TP-Link Smart Home protocol response.

    Format:
        - First 4 bytes: Big Endian message length (skipped)
        - Remaining bytes: XOR autokey encrypted payload

    XOR Autokey Decryption:
        - Start with key = 0xAB
        - For each byte: decrypted = byte XOR key, then key = byte

    Args:
        data: Raw bytes received from TCP socket.

    Returns:
        Decrypted JSON string.
    """
    key = INITIAL_KEY
    result = []

    for byte in data[4:]:  # skip 4-byte length header
        decrypted = byte ^ key
        key = byte
        result.append(chr(decrypted))

    return "".join(result)
