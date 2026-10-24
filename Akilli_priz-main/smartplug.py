"""
Smart plug factory — doğru cihaz driver'ını oluşturur.

Desteklenen driver'lar:
    - "kasa"  → Kasa protokolü (HS100, HS110, HS200, HS300, KP105, KP115 vb.)
    - "tapo"  → Tapo protokolü (P100, P105, P110, L510, L530 vb.)
    - "auto"  → Kullanıcı adı/şifre varsa Tapo, yoksa Kasa
"""

from typing import Optional

from core.base_device import SmartDevice
from core.device import HS110Device
from core.tapo_device import TapoDevice


def create_device(
    ip: str,
    timeout: float = 2.0,
    driver: str = "auto",
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> SmartDevice:
    """
    Factory: IP ve driver tipine göre uygun cihaz client'ı oluşturur.

    Args:
        ip: Cihazın yerel ağdaki IP adresi.
        timeout: Bağlantı timeout süresi (saniye).
        driver: Cihaz tipi — "kasa", "tapo" veya "auto".
        username: TP-Link hesap e-postası (Tapo cihazlar için).
        password: TP-Link hesap şifresi (Tapo cihazlar için).

    Returns:
        SmartDevice instance (HS110Device veya TapoDevice).

    Raises:
        ValueError: Tapo seçilmiş ama credential eksikse.
    """
    if driver == "tapo" or (driver == "auto" and username and password):
        if not username or not password:
            raise ValueError(
                "Tapo cihazlar için kullanıcı adı ve şifre gereklidir."
            )
        device = TapoDevice(
            ip=ip,
            username=username,
            password=password,
            timeout=timeout,
        )
        device.connect()
        return device

    # Default: Kasa protocol (HS100, HS110, etc.)
    return HS110Device(ip=ip, timeout=timeout)
