"""行政区划边界数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import AdministrativeBoundary, MonitoringProject


class BoundaryDAO:
    """封装项目行政区划边界空间查询。"""

    async def get_boundaries(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> Sequence[object]:
        """查询项目行政区划边界及 GeoJSON 几何。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            Sequence[object]: 行政区划边界数据行。
        """
        result = await db.execute(
            select(
                AdministrativeBoundary.boundary_code,
                AdministrativeBoundary.boundary_name,
                AdministrativeBoundary.boundary_level,
                AdministrativeBoundary.parent_code,
                AdministrativeBoundary.source_name,
                AdministrativeBoundary.source_uri,
                AdministrativeBoundary.source_version,
                AdministrativeBoundary.source_updated_at,
                func.ST_AsGeoJSON(AdministrativeBoundary.geom).label("geometry"),
            )
            .join(
                MonitoringProject,
                AdministrativeBoundary.project_id == MonitoringProject.id,
            )
            .where(MonitoringProject.project_code == project_code)
            .order_by(AdministrativeBoundary.boundary_code)
        )
        return result.all()
