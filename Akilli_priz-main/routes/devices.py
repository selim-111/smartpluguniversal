"""
Device CRUD endpoints — kayıt, listeleme, güncelleme, silme.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from db.db_models import Device
from schemas import (
    DeviceRegisterRequest,
    DeviceUpdateRequest,
    DeviceResponse,
    ActionResponse,
)
from smartplug import create_device
from config import settings

router = APIRouter(prefix="/api/devices", tags=["Cihaz Yönetimi"])


@router.post(
    "/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni cihaz kaydet",
    description="IP adresi üzerinden cihaza bağlanır, MAC adresini alır ve verilen isimle veritabanına kaydeder.",
)
async def register_device(
    request: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    # 1) Cihaza bağlan ve MAC adresini al
    try:
        plug = create_device(
            ip=request.ip,
            timeout=settings.DEVICE_TIMEOUT,
            driver=request.driver,
            username=request.username,
            password=request.password,
        )
        info = plug.get_sysinfo()
        mac_address = info.mac
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({request.ip}): {e}",
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Kimlik doğrulama hatası: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cihaz bilgisi alınamadı: {e}",
        )

    if not mac_address:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cihazdan MAC adresi alınamadı.",
        )

    # 2) İsmi cihazın kendisine de yaz (TAPO uygulamasındaki gibi)
    try:
        plug.set_alias(request.name)
    except Exception:
        pass  # İsim yazılamazsa bile DB'ye kaydetmeye devam et

    # 3) Aynı MAC ile kayıtlı cihaz var mı kontrol et
    existing = await db.execute(
        select(Device).where(Device.mac_address == mac_address)
    )
    existing_device = existing.scalar_one_or_none()

    if existing_device:
        # MAC zaten kayıtlı — IP, isim ve credential bilgilerini güncelle
        existing_device.name = request.name
        existing_device.ip_address = request.ip
        existing_device.driver = request.driver or "auto"
        existing_device.username = request.username
        existing_device.password = request.password
        await db.flush()
        await db.refresh(existing_device)
        return existing_device

    # 4) Yeni cihaz kaydı oluştur
    new_device = Device(
        mac_address=mac_address,
        name=request.name,
        ip_address=request.ip,
        driver=request.driver or "auto",
        username=request.username,
        password=request.password,
    )
    db.add(new_device)
    await db.flush()
    await db.refresh(new_device)
    return new_device


@router.get(
    "",
    response_model=list[DeviceResponse],
    summary="Tüm cihazları listele",
)
async def list_devices(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).order_by(Device.id))
    devices = result.scalars().all()
    return devices


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Tek cihaz bilgisi",
)
async def get_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cihaz bulunamadı (id={device_id})",
        )
    return device


@router.put(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Cihaz ismini güncelle",
)
async def update_device(
    device_id: int,
    request: DeviceUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cihaz bulunamadı (id={device_id})",
        )

    # İsmi cihazın kendisine de yaz
    try:
        plug = create_device(
            ip=device.ip_address,
            timeout=settings.DEVICE_TIMEOUT,
            driver=device.driver or "auto",
            username=device.username,
            password=device.password,
        )
        plug.set_alias(request.name)
    except (ConnectionError, TimeoutError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cihaza bağlanılamadı ({device.ip_address}): {e}",
        )

    device.name = request.name
    await db.flush()
    await db.refresh(device)
    return device


@router.delete(
    "/{device_id}",
    response_model=ActionResponse,
    summary="Cihaz kaydını sil",
)
async def delete_device(device_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cihaz bulunamadı (id={device_id})",
        )

    await db.delete(device)
    return ActionResponse(
        success=True,
        message=f"'{device.name}' cihazı silindi.",
    )
