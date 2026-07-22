"""种植面积统计分析业务服务。"""

import csv
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from io import StringIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.statistics_dao import StatisticsDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import AreaStatisticsImportBatch, ReviewRecord
from app.schemas.statistics import (
    AreaGroupItem,
    AreaStatisticsResponse,
    AreaStatisticsSnapshotImportMetadata,
    AreaStatisticsSnapshotImportResponse,
    AreaTrendItem,
)
from app.services.project_user_service import ProjectUserService
from app.services.statistics_snapshot_parser import StatisticsSnapshotCsvParser


class StatisticsService:
    """生成任务作用域内行政区、地类、作物和年度统计。"""

    def __init__(
        self,
        dao: StatisticsDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        snapshot_parser: StatisticsSnapshotCsvParser | None = None,
    ) -> None:
        """初始化面积统计服务。

        Args:
            dao: 面积统计 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目用户能力服务。
            snapshot_parser: 历史统计 CSV 解析服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or StatisticsDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.snapshot_parser = snapshot_parser or StatisticsSnapshotCsvParser()

    @staticmethod
    def _build_groups(rows: list[object], total_area: Decimal) -> list[AreaGroupItem]:
        """将数据库聚合行转换为统一面积指标。

        Args:
            rows: 数据库聚合行。
            total_area: 当前任务图斑总面积。

        Returns:
            list[AreaGroupItem]: 前端可直接展示的统计分组。
        """
        groups = []
        for row in rows:
            area = Decimal(str(row.area_ha))
            percentage = (area / total_area * 100) if total_area else Decimal(0)
            groups.append(
                AreaGroupItem(
                    label=row.label,
                    code=getattr(row, "code", None),
                    parent_label=getattr(row, "parent_label", None),
                    plot_count=int(row.plot_count),
                    area_ha=round(float(area), 2),
                    area_mu=round(float(area * Decimal("15")), 2),
                    percentage=round(float(percentage), 2),
                )
            )
        return groups

    @staticmethod
    def _build_trend(
        snapshots: list[object],
        monitor_year: int,
        current_area: Decimal,
        current_recorded_at: datetime,
    ) -> list[AreaTrendItem]:
        """将历史快照与当前任务实时面积合并为可信年度趋势。

        Args:
            snapshots: 项目历史面积快照。
            monitor_year: 当前项目监测年度。
            current_area: 当前任务实时总面积。
            current_recorded_at: 当前任务实时汇总时间。

        Returns:
            list[AreaTrendItem]: 年度面积和同比变化。
        """
        year_values = {
            int(snapshot.monitor_year): (
                Decimal(str(snapshot.total_area_ha)),
                getattr(snapshot, "source_name", None)
                or "历史快照（待补来源）",
                getattr(snapshot, "source_version", None),
                getattr(snapshot, "generated_at", current_recorded_at),
                False,
            )
            for snapshot in snapshots
            if int(snapshot.monitor_year) < monitor_year
        }
        year_values[monitor_year] = (
            current_area,
            "当前任务实时汇总",
            None,
            current_recorded_at,
            True,
        )
        result: list[AreaTrendItem] = []
        previous_area: Decimal | None = None
        for year, value in sorted(year_values.items()):
            area, source_name, source_version, recorded_at, is_current = value
            year_over_year = None
            if previous_area:
                year_over_year = round(
                    float((area - previous_area) / previous_area * 100),
                    2,
                )
            result.append(
                AreaTrendItem(
                    year=year,
                    area_ha=round(float(area), 2),
                    year_over_year=year_over_year,
                    source_name=source_name,
                    source_version=source_version,
                    recorded_at=recorded_at,
                    is_current=is_current,
                )
            )
            previous_area = area
        return result

    async def get_area_statistics(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> AreaStatisticsResponse:
        """获取任务作用域内多维面积统计与年度趋势。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            AreaStatisticsResponse: 面积聚合分析结果。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")

        totals = await self.dao.get_totals(db, task.id)
        land_rows = await self.dao.get_land_class_groups(db, task.id)
        crop_rows = await self.dao.get_crop_type_groups(db, task.id)
        planting_rows = await self.dao.get_planting_mode_groups(db, task.id)
        city_rows = await self.dao.get_city_groups(db, task.id)
        district_rows = await self.dao.get_district_groups(db, task.id)
        village_rows = await self.dao.get_village_groups(db, task.id)
        farmland_count, crop_assigned_count = (
            await self.dao.get_crop_assignment_counts(db, task.id)
        )
        monitor_year = await self.dao.get_project_monitor_year(
            db,
            task.project_id,
        )
        snapshots = await self.dao.get_annual_trend(db, task.project_id)

        plot_count, total_value = totals
        total_area = Decimal(str(total_value))
        land_groups = self._build_groups(list(land_rows), total_area)
        farmland_area = sum(
            item.area_ha for item in land_groups if item.label == "耕地"
        )
        generated_at = datetime.now(UTC)
        return AreaStatisticsResponse(
            task_code=task_code,
            monitor_year=monitor_year,
            generated_at=generated_at,
            total_plot_count=int(plot_count),
            total_area_ha=round(float(total_area), 2),
            total_area_mu=round(float(total_area * Decimal("15")), 2),
            average_plot_area_ha=(
                round(float(total_area / int(plot_count)), 2) if plot_count else 0
            ),
            farmland_area_ha=round(farmland_area, 2),
            crop_assigned_plot_count=crop_assigned_count,
            crop_assignment_rate=(
                round(crop_assigned_count / farmland_count * 100, 2)
                if farmland_count
                else 0
            ),
            by_land_class=land_groups,
            by_crop_type=self._build_groups(list(crop_rows), total_area),
            by_planting_mode=self._build_groups(list(planting_rows), total_area),
            by_city=self._build_groups(list(city_rows), total_area),
            by_district=self._build_groups(list(district_rows), total_area),
            by_village=self._build_groups(list(village_rows), total_area),
            annual_trend=self._build_trend(
                list(snapshots),
                monitor_year,
                total_area,
                generated_at,
            ),
        )

    async def import_history_csv(
        self,
        db: AsyncSession,
        task_code: str,
        metadata: AreaStatisticsSnapshotImportMetadata,
        filename: str,
        content: bytes,
    ) -> AreaStatisticsSnapshotImportResponse:
        """原子导入真实历史年度面积统计 CSV。

        Args:
            db: 异步数据库会话。
            task_code: 当前作业任务编号。
            metadata: 来源、冲突策略和操作人审计。
            filename: 原始 CSV 文件名。
            content: 原始 CSV 字节。

        Returns:
            AreaStatisticsSnapshotImportResponse: 导入批次和年度结果。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            metadata.operator_code,
            "import_statistics_history",
        )
        records = self.snapshot_parser.parse(filename, content)
        monitor_year = await self.dao.get_project_monitor_year(db, task.project_id)
        invalid_years = sorted(
            record.monitor_year
            for record in records
            if record.monitor_year >= monitor_year
        )
        if invalid_years:
            raise ValidationException(
                f"历史快照年度必须早于当前监测年度 {monitor_year}："
                f"{', '.join(str(year) for year in invalid_years)}"
            )
        years = [record.monitor_year for record in records]
        existing = await self.dao.get_snapshots_for_update(
            db,
            task.project_id,
            years,
        )
        if existing and metadata.conflict_strategy == "reject":
            conflict_years = "、".join(str(year) for year in sorted(existing))
            raise ValidationException(f"历史年度快照已存在：{conflict_years}")

        checksum = sha256(content).hexdigest()
        imported_at = datetime.now(UTC)
        batch_code = (
            f"STAT-{imported_at:%Y%m%dT%H%M%S}-"
            f"{checksum[:8]}-{secrets.token_hex(4)}"
        )
        batch = AreaStatisticsImportBatch(
            project_id=task.project_id,
            batch_code=batch_code,
            source_name=metadata.source_name,
            source_uri=metadata.source_uri,
            source_version=metadata.source_version,
            source_checksum_sha256=checksum,
            conflict_strategy=metadata.conflict_strategy,
            row_count=len(records),
            snapshot_payload=[record.model_dump(mode="json") for record in records],
            imported_by=operator.display_name,
            imported_by_code=operator.user_code,
            imported_by_role=operator.role_code,
            import_comment=metadata.comment,
            created_at=imported_at,
        )
        try:
            await self.dao.create_import_batch(db, batch)
            for record in records:
                await self.dao.save_snapshot(
                    db,
                    existing.get(record.monitor_year),
                    project_id=task.project_id,
                    monitor_year=record.monitor_year,
                    total_area_ha=record.total_area_ha,
                    farmland_area_ha=record.farmland_area_ha,
                    crop_area_ha=record.crop_area_ha,
                    import_batch_id=batch.id,
                )
            task.updated_at = imported_at
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="statistics",
                    action="statistics_history_imported",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"批次 {batch_code} 导入历史年度 {years}；"
                        f"来源 {metadata.source_name} {metadata.source_version}；"
                        f"策略 {metadata.conflict_strategy}；SHA256 {checksum}；"
                        f"文件 {filename}；{metadata.comment}"
                    ),
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException("历史年度统计导入批次或年度发生冲突") from exc
        return AreaStatisticsSnapshotImportResponse(
            task_code=task_code,
            batch_code=batch_code,
            imported_count=len(records) - len(existing),
            replaced_count=len(existing),
            years=sorted(years),
            source_checksum_sha256=checksum,
            imported_by=operator.display_name,
            imported_by_code=operator.user_code,
            imported_by_role=operator.role_code,
            imported_at=imported_at,
        )

    def build_history_csv_template(self) -> bytes:
        """生成历史年度统计 CSV 标准模板。

        Returns:
            bytes: UTF-8 BOM CSV 模板。
        """
        return self.snapshot_parser.build_template()

    async def export_area_statistics_csv(
        self,
        db: AsyncSession,
        task_code: str,
        operator_code: str,
    ) -> tuple[str, bytes]:
        """导出任务多维面积统计 CSV 并执行项目负责人权限校验。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            operator_code: 导出人稳定用户编码。

        Returns:
            tuple[str, bytes]: 下载文件名和 UTF-8 BOM CSV 内容。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            operator_code,
            "export_statistics",
        )
        summary = await self.get_area_statistics(db, task_code)
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["任务编号", summary.task_code])
        writer.writerow(["监测年度", summary.monitor_year])
        writer.writerow(["导出人", operator.display_name])
        writer.writerow(["导出人编码", operator.user_code])
        writer.writerow(["导出时角色", operator.role_code])
        writer.writerow(["生成时间", summary.generated_at.isoformat()])
        writer.writerow(["任务图斑数", summary.total_plot_count])
        writer.writerow(["总面积（公顷）", summary.total_area_ha])
        writer.writerow(["总面积（亩）", summary.total_area_mu])
        writer.writerow(["作物录入完成率（%）", summary.crop_assignment_rate])

        sections = (
            ("地级区域", summary.by_city),
            ("县区", summary.by_district),
            ("一级地类", summary.by_land_class),
            ("作物类型", summary.by_crop_type),
            ("种植模式", summary.by_planting_mode),
            ("权属村", summary.by_village),
        )
        for section_name, items in sections:
            writer.writerow([])
            writer.writerow([section_name])
            writer.writerow(
                [
                    "编码",
                    "名称",
                    "上级区域",
                    "图斑数",
                    "面积（公顷）",
                    "面积（亩）",
                    "占比（%）",
                ]
            )
            for item in items:
                writer.writerow(
                    [
                        item.code or "",
                        item.label,
                        item.parent_label or "",
                        item.plot_count,
                        item.area_ha,
                        item.area_mu,
                        item.percentage,
                    ]
                )
        writer.writerow([])
        writer.writerow(["年度趋势"])
        writer.writerow(["年度", "面积（公顷）", "同比（%）"])
        for item in summary.annual_trend:
            writer.writerow(
                [
                    item.year,
                    item.area_ha,
                    "" if item.year_over_year is None else item.year_over_year,
                ]
            )
        filename = f"{task_code}_area_statistics_{summary.monitor_year}.csv"
        return filename, output.getvalue().encode("utf-8-sig")
