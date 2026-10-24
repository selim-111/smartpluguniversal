"""
Database connection layer — SQLAlchemy async engine + session.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from config import settings

# ─────────────────────────────────────────────
# Base class for all ORM models
# ─────────────────────────────────────────────

class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""
    pass


# ─────────────────────────────────────────────
# Engine & Session Factory
# ─────────────────────────────────────────────

engine = None
async_session_factory = None


def _init_engine():
    """Initialize the engine and session factory (lazy)."""
    global engine, async_session_factory

    if not settings.has_database:
        return

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def init_db():
    """
    Create all tables defined in ORM models.
    Call this once at application startup.
    """
    _init_engine()

    if engine is None:
        return

    # Import models so they register with Base.metadata
    import db.db_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Dispose engine connections on shutdown."""
    global engine
    if engine:
        await engine.dispose()


async def get_db() -> AsyncSession:
    """
    FastAPI dependency — yields a database session.
    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    if async_session_factory is None:
        raise RuntimeError(
            "Veritabanı bağlantısı yapılandırılmamış. "
            ".env dosyasında DATABASE_URL ayarlayın."
        )

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
