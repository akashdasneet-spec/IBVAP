"""
Database Session Management for Central Gateway.
Supports SQLite (aiosqlite) in development/test and PostgreSQL (asyncpg) in production.
"""

import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from db.models import Base

# Database URL resolution
DEFAULT_DB_URL = "sqlite+aiosqlite:///./ibvap_gateway.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DB_URL)

# Fallback from postgres to sqlite if asyncpg driver is not available locally
if DATABASE_URL.startswith("postgresql") and not os.getenv("FORCE_POSTGRES"):
    try:
        import asyncpg
    except ImportError:
        DATABASE_URL = DEFAULT_DB_URL

# Create Async Engine
is_sqlite = DATABASE_URL.startswith("sqlite")
engine_kwargs = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True

engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, **engine_kwargs)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def init_db() -> None:
    """Creates database tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency provider for FastAPI routes."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
