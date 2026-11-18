import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.main import app
from app.core.database import engine, AsyncSessionLocal
from app.models.pin import Base, CosplayPin


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Khởi tạo lại CSDL và làm sạch dữ liệu trước mỗi lần test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("TRUNCATE TABLE cosplay_pins RESTART IDENTITY CASCADE;"))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_pin_clusters_api_endpoint():
    # 1. Chèn dữ liệu mẫu vào CSDL
    async with AsyncSessionLocal() as db:
        pin1 = CosplayPin(
            cosplayer_id=uuid.uuid4(),
            cosplayer_name="Luận Nguyễn",
            character_name="Makima",
            work_title="Chainsaw Man",
            work_category="MANGA",
            media_url="/static/uploads/makima.webp",
            media_hash_sha256="hash_makima_01",
            perceptual_hash="phash_01",
            alias_first_letter="L",
            virtual_coord=WKTElement("POINT(200.0 200.0)", srid=0),
            digital_signature={},
            moderation_status="APPROVED"
        )
        pin2 = CosplayPin(
            cosplayer_id=uuid.uuid4(),
            cosplayer_name="Power Cosplayer",
            character_name="Power",
            work_title="Chainsaw Man",
            work_category="MANGA",
            media_url="/static/uploads/power.webp",
            media_hash_sha256="hash_power_02",
            perceptual_hash="phash_02",
            alias_first_letter="P",
            virtual_coord=WKTElement("POINT(220.0 200.0)", srid=0),
            digital_signature={},
            moderation_status="APPROVED"
        )
        db.add_all([pin1, pin2])
        await db.commit()

    # 2. Gọi API GET /api/v1/pins/clusters
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/pins/clusters?eps=50.0&min_points=2")
        
        assert response.status_code == 200
        res_json = response.json()
        
        # Kiểm tra phản hồi có chứa 1 Cụm tròn gồm 2 phần tử
        assert len(res_json) == 1
        cluster = res_json[0]
        assert cluster["type"] == "cluster"
        assert cluster["count"] == 2
        assert cluster["center"]["x"] == 210.0
        assert cluster["center"]["y"] == 200.0
        assert len(cluster["items"]) == 2