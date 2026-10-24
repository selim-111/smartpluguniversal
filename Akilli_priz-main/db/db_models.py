"""
SQLAlchemy ORM models for the database tables.
"""

from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from db.database import Base


class Device(Base):
    """
    Kayıtlı akıllı priz cihazı.

    Columns:
        id          — Otomatik artan birincil anahtar
        mac_address — Cihazın benzersiz MAC adresi
        name        — Kullanıcının verdiği isim
        ip_address  — Cihazın yerel ağdaki IP adresi
        created_at  — İlk kayıt tarihi
        updated_at  — Son güncelleme tarihi
    """

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mac_address: Mapped[str] = mapped_column(String(17), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    driver: Mapped[str] = mapped_column(String(10), nullable=False, default="kasa")
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"Device(id={self.id}, name='{self.name}', mac='{self.mac_address}', ip='{self.ip_address}', driver='{self.driver}')"
