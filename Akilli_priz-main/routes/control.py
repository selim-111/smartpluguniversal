"""
Device control endpoints — cihaza TCP üzerinden komut gönderir.
Frontend bu endpoint'leri kullanarak senin PC'n üzerinden cihazı kontrol eder.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from db.db_models import Device
from schemas import DeviceInfoResponse, EnergyResponse, ActionResponse
from smartplug import create_device
from core.base_device import SmartDevice
from config import settings

router = APIRouter(prefix="/api/devices", tags=["Cihaz Kontrolü"])


async def _get_device_from_db(device_id: int, db: AsyncSession) -> Device:
    """DB'den cihaz kaydını getir, yoksa 404 döndür."""
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cihaz bulunamadı (id={device_id})",
        )
    return device


def _connect_to_device(device: Device) -> SmartDevice:
    """DB kaydına göre doğru driver ile cihaz bağlantısı oluştur."""
    return create_device(
        ip=device.ip_address,
        timeout=settings.DEVICE_TIMEOUT,
        driver=device.driver or "auto",
        username=device.username,
        password=device.password,
    )


@router.get(
    "/{device_id}/info",
    response_model=DeviceInfoResponse,
    summary="Cihaz sistem bilgisi",
    description="Cihazdan gerçek zamanlı sistem bilgisi alır (model, MAC, güç durumu, LED, RSSI, vb.)",
)
async def device_info(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        info = hs.get_sysinfo()
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({db_device.ip_address}): {e}",
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Kimlik doğrulama hatası: {e}",
        )

    return DeviceInfoResponse(
        alias=info.alias,
        model=info.model,
        mac=info.mac,
        is_on=info.is_on,
        is_led_on=info.is_led_on,
        rssi=info.rssi,
        on_time=info.on_time,
        software_version=info.software_version,
        hardware_version=info.hardware_version,
    )


@router.get(
    "/{device_id}/energy",
    response_model=EnergyResponse,
    summary="Anlık enerji ölçümü",
    description="Cihazdan gerçek zamanlı voltaj, akım, güç ve toplam tüketim bilgisi alır.",
)
async def device_energy(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        energy = hs.get_realtime_energy()
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({db_device.ip_address}): {e}",
        )
    except NotImplementedError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return EnergyResponse(
        voltage_v=energy.voltage_v,
        current_a=energy.current_a,
        power_w=energy.power_w,
        total_wh=energy.total_wh,
    )


@router.post(
    "/{device_id}/on",
    response_model=ActionResponse,
    summary="Prizi aç",
)
async def turn_on(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        hs.turn_on()
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı: {e}",
        )

    return ActionResponse(
        success=True,
        message=f"'{db_device.name}' açıldı.",
    )


@router.post(
    "/{device_id}/off",
    response_model=ActionResponse,
    summary="Prizi kapat",
)
async def turn_off(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        hs.turn_off()
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı: {e}",
        )

    return ActionResponse(
        success=True,
        message=f"'{db_device.name}' kapatıldı.",
    )


@router.post(
    "/{device_id}/led-on",
    response_model=ActionResponse,
    summary="LED aç",
)
async def led_on(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        hs.set_led(True)
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı: {e}",
        )

    return ActionResponse(
        success=True,
        message=f"'{db_device.name}' LED açıldı.",
    )


@router.post(
    "/{device_id}/led-off",
    response_model=ActionResponse,
    summary="LED kapat",
)
async def led_off(device_id: int, db: AsyncSession = Depends(get_db)):
    db_device = await _get_device_from_db(device_id, db)

    try:
        hs = _connect_to_device(db_device)
        hs.set_led(False)
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı: {e}",
        )

    return ActionResponse(
        success=True,
        message=f"'{db_device.name}' LED kapatıldı.",
    )
