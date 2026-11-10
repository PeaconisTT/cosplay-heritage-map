import io
import random
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from PIL import Image
from sqlalchemy import text

from app.main import app
from app.core.database import engine
from app.models.pin import Base


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Tự động làm sạch bảng dữ liệu trước khi thực thi testcase."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("TRUNCATE TABLE cosplay_pins RESTART IDENTITY CASCADE;"))
    yield
    await engine.dispose()


def create_test_image_bytes() -> bytes:
    """Tạo ảnh ngẫu nhiên màu sắc để sinh mã băm SHA-256 khác nhau giữa các lần test."""
    color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    img = Image.new("RGB", (300, 300), color=color)
    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def create_test_signature_base64() -> str:
    """Tạo chuỗi Base64 chữ ký tay giả lập ngẫu nhiên."""
    img = Image.new("RGBA", (200, 100), (255, 255, 255, 0))
    offset = random.randint(0, 30)
    for i in range(10 + offset, 50 + offset):
        img.putpixel((i, i), (0, 0, 0, 255))
    output = io.BytesIO()
    img.save(output, format="PNG")
    import base64
    return f"data:image/png;base64,{base64.b64encode(output.getvalue()).decode('utf-8')}"


@pytest.mark.asyncio
async def test_upload_cosplay_pin_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        image_bytes = create_test_image_bytes()
        signature_b64 = create_test_signature_base64()
        
        files = {
            "file": ("test_cosplay.png", image_bytes, "image/png")
        }
        data = {
            "cosplayer_id": str(uuid.uuid4()),
            "cosplayer_name": "Nguyễn Văn B",
            "character_name": "Makima",
            "work_title": "Chainsaw Man",
            "work_category": "MANGA",
            "signature_canvas": signature_b64,
            "coord_x": "150.5",
            "coord_y": "300.2",
            "message": "Kỷ niệm Color Fiesta S16"
        }

        response = await client.post("/api/v1/pins/upload", data=data, files=files)
        
        if response.status_code != 201:
            print("Response Error Detail:", response.json())

        assert response.status_code == 201
        res_json = response.json()
        assert res_json["cosplayer_name"] == "Nguyễn Văn B"
        assert res_json["character_name"] == "Makima"
        assert res_json["virtual_coord"]["x"] == 150.5
        assert res_json["virtual_coord"]["y"] == 300.2
        assert res_json["media_url"].startswith("/static/uploads/")