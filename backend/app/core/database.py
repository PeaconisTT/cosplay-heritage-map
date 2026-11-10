import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# URL kết nối PostgreSQL sử dụng asyncpg driver
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://cosplay_admin:cosplay_secure_password_2026@localhost:5432/cosplay_map_db"
)

# Khởi tạo Async Engine cho PostgreSQL
engine = create_async_engine(
    DATABASE_URL,
    echo=False,           # Đổi thành True nếu muốn log chi tiết các câu lệnh SQL
    future=True,
    pool_pre_ping=True,   # Tự động kiểm tra kết nối sống trước khi thực thi query
    pool_size=10,         # Số lượng kết nối cố định duy trì trong Connection Pool
    max_overflow=20       # Số kết nối mở rộng tối đa khi quá tải
)

# Khởi tạo Async Session Factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Tránh tự động expire object sau khi commit trong async
    autoflush=False
)


class Base(DeclarativeBase):
    """Lớp nền tảng (Declarative Base) cho các ORM Models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency: Cấp phát AsyncSession cho từng HTTP Request.
    Tự động quản lý commit/rollback và đóng kết nối an toàn.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()