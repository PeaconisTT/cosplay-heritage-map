import uuid
from datetime import datetime as DateTimeValue
from typing import Optional, Dict, Any

from sqlalchemy import String, Text, Boolean, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from geoalchemy2 import Geometry


class Base(DeclarativeBase):
    """Base ORM Class cho toàn bộ hệ thống FastAPI."""
    pass


class CosplayPin(Base):
    __tablename__ = "cosplay_pins"

    # 1. Định danh duy nhất cho Chấm tròn (Pin)
    pin_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="Mã định danh duy nhất của Pin (UUID v4)"
    )

    # 2. Định danh Cosplayer & Photographer
    cosplayer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        index=True,
        nullable=False,
        comment="ID tài khoản Cosplayer"
    )
    cosplayer_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Nghệ danh Cosplayer tại thời điểm đăng tác phẩm"
    )
    photographer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID tài khoản Photographer (nếu có co-sign xác thực)"
    )
    photographer_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Nghệ danh Photographer chụp tác phẩm"
    )

    # 3. Thông tin Tác phẩm & Nội dung Media
    character_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        index=True,
        comment="Tên nhân vật cosplay (vd: Makima, Frieren)"
    )
    work_title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
        comment="Tên bộ truyện/game/anime (vd: Chainsaw Man, Genshin Impact)"
    )
    work_category: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MANGA",
        comment="Phân loại: MANGA, ANIME, GAME, NOVEL, OC"
    )
    message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Lời nhắn kỷ niệm hoặc thông điệp cá nhân"
    )
    media_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Đường dẫn CDN chứa ảnh WebP đã loại bỏ EXIF/GPS"
    )

    # 4. Hash Bảo mật & Chống nạp trùng ảnh
    media_hash_sha256: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="Mã băm cryptographic SHA-256 của tập tin ảnh sạch"
    )
    perceptual_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Mã băm pHash dạng chuỗi nhị phân/hex để nhận diện ảnh trùng"
    )

    # 5. Phục vụ 3 loại Bản đồ Ảo (Event, IP, Cosplayer A-Z)
    event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="ID sự kiện Fest/Convention (Map Sự kiện)"
    )
    event_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
        comment="Tên sự kiện Fest (vd: Color Fiesta S16, Hobby Horizon)"
    )
    event_year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="Năm diễn ra sự kiện"
    )
    alias_first_letter: Mapped[str] = mapped_column(
        String(1),
        nullable=False,
        index=True,
        comment="Ký tự đầu tiên của nghệ danh (A-Z) phục vụ Map Nghệ danh"
    )

    # 6. Tọa độ phẳng 2D không-địa-lý (Flat Cartesian Geometry SRID=0)
    virtual_coord: Mapped[Any] = mapped_column(
        Geometry(geometry_type="POINT", srid=0, spatial_index=True),
        nullable=False,
        comment="Tọa độ 2D (X, Y) trên mặt phẳng Leaflet L.CRS.Simple"
    )

    # 7. Chứng thực Ký số C2PA & Trạng thái Kiểm duyệt
    digital_signature: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Lưu trữ chữ ký số Ed25519, Stroke Vector chữ ký tay và RFC3161 Timestamp"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Trạng thái Chấm Vàng đã xác thực ký kép"
    )
    moderation_status: Mapped[str] = mapped_column(
        String(20),
        default="APPROVED",
        nullable=False,
        comment="Trạng thái kiểm duyệt: PENDING, APPROVED, REJECTED"
    )

    # 8. Mốc thời gian
    datetime: Mapped[DateTimeValue] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
        comment="Thời điểm khởi tạo Pin trên bản đồ"
    )

    def __repr__(self) -> str:
        return f"<CosplayPin(pin_id={self.pin_id}, cosplayer='{self.cosplayer_name}', character='{self.character_name}')>"