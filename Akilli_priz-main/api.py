"""
TP-Link HS110 Akıllı Priz — REST API Gateway

Bu uygulama, senin PC'nde çalışır ve:
  1. Frontend'in HTTP ile erişebileceği endpoint'ler sunar
  2. Cihaza TCP/9999 ile bağlanarak komut gönderir
  3. PostgreSQL veritabanına cihaz bilgilerini kaydeder

Başlatma:
    uvicorn api:app --host 0.0.0.0 --port 8000 --reload

Swagger UI:
    http://localhost:8000/docs
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db.database import init_db, close_db
from routes import devices as device_routes
from routes import control as control_routes
from routes import wifi as wifi_routes
from routes import discovery as discovery_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama başlatma/kapatma yaşam döngüsü."""
    # Startup
    if settings.has_database:
        await init_db()
        print("✅ Veritabanı bağlantısı hazır.")
    else:
        print("⚠️  DATABASE_URL ayarlanmamış — DB gerektiren endpoint'ler çalışmaz.")
        print("   .env dosyasında DATABASE_URL değerini ayarlayın.")

    yield

    # Shutdown
    await close_db()
    print("🔌 Veritabanı bağlantısı kapatıldı.")


# ─────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────

app = FastAPI(
    title="🔌 Akıllı Priz API",
    description=(
        "TP-Link akıllı cihazları (Kasa + Tapo) REST API üzerinden kontrol etmek için gateway uygulaması.\n\n"
        "**Desteklenen Protokoller:**\n"
        "- **Kasa** — HS100, HS110, HS200, HS300, KP105, KP115 (TCP/9999, şifresiz)\n"
        "- **Tapo** — P100, P105, P110, L510, L530 (HTTP/80, kullanıcı adı + şifre)\n\n"
        "**Mimari:** Frontend → Bu API (senin PC) → Cihaz\n\n"
        "**Veritabanı:** PostgreSQL — cihaz bilgileri ve credential'ları saklar."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ─────────────────────────────────────────────
# CORS Middleware — Frontend erişimi
# ─────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Routers
# ─────────────────────────────────────────────

app.include_router(discovery_routes.router)   # ← discover önce! yoksa {device_id} yakalar
app.include_router(device_routes.router)
app.include_router(control_routes.router)
app.include_router(wifi_routes.router)


# ─────────────────────────────────────────────
# Health Check
# ─────────────────────────────────────────────

@app.get(
    "/",
    tags=["Genel"],
    summary="Sağlık kontrolü",
    response_model=dict,
)
async def health_check():
    """API'nin çalışıp çalışmadığını kontrol eder."""
    return {
        "status": "ok",
        "service": "Akıllı Priz API",
        "database_configured": settings.has_database,
    }
