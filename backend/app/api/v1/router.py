from fastapi import APIRouter
from app.api.v1.endpoints import pins

api_router = APIRouter()
api_router.include_router(pins.router, prefix="/pins", tags=["Cosplay Pins"])