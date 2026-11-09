import base64
import hashlib
import io
import logging
from typing import Tuple
from PIL import Image, UnidentifiedImageError

logger = logging.getLogger(__name__)


class PixelHasherError(Exception):
    """Ngoại lệ tùy chỉnh khi xử lý ma trận pixel chữ ký thất bại."""
    pass


def _decode_signature_input(signature_input: bytes | str) -> bytes:
    """Giải mã chuỗi Base64 hoặc trả về byte nhị phân trực tiếp."""
    if isinstance(signature_input, str):
        # Trích xuất dữ liệu Base64 nếu có tiền tố Data URL (ví dụ: data:image/png;base64,...)
        if "," in signature_input:
            signature_input = signature_input.split(",", 1)[1]
        try:
            return base64.b64decode(signature_input)
        except Exception as e:
            raise PixelHasherError(f"Chuỗi Base64 chữ ký không hợp lệ: {str(e)}")
    return signature_input


def generate_pixel_pin_id(
    signature_input: bytes | str,
    cosplayer_id: str | None = None,
    timestamp_str: str | None = None,
    target_size: Tuple[int, int] = (256, 256)
) -> str:
    """
    Chuẩn hóa ma trận pixel nét vẽ chữ ký tay và băm thành mã pin_id duy nhất (SHA-256).

    Args:
        signature_input: Byte nhị phân ảnh chữ ký hoặc chuỗi Base64 từ HTML5 Canvas.
        cosplayer_id: (Tùy chọn) ID Cosplayer để tăng tính duy nhất.
        timestamp_str: (Tùy chọn) Chuỗi ISO timestamp thời điểm ký.
        target_size: Kích thước ma trận chuẩn hóa (mặc định 256x256 px).

    Returns:
        str: Chuỗi mã pin_id dạng `pin_<64_char_hex_hash>`

    Raises:
        PixelHasherError: Khi bảng vẽ rỗng (chưa vẽ) hoặc file ảnh lỗi.
    """
    image_bytes = _decode_signature_input(signature_input)

    if not image_bytes:
        raise PixelHasherError("Dữ liệu chữ ký đầu vào rỗng.")

    try:
        input_stream = io.BytesIO(image_bytes)

        with Image.open(input_stream) as img:
            # 1. Đảm bảo chuyển về hệ màu RGBA để trích xuất kênh Alpha (độ trong suốt của nét vẽ)
            img = img.convert("RGBA")
            alpha_channel = img.getchannel("A")

            # 2. Tự động crop khung viền xung quanh nét vẽ (Bounding Box)
            bbox = alpha_channel.getbbox()
            if not bbox:
                raise PixelHasherError("Bảng vẽ chữ ký hoàn toàn rỗng (chưa có nét vẽ).")

            cropped_signature = img.crop(bbox)

            # 3. Chuẩn hóa ma trận về kích thước cố định (target_size)
            normalized_img = cropped_signature.resize(
                target_size, Image.Resampling.LANCZOS
            )

            # 4. Trích xuất mảng byte thô từ kênh Alpha (Alpha Channel Pixel Buffer)
            normalized_alpha = normalized_img.getchannel("A")
            raw_pixel_bytes = normalized_alpha.tobytes()

            # 5. Khởi tạo đối tượng băm SHA-256
            hasher = hashlib.sha256()
            hasher.update(raw_pixel_bytes)

            # (Tùy chọn) Bổ sung Salt gồm cosplayer_id và timestamp nếu được cung cấp
            if cosplayer_id:
                hasher.update(cosplayer_id.encode("utf-8"))
            if timestamp_str:
                hasher.update(timestamp_str.encode("utf-8"))

            hash_hex = hasher.hexdigest()
            pin_id = f"pin_{hash_hex}"

            logger.info(f"Khởi tạo pin_id thành công từ ma trận pixel: {pin_id}")
            return pin_id

    except UnidentifiedImageError:
        raise PixelHasherError("Tệp tin chữ ký không đúng định dạng ảnh.")
    except PixelHasherError:
        raise
    except Exception as e:
        logger.error(f"Lỗi không xác định khi băm pixel chữ ký: {str(e)}")
        raise PixelHasherError(f"Không thể tính toán mã băm pixel: {str(e)}")