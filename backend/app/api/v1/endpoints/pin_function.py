import base64
import hashlib
import io
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from geoalchemy2.elements import WKTElement
import imagehash
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.pin import CosplayPin
from app.schemas.pin import PinResponse, WorkCategoryEnum
from app.services.image_sanitizer import ImageSanitizationError, sanitize_and_convert_to_webp
from app.services.pixel_hasher import PixelHasherError, generate_pixel_pin_id
from app.services.spatial_cluster import get_spatial_clusters

router = APIRouter()

UPLOAD_DIR = os.path.join("static", "uploads")
PLACEHOLDER_DIR = os.path.join("static", "placeholders")
SIGNATURE_DIR = os.path.join("static", "signatures")
DEFAULT_PLACEHOLDER_FILENAME = "default-artistic-pin.svg"
DEFAULT_PLACEHOLDER_URL = f"/static/placeholders/{DEFAULT_PLACEHOLDER_FILENAME}"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(PLACEHOLDER_DIR, exist_ok=True)
os.makedirs(SIGNATURE_DIR, exist_ok=True)


def ensure_artistic_placeholder() -> None:
    """Tạo sẵn tệp SVG Placeholder nghệ thuật mặc định nếu chưa tồn tại."""
    placeholder_path = os.path.join(PLACEHOLDER_DIR, DEFAULT_PLACEHOLDER_FILENAME)
    if os.path.exists(placeholder_path):
        return

    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400" width="600" height="400">
  <defs>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="50%" stop-color="#1e1b4b"/>
      <stop offset="100%" stop-color="#31102f"/>
    </linearGradient>
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fde68a"/>
      <stop offset="50%" stop-color="#f59e0b"/>
      <stop offset="100%" stop-color="#ff4757"/>
    </linearGradient>
  </defs>
  <rect width="600" height="400" fill="url(#bgGrad)"/>
  <circle cx="300" cy="200" r="135" fill="none" stroke="url(#goldGrad)" stroke-width="1.5" stroke-dasharray="6 6" opacity="0.65"/>
  <circle cx="300" cy="200" r="105" fill="none" stroke="#94a3b8" stroke-width="0.8" opacity="0.35"/>
  <polygon points="300,75 312,188 425,200 312,212 300,325 288,212 175,200 288,188" fill="url(#goldGrad)" opacity="0.85"/>
  <circle cx="300" cy="200" r="14" fill="#0f172a" stroke="url(#goldGrad)" stroke-width="3"/>
  <circle cx="140" cy="95" r="2.5" fill="#fde68a" opacity="0.8"/>
  <circle cx="470" cy="110" r="3" fill="#ff4757" opacity="0.8"/>
  <circle cx="450" cy="305" r="2" fill="#fde68a" opacity="0.7"/>
  <circle cx="155" cy="295" r="2.5" fill="#38bdf8" opacity="0.7"/>
  <text x="300" y="365" text-anchor="middle" fill="#cbd5e1" font-family="sans-serif" font-size="13" letter-spacing="4" opacity="0.85">COSPLAY HERITAGE ARCHIVE</text>
</svg>"""
    with open(placeholder_path, "w", encoding="utf-8") as f:
        f.write(svg_content)


def calculate_perceptual_hash(image_bytes: bytes) -> str:
    """Tính mã băm pHash (Perceptual Hash) 64-bit từ byte ảnh WebP."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return str(imagehash.phash(img))


