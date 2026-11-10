import uuid
import pytest
import pytest_asyncio
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.core.database import engine, AsyncSessionLocal
from app.models.pin import Base, CosplayPin
from app.services.spatial_cluster import get_spatial_clusters


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("TRUNCATE TABLE cosplay_pins RESTART IDENTITY CASCADE;"))
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_spatial_clustering_dbscan():
    async with AsyncSessionLocal() as db:
        # 1. Thêm 2 điểm nằm rất gần nhau (khoảng cách 10.0px < eps=50.0)
        pin1 = CosplayPin(
            cosplayer_id=uuid.uuid4(),
            cosplayer_name="Cosplayer A",
            character_name="Character A",
            work_title="Anime X",
            work_category="ANIME",
            media_url="/static/uploads/1.webp",
            media_hash_sha256="hash_1",
            perceptual_hash="phash_1",
            alias_first_letter="C",
            virtual_coord=WKTElement("POINT(100.0 100.0)", srid=0),
            digital_signature={},
            moderation_status="APPROVED"
        )
        pin2 = CosplayPin(
            cosplayer_id=uuid.uuid4(),
            cosplayer_name="Cosplayer B",
            character_name="Character B",
            work_title="Anime X",
            work_category="ANIME",
            media_url="/static/uploads/2.webp",
            media_hash_sha256="hash_2",
            perceptual_hash="phash_2",
            alias_first_letter="C",
            virtual_coord=WKTElement("POINT(110.0 100.0)", srid=0),
            digital_signature={},
            moderation_status="APPROVED"
        )

        # 2. Thêm 1 điểm nằm cách xa (khoảng cách 400.0px > eps=50.0)
        pin3 = CosplayPin(
            cosplayer_id=uuid.uuid4(),
            cosplayer_name="Cosplayer C",
            character_name="Character C",
            work_title="Anime Y",
            work_category="ANIME",
            media_url="/static/uploads/3.webp",
            media_hash_sha256="hash_3",
            perceptual_hash="phash_3",
            alias_first_letter="C",
            virtual_coord=WKTElement("POINT(500.0 500.0)", srid=0),
            digital_signature={},
            moderation_status="APPROVED"
        )

        db.add_all([pin1, pin2, pin3])
        await db.commit()

        # 3. Chạy hàm phân cụm với eps=50.0 và min_points=2
        results = await get_spatial_clusters(db, eps=50.0, min_points=2)

        # Phải trả về tổng cộng 2 phần tử (1 Cụm tròn gom pin1+pin2, và 1 Điểm đơn pin3)
        assert len(results) == 2

        cluster_items = [r for r in results if r["type"] == "cluster"]
        single_items = [r for r in results if r["type"] == "single"]

        assert len(cluster_items) == 1
        assert cluster_items[0]["count"] == 2
        # Tâm cụm trung bình của (100,100) và (110,100) là (105, 100)
        assert cluster_items[0]["center"]["x"] == 105.0

        assert len(single_items) == 1
        assert single_items[0]["count"] == 1
        assert single_items[0]["center"]["x"] == 500.0