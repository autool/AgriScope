"""行政区划边界业务服务。"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.dao.boundary_dao import BoundaryDAO
from app.schemas.boundary import BoundaryFeatureCollectionResponse


class BoundaryService:
    """生成项目行政区划边界专题图层。"""

    def __init__(self, dao: BoundaryDAO | None = None) -> None:
        """初始化行政区划边界服务。

        Args:
            dao: 行政区划边界 DAO。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or BoundaryDAO()

    async def get_boundaries(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> BoundaryFeatureCollectionResponse:
        """查询项目行政区划边界 GeoJSON。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            BoundaryFeatureCollectionResponse: 行政区划边界专题图层。
        """
        rows = await self.dao.get_boundaries(db, project_code)
        if not rows:
            raise NotFoundException(f"未找到项目 {project_code} 的行政区划边界")
        return BoundaryFeatureCollectionResponse(
            features=[
                {
                    "type": "Feature",
                    "geometry": json.loads(row.geometry),
                    "properties": {
                        "boundary_code": row.boundary_code,
                        "boundary_name": row.boundary_name,
                        "boundary_level": row.boundary_level,
                        "parent_code": row.parent_code,
                        "source_name": row.source_name,
                        "source_uri": row.source_uri,
                        "source_version": row.source_version,
                        "source_updated_at": (
                            row.source_updated_at.isoformat()
                            if row.source_updated_at
                            else None
                        ),
                    },
                }
                for row in rows
            ]
        )
