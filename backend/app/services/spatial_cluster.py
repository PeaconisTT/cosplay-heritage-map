import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_spatial_clusters(
    db: AsyncSession,
    eps: float = 80.0,
    min_points: int = 2,
    event_id: Optional[UUID] = None,
    work_title: Optional[str] = None,
    alias_first_letter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Phân cụm dữ liệu Pin 2D không-địa-lý bằng thuật toán PostGIS ST_ClusterDBSCAN.

    Args:
        db: AsyncSession CSDL PostgreSQL.
        eps: Bán kính khoảng cách tối đa giữa các điểm để gộp cụm (đơn vị pixel 2D).
        min_points: Số lượng điểm tối thiểu để cấu thành một Cụm tròn (Cluster).
        event_id: (Tùy chọn) Lọc theo ID sự kiện (Dành cho Map Sự kiện).
        work_title: (Tùy chọn) Lọc theo tên tác phẩm nguyên tác (Dành cho Map IP).
        alias_first_letter: (Tùy chọn) Lọc theo chữ cái đầu nghệ danh (Dành cho Map Cosplayer A-Z).

    Returns:
        List[Dict[str, Any]]: Danh sách các Cụm tròn (Cluster) và Điểm đơn lẻ (Single Pin).
    """
    # 1. Khởi tạo điều kiện lọc WHERE linh hoạt
    where_clauses = ["moderation_status = 'APPROVED'"]
    params: Dict[str, Any] = {
        "eps": eps,
        "min_points": min_points
    }

    if event_id:
        where_clauses.append("event_id = :event_id")
        params["event_id"] = str(event_id)

    if work_title:
        where_clauses.append("work_title = :work_title")
        params["work_title"] = work_title

    if alias_first_letter:
        where_clauses.append("alias_first_letter = :alias_first_letter")
        params["alias_first_letter"] = alias_first_letter.upper()

    where_stmt = " AND ".join(where_clauses)

    # 2. Câu lệnh SQL CTE sử dụng ST_ClusterDBSCAN & ST_Centroid trong PostGIS
    query_sql = text(f"""
        WITH clustered_pins AS (
            SELECT
                pin_id,
                cosplayer_name,
                character_name,
                work_title,
                media_url,
                is_verified,
                virtual_coord,
                ST_X(virtual_coord) AS x,
                ST_Y(virtual_coord) AS y,
                ST_ClusterDBSCAN(virtual_coord, eps := :eps, minpoints := :min_points) OVER () AS cluster_id
            FROM cosplay_pins
            WHERE {where_stmt}
        ),
        -- Nhóm các điểm gom thành Cụm tròn (Cluster)
        grouped_clusters AS (
            SELECT
                cluster_id,
                COUNT(*) AS count,
                ST_X(ST_Centroid(ST_Collect(virtual_coord))) AS center_x,
                ST_Y(ST_Centroid(ST_Collect(virtual_coord))) AS center_y,
                json_agg(
                    json_build_object(
                        'pin_id', pin_id,
                        'cosplayer_name', cosplayer_name,
                        'character_name', character_name,
                        'work_title', work_title,
                        'media_url', media_url,
                        'is_verified', is_verified,
                        'virtual_coord', json_build_object('x', x, 'y', y)
                    )
                ) AS items
            FROM clustered_pins
            WHERE cluster_id IS NOT NULL
            GROUP BY cluster_id
        ),
        -- Giữ nguyên các Điểm đơn lẻ (Noise / Single Pins)
        single_pins AS (
            SELECT
                pin_id,
                cosplayer_name,
                character_name,
                work_title,
                media_url,
                is_verified,
                x,
                y
            FROM clustered_pins
            WHERE cluster_id IS NULL
        )
        -- Hợp nhất kết quả trả về cho Frontend Leaflet
        SELECT 
            'cluster' AS type,
            cluster_id::text AS id,
            center_x AS x,
            center_y AS y,
            count,
            items
        FROM grouped_clusters
        UNION ALL
        SELECT 
            'single' AS type,
            pin_id::text AS id,
            x,
            y,
            1 AS count,
            json_build_array(
                json_build_object(
                    'pin_id', pin_id,
                    'cosplayer_name', cosplayer_name,
                    'character_name', character_name,
                    'work_title', work_title,
                    'media_url', media_url,
                    'is_verified', is_verified,
                    'virtual_coord', json_build_object('x', x, 'y', y)
                )
            ) AS items
        FROM single_pins;
    """)

    result = await db.execute(query_sql, params)
    rows = result.fetchall()

    clusters_output = []
    for row in rows:
        clusters_output.append({
            "type": row.type,
            "id": row.id,
            "count": row.count,
            "center": {"x": float(row.x), "y": float(row.y)},
            "items": row.items
        })

    logger.info(f"Phân cụm PostGIS hoàn tất: Tìm thấy {len(clusters_output)} cụm/điểm hiển thị.")
    return clusters_output