import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from geoalchemy2.elements import WKTElement
from PIL import Image
import imagehash
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.database import get_db
from app.models.pin import CosplayPin
from app.schemas.pin import PinResponse, WorkCategoryEnum
from app.services.image_sanitizer import sanitize_and_convert_to_webp, ImageSanitizationError
from app.services.pixel_hasher import generate_pixel_pin_id, PixelHasherError

router = APIRouter()

# Thư mục lưu trữ hình ảnh WebP đã làm sạch
UPLOAD_DIR = os.path.join("static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def calculate_perceptual_hash(image_bytes: bytes) -> str:
    """Tính mã băm pHash (Perceptual Hash) 64-bit từ byte ảnh WebP."""
    import io
    with Image.open(io.BytesIO(image_bytes)) as img:
        phash_val = imagehash.phash(img)
        return str(phash_val)


@router.post(
    "/upload",
    response_model=PinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload tác phẩm & Khởi tạo Pin trên Bản đồ",
    description="Nhận ảnh tác phẩm và chữ ký tay, xóa 100% EXIF/GPS, nén WebP, băm SHA-256 & pHash và lưu tọa độ 2D vào PostGIS."
)
async def upload_cosplay_pin(
    # 1. File ảnh tác phẩm
    file: UploadFile = File(..., description="File ảnh tác phẩm cosplay gốc"),
    
    # 2. Chữ ký tay Canvas & Thông tin Định danh
    signature_canvas: str = Form(..., description="Chuỗi Base64 nét vẽ chữ ký tay từ Canvas"),
    cosplayer_id: uuid.UUID = Form(..., description="UUID tài khoản Cosplayer"),
    cosplayer_name: str = Form(..., description="Nghệ danh Cosplayer"),
    photographer_id: Optional[uuid.UUID] = Form(None, description="UUID Photographer (nếu có)"),
    photographer_name: Optional[str] = Form(None, description="Nghệ danh Photographer"),
    
    # 3. Thông tin Tác phẩm
    character_name: str = Form(..., description="Tên nhân vật cosplay"),
    work_title: str = Form(..., description="Tên bộ truyện/game/anime"),
    work_category: WorkCategoryEnum = Form(WorkCategoryEnum.MANGA, description="Phân loại tác phẩm"),
    message: Optional[str] = Form(None, description="Lời nhắn kỷ niệm"),
    
    # 4. Tọa độ phẳng 2D (Leaflet L.CRS.Simple)
    coord_x: float = Form(..., description="Tọa độ X trên mặt phẳng 2D"),
    coord_y: float = Form(..., description="Tọa độ Y trên mặt phẳng 2D"),
    
    # 5. Thông tin Sự kiện (Tùy chọn cho Map Sự kiện)
    event_id: Optional[uuid.UUID] = Form(None, description="ID sự kiện Fest"),
    event_name: Optional[str] = Form(None, description="Tên sự kiện Fest"),
    event_year: Optional[int] = Form(None, description="Năm diễn ra sự kiện"),
    
    # Context Session CSDL
    db: AsyncSession = Depends(get_db)
):
    # A. Validate định dạng file đầu vào
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tập tin tải lên không phải là định dạng hình ảnh hợp lệ."
        )

    try:
        raw_image_bytes = await file.read()
        
        # B. Loại bỏ 100% EXIF/GPS metadata và nén sang WebP
        webp_bytes, width, height = sanitize_and_convert_to_webp(
            raw_image_bytes, quality=85, max_dimension=2560
        )
        
        # C. Tính toán các chuỗi Hash chứng thực
        # 1. SHA-256 Media Hash
        media_hash_sha256 = hashlib.sha256(webp_bytes).hexdigest()
        
        # Kiểm tra trùng lặp ảnh tuyệt đối (Exact SHA-256 Duplicate)
        existing_pin = await db.execute(
            select(CosplayPin).where(CosplayPin.media_hash_sha256 == media_hash_sha256)
        )
        if existing_pin.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Tác phẩm này đã được đăng tải lên hệ thống trước đó."
            )
        
        # 2. pHash (Perceptual Hash) phục vụ quét trùng
        perceptual_hash_str = calculate_perceptual_hash(webp_bytes)
        
        # 3. Ký số Pixel Matrix từ nét vẽ chữ ký tay Canvas
        current_time_iso = datetime.now(timezone.utc).isoformat()
        pixel_pin_id = generate_pixel_pin_id(
            signature_input=signature_canvas,
            cosplayer_id=str(cosplayer_id),
            timestamp_str=current_time_iso
        )

        # D. Lưu file WebP đã làm sạch vào hệ thống lưu trữ/CDN
        filename = f"{media_hash_sha256}.webp"
        file_path = os.path.join(UPLOAD_DIR, filename)
        with open(file_path, "wb") as f:
            f.write(webp_bytes)
        
        media_url = f"/static/uploads/{filename}"

        # E. Khởi tạo đối tượng PostGIS Geometry Point (SRID=0 Cartesian 2D)
        geometry_point = WKTElement(f"POINT({coord_x} {coord_y})", srid=0)

        # F. Đóng gói Chữ ký số C2PA Manifest
        digital_signature_manifest = {
            "c2pa_version": "1.3",
            "pixel_pin_id": pixel_pin_id,
            "signature_canvas_hash": hashlib.sha256(signature_canvas.encode()).hexdigest(),
            "cosplayer_id": str(cosplayer_id),
            "timestamp": current_time_iso,
            "sanitized_dimensions": {"width": width, "height": height}
        }

        # G. Tạo record ORM CosplayPin
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