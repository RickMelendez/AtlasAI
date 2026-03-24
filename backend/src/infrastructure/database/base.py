"""
Configuración base de la base de datos para Atlas AI.

Inicializa el engine asíncrono de SQLAlchemy, la SessionFactory,
y la clase base declarativa para todos los modelos ORM.
"""

import logging
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase

from src.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# ─── Engine asíncrono ────────────────────────────────────────────────────────

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Loguea SQL en modo debug
    connect_args={"check_same_thread": False},  # Requerido para SQLite
)

# ─── Session factory ─────────────────────────────────────────────────────────

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Permite acceder a objetos después del commit
    autocommit=False,
    autoflush=False,
)


# ─── Base declarativa ────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    """Clase base para todos los modelos ORM de Atlas AI."""

    pass


# ─── Helpers de sesión ───────────────────────────────────────────────────────


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency injection para sesiones de base de datos.

    Uso en FastAPI:
        async def endpoint(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Inicialización de tablas ─────────────────────────────────────────────────


async def init_db() -> None:
    """
    Crea todas las tablas en la base de datos si no existen.

    Debe llamarse al iniciar la aplicación. Usa CREATE TABLE IF NOT EXISTS
    por lo que es seguro llamarla múltiples veces.
    """
    # Importar modelos para que SQLAlchemy los registre en Base.metadata
    from src.infrastructure.database import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("✅ Database tables initialized (SQLite: atlas.db)")
