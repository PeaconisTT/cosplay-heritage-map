from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==========================================
# 1. ENUMS (Danh mục chuẩn hóa)
# ==========================================

class WorkCategoryEnum(str, Enum):
    """Phân loại tác phẩm nguyên tác."""
    MANGA = "MANGA"
    ANIME = "ANIME"
    GAME = "GAME"
    NOVEL = "NOVEL"
    OC = "OC"


class ModerationStatusEnum(str, Enum):
    """Trạng thái kiểm duyệt Pin."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# ==========================================
# 2. SUB-SCHEMAS (Cấu trúc con bổ trợ)
# ==========================================

class VirtualCoordinate(BaseModel):
    """Tọa độ phẳng 2D (X, Y) sử dụng cho Leaflet L.CRS.Simple."""
    x: float = Field(..., description="Tọa độ ngang trên mặt phẳng 2D")
    y: float = Field(..., description="Tọa độ dọc trên mặt phẳng 2D")

    model_config = ConfigDict(from_attributes=True)


class StrokePoint(BaseModel):
    """Tọa độ điểm vẽ nét chữ ký tay trên Canvas."""
    x: float
    y: float
    time: Optional[float] = None


class DigitalSignaturePayload(BaseModel):
    """Cấu trúc dữ liệu Chữ ký số & Chứng nhận Provenance C2PA."""
    pixel_hash: str = Field(..., description="Mã băm SHA-256 từ ma trận pixel chữ ký tay")
    stroke_vectors: Optional[List[List[StrokePoint]]] = Field(
        None, description="Danh sách các đường nét vẽ vector dạng stroke path"
    )
    cosplayer_signature_hex: Optional[str] = Field(
        None, description="Chữ ký mã hóa Ed25519 của Cosplayer"
    )
    photographer_signature_hex: Optional[str] = Field(
        None, description="Chữ ký mã hóa Ed25519 của Nhiếp ảnh gia (Co-sign)"
    )
    public_key_hex: Optional[str] = Field(None, description="Public Key dùng để xác thực chữ ký")
    rfc3161_timestamp: Optional[str] = Field(
        None, description="Con dấu thời gian xác thực từ TSA Server"
    )

    model_config = ConfigDict(from_attributes=True)


# ==========================================
# 3. PIN SCHEMAS (Request & Response)
# ==========================================

class PinBase(BaseModel):
    """Cấu hình thuộc tính nền tảng của một Pin."""
    cosplayer_name: str = Field(..., min_length=1, max_length=100, description="Nghệ danh Cosplayer")
    photographer_name: Optional[str] = Field(None, max_length=100, description="Nghệ danh Photographer")
    character_name: str = Field(..., min_length=1, max_length=150, description="Tên nhân vật cosplay")
    work_title: str = Field(..., min_length=1, max_length=200, description="Tên bộ truyện/game/anime")
    work_category: WorkCategoryEnum = Field(WorkCategoryEnum.MANGA, description="Phân loại tác phẩm")
    message: Optional[str] = Field(None, max_length=500, description="Lời nhắn kỷ niệm")
    event_id: Optional[UUID] = Field(None, description="ID sự kiện Fest (nếu có)")
    event_name: Optional[str] = Field(None, max_length=150, description="Tên sự kiện Fest")
    event_year: Optional[int] = Field(None, ge=2000, le=2100, description="Năm diễn ra sự kiện")


class PinCreate(PinBase):
    """Schema yêu cầu khi Cosplayer khởi tạo Pin mới."""
    cosplayer_id: UUID = Field(..., description="ID tài khoản Cosplayer")
    photographer_id: Optional[UUID] = Field(None, description="ID tài khoản Photographer")
    virtual_coord: VirtualCoordinate = Field(..., description="Tọa độ 2D (X, Y) đặt Pin")
    digital_signature: DigitalSignaturePayload = Field(..., description="Dữ liệu chữ ký số và nét vẽ")
    signature_canvas_base64: Optional[str] = Field(
        None, description="Chuỗi ảnh nét vẽ Base64 từ HTML5 Canvas để tạo pin_id"
    )


class PinUpdate(BaseModel):
    """Schema cho phép cập nhật thông tin Pin."""
    message: Optional[str] = Field(None, max_length=500)
    moderation_status: Optional[ModerationStatusEnum] = None
    is_verified: Optional[bool] = None


class PinResponse(PinBase):
    """Schema chuẩn đầu ra API trả về cho Client."""
    pin_id: UUID
    cosplayer_id: UUID
    photographer_id: Optional[UUID] = None
    media_url: str = Field(..., description="Đường dẫn CDN ảnh WebP đã xóa EXIF/GPS")
    media_hash_sha256: str
    perceptual_hash: str
    alias_first_letter: str
    virtual_coord: VirtualCoordinate
    digital_signature: Dict[str, Any]
    is_verified: bool
    moderation_status: ModerationStatusEnum
    datetime: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("virtual_coord", mode="before")
    @classmethod
    def parse_postgis_geometry(cls, value: Any) -> Union[VirtualCoordinate, Dict[str, float]]:
        """
        Tự động chuyển đổi dữ liệu WKBElement từ PostGIS Geometry(Point, 0)
        thành đối tượng VirtualCoordinate (x, y) cho Frontend Leaflet.
        """
        if isinstance(value, WKBElement):
            point = to_shape(value)
            return VirtualCoordinate(x=point.x, y=point.y)
        if isinstance(value, dict) and "x" in value and "y" in value:
            return value
        return value


class PinClusterItem(BaseModel):
    """Schema rút gọn phục vụ Render Phân cụm 2D trên Leaflet Map."""
    pin_id: UUID
    cosplayer_name: str
    character_name: str
    work_title: str
    media_url: str
    virtual_coord: VirtualCoordinate
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)

    @field_validator("virtual_coord", mode="before")
    @classmethod
    def parse_postgis_geometry(cls, value: Any) -> VirtualCoordinate:
        if isinstance(value, WKBElement):
            point = to_shape(value)
            return VirtualCoordinate(x=point.x, y=point.y)
        return value