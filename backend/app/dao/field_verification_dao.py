"""外业核查数据访问对象。"""

from collections.abc import Sequence

from geoalchemy2 import Geography
from sqlalchemy import Row, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot import FarmlandPlot
from app.models.workbench import (
    AdministrativeBoundary,
    FieldVerification,
    QualityIssue,
    TaskPlot,
)


class FieldVerificationDAO:
    """封装外业核查记录与最近邻空间匹配查询。"""

    async def get_task_records(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[Row[tuple[FieldVerification, float, float]]]:
        """查询任务外业核查记录及 WGS84 坐标。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            Sequence[Row]: 核查记录、经度和纬度查询结果。
        """
        result = await db.execute(
            select(
                FieldVerification,
                func.ST_X(FieldVerification.location).label("lon"),
                func.ST_Y(FieldVerification.location).label("lat"),
            )
            .where(FieldVerification.task_id == task_id)
            .order_by(FieldVerification.captured_at.desc())
        )
        return result.all()

    async def get_by_code(
        self,
        db: AsyncSession,
        verification_code: str,
    ) -> FieldVerification | None:
        """按编号查询外业核查记录。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录编号。

        Returns:
            FieldVerification | None: 核查记录，不存在时返回 None。
        """
        result = await db.execute(
            select(FieldVerification).where(
                FieldVerification.verification_code == verification_code
            )
        )
        return result.scalar_one_or_none()

    async def get_by_code_for_update(
        self,
        db: AsyncSession,
        verification_code: str,
    ) -> FieldVerification | None:
        """锁定并查询待处置外业记录。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录编号。

        Returns:
            FieldVerification | None: 已锁定记录；不存在时返回 None。
        """
        result = await db.execute(
            select(FieldVerification)
            .where(FieldVerification.verification_code == verification_code)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_import_conflicts_for_update(
        self,
        db: AsyncSession,
        task_id: int,
        verification_codes: list[str],
        source_name: str,
        source_record_ids: list[str],
    ) -> Sequence[FieldVerification]:
        """锁定编号或来源记录与导入批次冲突的外业记录。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。
            verification_codes: 待导入核查编号。
            source_name: 数据来源名称。
            source_record_ids: 来源系统记录编号。

        Returns:
            Sequence[FieldVerification]: 已锁定的冲突记录。
        """
        result = await db.execute(
            select(FieldVerification)
            .where(
                FieldVerification.task_id == task_id,
                or_(
                    FieldVerification.verification_code.in_(verification_codes),
                    (
                        (FieldVerification.source_name == source_name)
                        & FieldVerification.source_record_id.in_(source_record_ids)
                    ),
                ),
            )
            .with_for_update()
        )
        return result.scalars().all()

    async def is_point_within_project(
        self,
        db: AsyncSession,
        project_id: int,
        lon: float,
        lat: float,
    ) -> bool:
        """判断 WGS84 外业点是否位于项目省级边界内。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            lon: WGS84 经度。
            lat: WGS84 纬度。

        Returns:
            bool: 点位于项目省域内时返回 True。
        """
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        result = await db.execute(
            select(
                func.coalesce(
                    func.bool_or(func.ST_Covers(AdministrativeBoundary.geom, point)),
                    False,
                )
            ).where(
                AdministrativeBoundary.project_id == project_id,
                AdministrativeBoundary.boundary_level == "province",
            )
        )
        return bool(result.scalar_one())

    async def get_coordinates(
        self,
        db: AsyncSession,
        verification_id: int,
    ) -> tuple[float, float]:
        """读取外业核查点 WGS84 坐标。

        Args:
            db: 异步数据库会话。
            verification_id: 外业记录主键。

        Returns:
            tuple[float, float]: 经度和纬度。
        """
        result = await db.execute(
            select(
                func.ST_X(FieldVerification.location),
                func.ST_Y(FieldVerification.location),
            ).where(FieldVerification.id == verification_id)
        )
        lon, lat = result.one()
        return float(lon), float(lat)

    async def create(
        self,
        db: AsyncSession,
        record: FieldVerification,
        lon: float,
        lat: float,
    ) -> FieldVerification:
        """创建带 WGS84 点几何的外业核查记录。

        Args:
            db: 异步数据库会话。
            record: 待创建核查记录。
            lon: WGS84 经度。
            lat: WGS84 纬度。

        Returns:
            FieldVerification: 已写入核查记录。
        """
        record.location = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        db.add(record)
        await db.flush()
        await db.refresh(record)
        return record

    async def find_nearest_plot(
        self,
        db: AsyncSession,
        task_id: int,
        record: FieldVerification,
        search_radius_m: float,
    ) -> tuple[str, float, bool] | None:
        """查找距离外业点最近的内业图斑。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            record: 外业核查记录。
            search_radius_m: 最近邻最大搜索半径，单位米。

        Returns:
            tuple[str, float, bool] | None: 图斑编号、距离和包含关系。
        """
        location = (
            select(FieldVerification.location)
            .where(FieldVerification.id == record.id)
            .scalar_subquery()
        )
        distance = func.ST_Distance(
            cast(FarmlandPlot.geom, Geography(srid=4326)),
            cast(location, Geography(srid=4326)),
        )
        result = await db.execute(
            select(
                FarmlandPlot.plot_code,
                distance.label("distance_m"),
                func.ST_Covers(FarmlandPlot.geom, location).label("contains"),
            )
            .join(TaskPlot, TaskPlot.plot_code == FarmlandPlot.plot_code)
            .where(
                TaskPlot.task_id == task_id,
                FarmlandPlot.interpretation_status != "deleted",
                func.ST_DWithin(
                    cast(FarmlandPlot.geom, Geography(srid=4326)),
                    cast(location, Geography(srid=4326)),
                    search_radius_m,
                ),
            )
            .order_by(FarmlandPlot.geom.op("<->")(location))
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        return row.plot_code, float(row.distance_m), bool(row.contains)

    async def resolve_quality_issue(
        self,
        db: AsyncSession,
        task_id: int,
        verification_code: str,
        resolved_by: str,
        resolved_by_code: str,
        resolved_by_role: str,
        resolution_comment: str,
    ) -> None:
        """关闭指定外业核查记录关联的质量问题。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            verification_code: 外业记录编号。
            resolved_by: 处置人显示姓名。
            resolved_by_code: 处置人稳定编码。
            resolved_by_role: 处置时角色编码。
            resolution_comment: 处置说明。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.rule_code == f"FIELD_{verification_code}",
                QualityIssue.status == "open",
            )
            .values(
                status="resolved",
                resolved_at=func.now(),
                resolved_by=resolved_by,
                resolved_by_code=resolved_by_code,
                resolved_by_role=resolved_by_role,
                resolution_comment=resolution_comment,
            )
        )

    async def clear_field_issue(
        self,
        db: AsyncSession,
        task_id: int,
        verification_code: str,
    ) -> None:
        """关闭重新匹配前的自动外业质量问题并保留历史。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            verification_code: 外业记录编号。

        Returns:
            None: 无返回值。
        """
        await db.execute(
            update(QualityIssue)
            .where(
                QualityIssue.task_id == task_id,
                QualityIssue.rule_code == f"FIELD_{verification_code}",
                QualityIssue.source == "auto",
                QualityIssue.status == "open",
            )
            .values(status="resolved", resolved_at=func.now())
        )
