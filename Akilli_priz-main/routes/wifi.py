"""
WiFi provisioning endpoints — cihazı mobil uygulama olmadan ağa bağlar.

Kullanım Akışı:
    1. Cihaz resetlenince kendi AP'sini açar (TP-LINK_Smart Plug_XXXX)
    2. PC'nin WiFi'sini cihazın AP'sine bağla
    3. POST /api/wifi/setup ile WiFi bilgilerini gönder
    4. Cihaz ağınıza bağlanır
    5. PC'yi tekrar normal ağa bağla

Not: Bu endpoint'ler DB gerektirmez — doğrudan IP ile cihaza bağlanır.
"""

from fastapi import APIRouter, HTTPException, status

from schemas import WifiNetwork, WifiSetupRequest, ActionResponse
from core.device import HS110Device
from config import settings

router = APIRouter(prefix="/api/wifi", tags=["WiFi Provisioning"])

# Cihaz AP modundayken varsayılan IP adresi
DEFAULT_AP_IP = "192.168.0.1"


@router.get(
    "/scan",
    response_model=list[WifiNetwork],
    summary="WiFi ağlarını tara",
    description=(
        "Cihazın çevresindeki WiFi ağlarını listeler. "
        "Cihaz AP modundayken (reset sonrası) çağırın. "
        
    ),
)
async def scan_wifi(ip: str = DEFAULT_AP_IP):
    """
    Query params:
        ip: Cihaz IP adresi (AP modunda genellikle 192.168.0.1)
    """
    try:
        hs = HS110Device(ip=ip, timeout=settings.DEVICE_TIMEOUT)
        networks = hs.get_scan_wifi_list()
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({ip}): {e}. "
                   f"PC'nizin WiFi'sini cihazın AP'sine (TP-LINK_Smart Plug_XXXX) bağladığınızdan emin olun.",
        )

    return [WifiNetwork(**n) for n in networks]


@router.post(
    "/setup",
    response_model=ActionResponse,
    summary="Cihazı WiFi ağına bağla",
    description=(
        "Cihaza WiFi SSID ve şifresini gönderir. "
        "Cihaz bu bilgileri kaydedip belirtilen ağa bağlanır. "
        "**TAPO/Kasa uygulamasının yaptığı işlemin aynısıdır.**"
    ),
)
async def setup_wifi(request: WifiSetupRequest, ip: str = DEFAULT_AP_IP):
    """
    Query params:
        ip: Cihaz IP adresi (AP modunda genellikle 192.168.0.1)

    Body:
        ssid: WiFi ağ adı
        password: WiFi şifresi
        key_type: Şifreleme tipi (varsayılan: 3 = WPA/WPA2)
    """
    try:
        hs = HS110Device(ip=ip, timeout=5.0)  # WiFi ayarı için daha uzun timeout
        result = hs.set_wifi(
            ssid=request.ssid,
            password=request.password,
            key_type=request.key_type,
        )
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({ip}): {e}. "
                   f"PC'nizin WiFi'sini cihazın AP'sine bağladığınızdan emin olun.",
        )

    # Hata kodu kontrolü
    err_code = result.get("netif", {}).get("set_stainfo", {}).get("err_code", -1)

    if err_code == 0:
        return ActionResponse(
            success=True,
            message=f"Cihaz '{request.ssid}' ağına bağlanıyor. "
                    f"Birkaç saniye sonra cihaz yeni IP'siyle ağınızda görünecektir.",
        )
    else:
        return ActionResponse(
            success=False,
            message=f"WiFi ayarı başarısız oldu (hata kodu: {err_code}).",
            data=result,
        )
