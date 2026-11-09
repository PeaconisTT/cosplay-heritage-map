import io
import pytest
from PIL import Image
from app.services.image_sanitizer import sanitize_and_convert_to_webp, ImageSanitizationError


def create_dummy_image_with_exif() -> bytes:
    """Tạo một file ảnh JPEG giả lập chứa thông tin EXIF GPS dummy."""
    img = Image.new("RGB", (800, 600), color="red")
    output = io.BytesIO()
    # Ghi ảnh kèm một số tag thông tin giả lập
    exif = img.getexif()
    exif[0x0110] = "Dummy Camera Model"  # Model tag
    img.save(output, format="JPEG", exif=exif)
    return output.getvalue()


def test_sanitize_removes_exif_and_converts_to_webp():
    raw_bytes = create_dummy_image_with_exif()
    
    # Thực thi làm sạch ảnh
    clean_bytes, width, height = sanitize_and_convert_to_webp(raw_bytes)

    # Kiểm tra kích thước trả về
    assert width == 800
    assert height == 600

    # Đọc lại ảnh đã làm sạch
    with Image.open(io.BytesIO(clean_bytes)) as result_img:
        assert result_img.format == "WEBP"
        # Xác minh không còn bất kỳ tag EXIF nào tồn tại
        exif_data = result_img.getexif()
        assert len(exif_data) == 0


def test_invalid_image_raises_error():
    invalid_bytes = b"not_an_image_binary_data"
    with pytest.raises(ImageSanitizationError):
        sanitize_and_convert_to_webp(invalid_bytes)