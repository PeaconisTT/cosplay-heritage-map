import io
import logging
from typing import Tuple
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)


class ImageSanitizationError(Exception):
    """Ngoại lệ tùy chỉnh khi xử lý hoặc làm sạch ảnh thất bại."""
    pass


def sanitize_and_convert_to_webp(
    image_bytes: bytes,
    quality: int = 85,
    max_dimension: int | None = 2560
) -> Tuple[bytes, int, int]:
    """
    Loại bỏ 100% thông tin EXIF, GPS metadata, Camera serial number và nén ảnh về WebP.
    """
    if not image_bytes:
        raise ImageSanitizationError("Dữ liệu ảnh đầu vào rỗng (empty bytes).")

    try:
        input_stream = io.BytesIO(image_bytes)
        
        with Image.open(input_stream) as img:
            # 1. Tự động xoay ảnh theo EXIF Orientation trước khi xóa thông tin này
            try:
                img = ImageOps.exif_transpose(img)
            except Exception as e:
                logger.warning(f"Khai thác EXIF orientation thất bại, tiếp tục xử lý: {e}")

            # 2. Chuẩn hóa Color Mode
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                target_mode = "RGBA"
            else:
                target_mode = "RGB"

            if img.mode != target_mode:
                img = img.convert(target_mode)

            # 3. Downscale kích thước nếu vượt quá max_dimension
            width, height = img.size
            if max_dimension and (width > max_dimension or height > max_dimension):
                img.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
                width, height = img.size

            # 4. Tách sạch Metadata bằng cách tạo ảnh mới từ Pixel Bytes thô
            clean_img = Image.frombytes(target_mode, (width, height), img.tobytes())

            # 5. Xuất ra byte stream định dạng WebP
            output_stream = io.BytesIO()
            clean_img.save(
                output_stream,
                format="WEBP",
                quality=quality,
                method=6,
                exact=True if target_mode == "RGBA" else False
            )

            sanitized_bytes = output_stream.getvalue()
            logger.info(
                f"Làm sạch ảnh thành công. Kích thước WebP: {len(sanitized_bytes)} bytes ({width}x{height}px)"
            )
            return sanitized_bytes, width, height

    except UnidentifiedImageError:
        raise ImageSanitizationError("Định dạng file không được hỗ trợ hoặc file ảnh bị hỏng.")
    except Exception as e:
        logger.error(f"Lỗi không xác định khi làm sạch ảnh: {str(e)}")
        raise ImageSanitizationError(f"Không thể xử lý và làm sạch ảnh: {str(e)}")