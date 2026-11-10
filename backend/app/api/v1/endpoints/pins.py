from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_pins():
    """Endpoint thử nghiệm danh sách Pins."""
    return {"message": "Danh sách Pin từ API v1"}