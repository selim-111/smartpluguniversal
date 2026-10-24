"""
Application configuration — loaded from environment variables / .env file.
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# .env dosyasını yükle (varsa)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)


class Settings(BaseSettings):
    """
    Uygulama ayarları.
    Değerler .env dosyasından veya ortam değişkenlerinden okunur.
    """

    # PostgreSQL bağlantı URL'si
    # URL henüz hazır değilse boş bırakın — DB gerektiren endpoint'ler hata verecektir.
    DATABASE_URL: str = ""

    # CORS — frontend origin'leri (virgülle ayrılmış)
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Cihaz TCP timeout
    DEVICE_TIMEOUT: float = 2.0

    @property
    def cors_origins_list(self) -> list[str]:
        """CORS_ORIGINS string'ini listeye çevir."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def has_database(self) -> bool:
        """Veritabanı URL'si tanımlı mı?"""
        return bool(self.DATABASE_URL) and self.DATABASE_URL != "postgresql+asyncpg://user:password@HOST:5432/akilli_priz"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
