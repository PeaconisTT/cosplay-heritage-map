-- Kích hoạt extension PostGIS cho hệ tọa độ không gian
CREATE EXTENSION IF NOT EXISTS postgis;

-- (Tùy chọn) Kích hoạt extension pgvector phục vụ tính toán pHash / Vector Search
CREATE EXTENSION IF NOT EXISTS vector;

-- Kiểm tra phiên bản PostGIS đã cài đặt
SELECT PostGIS_Full_Version();