@router.post(
    "/upload",
    response_model=PinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload tác phẩm & Khởi tạo Pin trên Bản đồ"
)
async def upload_cosplay_pin(
    file: Union[UploadFile, str, None] = File(default=None, description="File ảnh tác phẩm (Tùy chọn)"),
    signature_canvas: str = Form(..., description="Chuỗi Base64 nét vẽ chữ ký tay từ Canvas"),
    cosplayer_id: uuid.UUID = Form(..., description="UUID tài khoản Cosplayer"),
    cosplayer_name: str = Form(..., description="Nghệ danh Cosplayer"),
    photographer_id: Optional[uuid.UUID] = Form(None, description="UUID Photographer (nếu có)"),
    photographer_name: Optional[str] = Form(None, description="Nghệ danh Photographer"),
    character_name: str = Form(..., description="Tên nhân vật cosplay"),
    work_title: str = Form(..., description="Tên bộ truyện/game/anime"),
    work_category: WorkCategoryEnum = Form(WorkCategoryEnum.MANGA, description="Phân loại tác phẩm"),
    message: Optional[str] = Form(None, description="Lời nhắn kỷ niệm"),
    coord_x: float = Form(..., description="Tọa độ X trên mặt phẳng 2D"),
    coord_y: float = Form(..., description="Tọa độ Y trên mặt phẳng 2D"),
    event_id: Optional[uuid.UUID] = Form(None, description="ID sự kiện Fest"),
    event_name: Optional[str] = Form(None, description="Tên sự kiện Fest"),
    event_year: Optional[int] = Form(None, description="Năm diễn ra sự kiện"),
    db: AsyncSession = Depends(get_db)
):
    try:
        ensure_artistic_placeholder()

        # 1. Xử lý chữ ký tay Canvas (Bắt buộc để tạo mã định danh Pixel Pin ID & C2PA)
        current_time_iso = datetime.now(timezone.utc).isoformat()
        pixel_pin_id = generate_pixel_pin_id(
            signature_input=signature_canvas,
            cosplayer_id=str(cosplayer_id),
            timestamp_str=current_time_iso
        )

        # 2. Kiểm tra xem người dùng có tải ảnh tác phẩm lên hay không
        has_real_image = isinstance(file, UploadFile) and bool(file.filename)

        if has_real_image:
            if not file.content_type or not file.content_type.startswith("image/"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tập tin tải lên không phải là định dạng hình ảnh hợp lệ."
                )

            raw_image_bytes = await file.read()
            webp_bytes, width, height = sanitize_and_convert_to_webp(
                raw_image_bytes, quality=85, max_dimension=2560
            )

            media_hash_sha256 = hashlib.sha256(webp_bytes).hexdigest()

            # Kiểm tra trùng lặp ảnh tuyệt đối
            existing_pin = await db.execute(
                select(CosplayPin).where(CosplayPin.media_hash_sha256 == media_hash_sha256)
            )
            if existing_pin.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Tác phẩm này đã được đăng tải lên hệ thống trước đó."
                )

            perceptual_hash_str = calculate_perceptual_hash(webp_bytes)

            filename = f"{media_hash_sha256}.webp"
            file_path = os.path.join(UPLOAD_DIR, filename)
            with open(file_path, "wb") as f:
                f.write(webp_bytes)

            media_url = f"/static/uploads/{filename}"
            dimensions_meta = {"width": width, "height": height}
        else:
            # Không tải ảnh: Sử dụng Placeholder nghệ thuật mặc định (không dùng chữ ký làm ảnh)
            media_url = DEFAULT_PLACEHOLDER_URL
            media_hash_sha256 = hashlib.sha256(f"placeholder:{pixel_pin_id}".encode()).hexdigest()
            perceptual_hash_str = "0000000000000000"
            dimensions_meta = {"width": 600, "height": 400, "is_placeholder": True}

        # 3. Khởi tạo đối tượng PostGIS Geometry Point (SRID=0 Cartesian 2D)
        geometry_point = WKTElement(f"POINT({coord_x} {coord_y})", srid=0)

        # Lưu file ảnh chữ ký tay PNG
        try:
            signature_clean = signature_canvas
            if "," in signature_clean:
                signature_clean = signature_clean.split(",", 1)[1]
            sig_bytes = base64.b64decode(signature_clean)
            sig_filename = f"{pixel_pin_id}.png"
            sig_path = os.path.join(SIGNATURE_DIR, sig_filename)
            with open(sig_path, "wb") as f:
                f.write(sig_bytes)
            signature_url = f"/static/signatures/{sig_filename}"
        except Exception:
            signature_url = None

        digital_signature_manifest = {
            "c2pa_version": "1.3",
            "pixel_pin_id": pixel_pin_id,
            "signature_url": signature_url,
            "signature_canvas_hash": hashlib.sha256(signature_canvas.encode()).hexdigest(),
            "cosplayer_id": str(cosplayer_id),
            "timestamp": current_time_iso,
            "has_custom_photo": has_real_image,
            "sanitized_dimensions": dimensions_meta
        }

        new_pin = CosplayPin(
            cosplayer_id=cosplayer_id,
            cosplayer_name=cosplayer_name.strip(),
            photographer_id=photographer_id,
            photographer_name=photographer_name.strip() if photographer_name else None,
            character_name=character_name.strip(),
            work_title=work_title.strip(),
            work_category=work_category.value,
            message=message.strip() if message else None,
            media_url=media_url,
            media_hash_sha256=media_hash_sha256,
            perceptual_hash=perceptual_hash_str,
            event_id=event_id,
            event_name=event_name.strip() if event_name else None,
            event_year=event_year,
            alias_first_letter=cosplayer_name.strip()[0].upper(),
            virtual_coord=geometry_point,
            digital_signature=digital_signature_manifest,
            is_verified=True if photographer_id else False,
            moderation_status="APPROVED"
        )

        db.add(new_pin)
        await db.commit()
        await db.refresh(new_pin)

        return new_pin

    except HTTPException:
        raise
    except ImageSanitizationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Lỗi làm sạch hình ảnh: {str(e)}"
        )
    except PixelHasherError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Lỗi xử lý chữ ký tay Canvas: {str(e)}"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi hệ thống khi khởi tạo Pin: {str(e)}"
        )


