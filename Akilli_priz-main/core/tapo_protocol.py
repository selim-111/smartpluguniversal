"""
TP-Link Tapo Protocol — HTTP + RSA handshake + AES-CBC encryption.

Tapo cihazlar (P100, P105, P110, L510, L530 vb.) eski Kasa protokolünden
farklı olarak HTTP/80 portu üzerinden AES şifreli iletişim kurar ve
kullanıcı adı/şifre ile kimlik doğrulaması gerektirir.

İletişim Akışı:
    1. RSA Handshake — public key gönder, AES key al
    2. Login — şifreli kullanıcı adı/şifre ile token al
    3. Komut gönder — AES ile şifreli JSON payload

Gereksinimler:
    pip install cryptography requests
"""

import base64
import hashlib
import json
import logging
import time
from typing import Optional

from cryptography.hazmat.primitives import padding as sym_padding, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import requests

logger = logging.getLogger(__name__)


class TapoProtocol:
    """
    Tapo secure communication protocol handler.

    Flow:
        1. Generate RSA-1024 key pair
        2. Handshake — send public key, get encrypted AES key back
        3. Login — authenticate with hashed credentials, get session token
        4. Send encrypted commands using AES-CBC + session token
    """

    def __init__(self, ip: str, port: int = 80, timeout: float = 5.0):
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{ip}:{port}/app"
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.aes_key: Optional[bytes] = None
        self.aes_iv: Optional[bytes] = None

        # Generate RSA key pair for handshake
        self._private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=1024,
            backend=default_backend(),
        )
        self._public_key = self._private_key.public_key()

    def _get_public_key_pem(self) -> str:
        """PEM-encoded public key for handshake."""
        pem = self._public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return pem.decode("utf-8")

    def _aes_encrypt(self, data: str) -> bytes:
        """AES-128-CBC encrypt with PKCS7 padding."""
        padder = sym_padding.PKCS7(128).padder()
        padded = padder.update(data.encode("utf-8")) + padder.finalize()

        cipher = Cipher(
            algorithms.AES(self.aes_key),
            modes.CBC(self.aes_iv),
            backend=default_backend(),
        )
        encryptor = cipher.encryptor()
        return encryptor.update(padded) + encryptor.finalize()

    def _aes_decrypt(self, data: bytes) -> str:
        """AES-128-CBC decrypt with PKCS7 unpadding."""
        cipher = Cipher(
            algorithms.AES(self.aes_key),
            modes.CBC(self.aes_iv),
            backend=default_backend(),
        )
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(data) + decryptor.finalize()

        unpadder = sym_padding.PKCS7(128).unpadder()
        return (unpadder.update(decrypted) + unpadder.finalize()).decode("utf-8")

    def handshake(self) -> None:
        """
        Step 1: RSA Handshake.
        Send our public key to the device, receive AES key encrypted with it.
        """
        payload = {
            "method": "handshake",
            "params": {"key": self._get_public_key_pem()},
        }

        response = self.session.post(
            self.base_url,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("error_code", -1) != 0:
            raise ConnectionError(
                f"Tapo handshake hatası: error_code={result.get('error_code')}"
            )

        # Decrypt the AES key with our RSA private key
        encrypted_key = base64.b64decode(result["result"]["key"])
        decrypted = self._private_key.decrypt(
            encrypted_key,
            asym_padding.PKCS1v15(),
        )

        # First 16 bytes = AES key, next 16 bytes = IV
        self.aes_key = decrypted[:16]
        self.aes_iv = decrypted[16:32]

        logger.debug(f"Tapo handshake başarılı: {self.ip}")

    def login(self, username: str, password: str) -> None:
        """
        Step 2: Login with TP-Link account credentials.

        Args:
            username: TP-Link hesap e-posta adresi.
            password: TP-Link hesap şifresi.
        """
        # Username → SHA1 hash → base64
        username_hash = hashlib.sha1(username.encode("utf-8")).hexdigest()
        username_b64 = base64.b64encode(
            username_hash.encode("utf-8")
        ).decode("utf-8")

        # Password → base64
        password_b64 = base64.b64encode(
            password.encode("utf-8")
        ).decode("utf-8")

        login_payload = json.dumps({
            "method": "login_device",
            "params": {
                "username": username_b64,
                "password": password_b64,
            },
            "requestTimeMils": int(time.time() * 1000),
        })

        # Encrypt and wrap in securePassthrough
        encrypted = self._aes_encrypt(login_payload)
        secure_payload = {
            "method": "securePassthrough",
            "params": {
                "request": base64.b64encode(encrypted).decode("utf-8"),
            },
        }

        response = self.session.post(
            self.base_url,
            json=secure_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("error_code", -1) != 0:
            raise ConnectionError(
                f"Tapo login hatası: error_code={result.get('error_code')}"
            )

        # Decrypt response to get token
        encrypted_response = base64.b64decode(result["result"]["response"])
        decrypted = json.loads(self._aes_decrypt(encrypted_response))

        if decrypted.get("error_code", -1) != 0:
            raise PermissionError(
                f"Tapo kimlik doğrulama hatası: Kullanıcı adı veya şifre yanlış "
                f"(error_code={decrypted.get('error_code')})"
            )

        self.token = decrypted["result"]["token"]
        logger.info(f"Tapo login başarılı: {self.ip}")

    def send_request(self, method: str, params: dict = None) -> dict:
        """
        Step 3: Send an encrypted command.

        Args:
            method: Tapo API method name (e.g. "get_device_info").
            params: Method parameters.

        Returns:
            Decrypted response dict.

        Raises:
            ConnectionError: If not logged in or command fails.
        """
        if not self.token:
            raise ConnectionError(
                "Henüz login yapılmamış. Önce handshake() ve login() çağırın."
            )

        inner_payload = json.dumps({
            "method": method,
            "params": params or {},
            "requestTimeMils": int(time.time() * 1000),
        })

        encrypted = self._aes_encrypt(inner_payload)
        secure_payload = {
            "method": "securePassthrough",
            "params": {
                "request": base64.b64encode(encrypted).decode("utf-8"),
            },
        }

        url = f"{self.base_url}?token={self.token}"
        response = self.session.post(
            url,
            json=secure_payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()

        if result.get("error_code", -1) != 0:
            raise ConnectionError(
                f"Tapo komut hatası: error_code={result.get('error_code')}"
            )

        encrypted_response = base64.b64decode(result["result"]["response"])
        return json.loads(self._aes_decrypt(encrypted_response))
