import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import engine, AsyncSessionLocal, get_db


@pytest_asyncio.fixture(autouse=True)
async def cleanup_engine():
    """
    Tự động giải phóng connection pool của engine sau mỗi testcase.
    Ngăn ngừa lỗi 'Event loop is closed' khi asyncpg dùng lại kết nối cũ trên Windows.
    """
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_postgres_async_connection():
    """Kiểm thử kết nối trực tiếp từ Async Engine tới PostgreSQL."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1;"))
        scalar_value = result.scalar()
        assert scalar_value == 1


@pytest.mark.asyncio
async def test_async_session_lifecycle():
    """Kiểm thử vòng đời thủ công của AsyncSessionLocal."""
    async with AsyncSessionLocal() as session:
        assert isinstance(session, AsyncSession)
        assert session.is_active is True

        result = await session.execute(text("SELECT 'cosplay_heritage_map' AS test_name;"))
        row = result.fetchone()
        assert row is not None
        assert row.test_name == "cosplay_heritage_map"

    assert session.in_transaction() is False
    assert session.get_transaction() is None


@pytest.mark.asyncio
async def test_get_db_dependency_generator():
    """Kiểm thử vòng đời Dependency get_db() dùng cho FastAPI Endpoints."""
    db_generator = get_db()
    
    session = await anext(db_generator)
    assert isinstance(session, AsyncSession)
    assert session.is_active is True

    result = await session.execute(text("SELECT 10 + 20 AS result;"))
    assert result.scalar() == 30

    with pytest.raises(StopAsyncIteration):
        await anext(db_generator)