@router.get(
    "/clusters",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách Cụm tròn và Điểm Pin đơn lẻ trên bản đồ"
)
async def list_pin_clusters(
    eps: float = Query(80.0, description="Bán kính phân cụm (đơn vị pixel 2D)"),
    min_points: int = Query(2, description="Số lượng điểm tối thiểu để cấu thành Cụm tròn"),
    event_id: Optional[uuid.UUID] = Query(None, description="Lọc theo ID sự kiện"),
    event_name: Optional[str] = Query(None, description="Lọc theo tên sự kiện Fest"),
    work_title: Optional[str] = Query(None, description="Lọc theo tên tác phẩm nguyên tác"),
    alias_first_letter: Optional[str] = Query(None, description="Lọc theo chữ cái đầu nghệ danh"),
    db: AsyncSession = Depends(get_db)
):
    """
    Truy vấn các Cụm tròn (Cluster) và Điểm đơn lẻ (Single Pin)
    sử dụng thuật toán phân cụm không gian PostGIS ST_ClusterDBSCAN.
    """
    try:
        clusters = await get_spatial_clusters(
            db=db,
            eps=eps,
            min_points=min_points,
            event_id=event_id,
            event_name=event_name,
            work_title=work_title,
            alias_first_letter=alias_first_letter
        )
        return clusters
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi truy vấn dữ liệu cụm bản đồ: {str(e)}"
        )


@router.get(
    "/filters",
    response_model=Dict[str, List[str]],
    status_code=status.HTTP_200_OK,
    summary="Lấy danh sách các giá trị bộ lọc thực tế trong CSDL (Events, Works, Letters)"
)
async def get_filter_options(db: AsyncSession = Depends(get_db)):
    """
    Truy vấn danh sách giá trị phân loại thực tế từ các Pin đã duyệt (APPROVED):
    - events: danh sách event_name duy nhất (khác null/rỗng, sắp xếp A-Z)
    - works: danh sách work_title duy nhất (sắp xếp A-Z)
    - letters: danh sách alias_first_letter duy nhất (sắp xếp A-Z)
    """
    try:
        events_query = select(CosplayPin.event_name).where(
            CosplayPin.moderation_status == "APPROVED",
            CosplayPin.event_name.is_not(None),
            CosplayPin.event_name != ""
        ).distinct().order_by(CosplayPin.event_name)
        events_res = await db.execute(events_query)
        events = [r[0] for r in events_res.all() if r[0]]

        works_query = select(CosplayPin.work_title).where(
            CosplayPin.moderation_status == "APPROVED",
            CosplayPin.work_title.is_not(None),
            CosplayPin.work_title != ""
        ).distinct().order_by(CosplayPin.work_title)
        works_res = await db.execute(works_query)
        works = [r[0] for r in works_res.all() if r[0]]

        letters_query = select(CosplayPin.alias_first_letter).where(
            CosplayPin.moderation_status == "APPROVED",
            CosplayPin.alias_first_letter.is_not(None),
            CosplayPin.alias_first_letter != ""
        ).distinct().order_by(CosplayPin.alias_first_letter)
        letters_res = await db.execute(letters_query)
        letters = [r[0] for r in letters_res.all() if r[0]]

        return {
            "events": events,
            "works": works,
            "letters": letters
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Lỗi truy vấn danh mục bộ lọc: {str(e)}"
        )