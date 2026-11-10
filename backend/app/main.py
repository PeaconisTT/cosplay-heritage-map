from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router

# Thiết lập Logger cho Backend
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("cosplay_map")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Xử lý sự kiện khi server khởi chạy (Startup) và dừng (Shutdown)."""
    logger.info("🚀 Khởi chạy ứng dụng Backend Bản đồ Cosplay API...")
    yield
    logger.info("🛑 Đã dừng ứng dụng Backend.")


# Khởi tạo ứng dụng FastAPI
app = FastAPI(
    title="Bản đồ Cosplay API",
    description="Backend API cho hệ thống Bản đồ Cosplay Ảo - Digital Heritage Atlas",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Cấu hình CORS Middleware (Cho phép kết nối từ Frontend)
origins = [
    "http://localhost:5173",  # Vite Dev Server
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "*"                       # Cho phép tất cả nguồn truy cập ở môi trường Local
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Endpoints kiểm tra trạng thái Server (Health Check)
@app.get("/", tags=["Health Check"])
async def root():
    return {
        "status": "online",
        "service": "Bản đồ Cosplay API Engine",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health Check"])
async def health_check():
    return {"status": "healthy"}


# Tích hợp Router API v1
app.include_router(api_router, prefix="/api/v1")