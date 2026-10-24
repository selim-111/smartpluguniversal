"""
Cihaz keşif endpoint'i — ağdaki TP-Link cihazları otomatik bulur.

Desteklenen yöntemler:
  - auto (varsayılan): Önce UDP broadcast, bulamazsa TCP fallback
  - udp:  Sadece UDP broadcast (hızlı, ~3s)
  - tcp:  Sadece TCP subnet scan (güvenilir, ~10-30s)
"""

from fastapi import APIRouter, Query

from core.discovery import discover_devices_async
from schemas import DiscoveredDeviceResponse

router = APIRouter(prefix="/api/devices", tags=["Cihaz Keşfi"])


@router.get(
    "/discover",
    response_model=list[DiscoveredDeviceResponse],
    summary="Ağdaki TP-Link cihazları otomatik keşfet",
    description=(
        "Yerel ağdaki tüm TP-Link akıllı priz cihazlarını otomatik bulur.\n\n"
        "**Yöntemler:**\n"
        "- `auto` (varsayılan) — Önce UDP broadcast dener, bulamazsa TCP taramaya geçer\n"
        "- `udp` — Sadece UDP broadcast (hızlı, ~3s, firewall engelleyebilir)\n"
        "- `tcp` — Sadece TCP subnet tarama (güvenilir, ~10-30s)\n\n"
        "**Öneri:** İlk denemede `auto` kullanın. Cihaz bulunamazsa `tcp` deneyin."
    ),
)
async def discover(
    timeout: float = Query(default=3.0, description="UDP bekleme süresi (saniye)"),
    method: str = Query(
        default="auto",
        description="Tarama yöntemi: auto, udp, tcp",
        pattern="^(auto|udp|tcp)$",
    ),
):
    """
    Returns:
        Bulunan cihazların IP, alias, model, MAC bilgilerini içeren liste.
    """
    devices = await discover_devices_async(timeout=timeout, method=method)
    return [
        DiscoveredDeviceResponse(
            ip=d.ip,
            alias=d.alias,
            model=d.model,
            mac=d.mac,
            device_id=d.device_id,
            is_on=d.is_on,
            rssi=d.rssi,
            hardware_version=d.hardware_version,
            software_version=d.software_version,
        )
        for d in devices
    ]
