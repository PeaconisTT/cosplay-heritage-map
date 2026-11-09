import base64
import io
import pytest
from PIL import Image
from app.services.pixel_hasher import generate_pixel_pin_id, PixelHasherError

"""Hiển thị 2 lựa chọn: (1) Chọn ảnh chữ ký từ file PNG, (2) Tạo ảnh chữ ký giả lập từ byte nhị phân. Dùng pytest để kiểm tra các trường hợp thành công và thất bại."""

def select_choice_for_signature_input() -> bytes:
    """Cho phép người dùng chọn giữa 2 cách nhập dữ liệu chữ ký."""
    print("Chọn cách nhập dữ liệu chữ ký:")
    print("1. Chọn file PNG từ đường dẫn.")
    print("2. Tạo ảnh chữ ký giả lập từ byte nhị phân.")
    choice = input("Nhập 1 hoặc 2: ").strip()

    if choice == "1":
        file_path = input("Nhập đường dẫn file PNG chữ ký: ").strip()
        return load_image_from_file(file_path)
    elif choice == "2":
        return create_dummy_signature_bytes(draw_stroke=True)
    else:
        raise ValueError("Lựa chọn không hợp lệ. Vui lòng nhập 1 hoặc 2.")
def load_image_from_file(file_path: str) -> bytes:
    """Đọc file ảnh PNG từ đường dẫn và trả về byte nhị phân."""
    with open(file_path, "rb") as f:
        return f.read()

def create_dummy_signature_bytes(color: str = "black", draw_stroke: bool = True) -> bytes:

    """Tạo file PNG chữ ký giả lập có chứa nét vẽ (hoặc trong suốt rỗng)."""
    img = Image.new("RGBA", (400, 200), (255, 255, 255, 0))
    
    if draw_stroke:
        # Vẽ một đường chéo giả lập nét ký tay
        for i in range(50, 150):
            img.putpixel((i, i), (0, 0, 0, 255))
            img.putpixel((i + 1, i), (0, 0, 0, 255))

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def test_generate_pin_id_from_bytes_success():
    raw_bytes = create_dummy_signature_bytes(draw_stroke=True)
    pin_id = generate_pixel_pin_id(raw_bytes)

    assert pin_id.startswith("pin_")
    # Độ dài = 4 ("pin_") + 64 (SHA-256 Hex) = 68 ký tự
    assert len(pin_id) == 68


def test_generate_pin_id_from_base64_string():
    raw_bytes = create_dummy_signature_bytes(draw_stroke=True)
    b64_str = f"data:image/png;base64,{base64.b64encode(raw_bytes).decode('utf-8')}"

    pin_id_from_b64 = generate_pixel_pin_id(b64_str)
    pin_id_from_bytes = generate_pixel_pin_id(raw_bytes)

    # Chữ ký giống nhau ở 2 định dạng phải cho cùng 1 mã pin_id
    assert pin_id_from_b64 == pin_id_from_bytes


def test_deterministic_hashing_same_signature():
    raw_bytes = create_dummy_signature_bytes(draw_stroke=True)
    
    pin_id_1 = generate_pixel_pin_id(raw_bytes, cosplayer_id="usr_01")
    pin_id_2 = generate_pixel_pin_id(raw_bytes, cosplayer_id="usr_01")

    assert pin_id_1 == pin_id_2


def test_blank_signature_raises_error():
    blank_bytes = create_dummy_signature_bytes(draw_stroke=False)

    with pytest.raises(PixelHasherError) as exc_info:
        generate_pixel_pin_id(blank_bytes)
    
    assert "bảng vẽ chữ ký hoàn toàn rỗng" in str(exc_info.value).lower()


def test_invalid_image_data_raises_error():
    invalid_data = b"not_an_image_string"

    with pytest.raises(PixelHasherError):
        generate_pixel_pin_id(invalid_data)