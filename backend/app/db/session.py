from collections.abc import AsyncIterator

from sqlalchemy import URL, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password,
    host=settings.postgres_host,
    port=settings.postgres_port,
    database=settings.postgres_db,
)

engine: AsyncEngine = create_async_engine(
    database_url,
    pool_pre_ping=True,
)

session_factory = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


async def get_database_session() -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


async def check_database_connection() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
