from fastapi import APIRouter
from app.api.v1.endpoints import pin_function

api_router = APIRouter()
api_router.include_router(pin_function.router, prefix="/pins", tags=["Cosplay Pins"])