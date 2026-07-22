"""成果交付包生成、清单管理与下载业务服务。"""

import csv
import hashlib
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.delivery_dao import DeliveryDAO
from app.dao.workbench_dao import QualityGateSummary, WorkbenchDAO
from app.models.workbench import DeliveryPackage, ReviewRecord
from app.schemas.delivery import (
    DeliveryGenerateRequest,
    DeliveryListResponse,
    DeliveryManifestItem,
    DeliveryPackageResponse,
)
from app.services.disaster_service import DisasterService
from app.services.project_user_service import ProjectUserService
from app.services.statistics_service import StatisticsService


class DeliveryService:
    """生成可下载、可校验、可审计的成果交付包。"""

    def __init__(
        self,
        dao: DeliveryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        statistics_service: StatisticsService | None = None,
        disaster_service: DisasterService | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化成果交付服务。

        Args:
            dao: 成果交付 DAO。
            workbench_dao: 工作台公共 DAO。
            statistics_service: 面积统计服务。
            disaster_service: 灾害评估服务。
            project_user_service: 项目用户与角色校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or DeliveryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.statistics_service = statistics_service or StatisticsService()
        self.disaster_service = disaster_service or DisasterService()
        self.project_user_service = project_user_service or ProjectUserService()
        self.storage_dir = (
            Path(__file__).resolve().parents[2] / "storage" / "deliveries"
        )

    @staticmethod
    def _get_stale_reason(
        package: DeliveryPackage,
        task: object,
    ) -> str | None:
        """判断成果包是否仍对应任务当前版本。

        Args:
            package: 成果交付包模型。
            task: 当前任务模型。

        Returns:
            str | None: 失效原因；仍为当前成果时返回 None。
        """
        if package.status not in {"completed", "superseded"}:
            return "成果包未处于已完成状态"
        if package.completed_at is None:
            return "成果包缺少完成时间"
        if package.completed_at < task.updated_at:
            return "任务在成果包生成后发生过变更"
        package_plot_count = package.quality_summary.get("plot_count")
        if package_plot_count != task.total_plots:
            return "成果包图斑数量与当前任务作用域不一致"
        return None

    @classmethod
    def _to_response(
        cls,
        package: DeliveryPackage,
        task: object,
    ) -> DeliveryPackageResponse:
        """将成果包模型转换为 API 响应。

        Args:
            package: 成果交付包模型。

        Returns:
            DeliveryPackageResponse: 成果交付包响应。
        """
        stale_reason = cls._get_stale_reason(package, task)
        return DeliveryPackageResponse(
            package_code=package.package_code,
            package_name=package.package_name,
            version=package.version,
            status=package.status,
            generated_by=package.generated_by,
            generated_by_code=package.generated_by_code,
            generated_by_role=package.generated_by_role,
            file_size_bytes=package.file_size_bytes,
            checksum_sha256=package.checksum_sha256,
            manifest=[DeliveryManifestItem(**item) for item in package.manifest],
            quality_summary=package.quality_summary,
            created_at=package.created_at,
            completed_at=package.completed_at,
            download_url=(
                f"/api/v1/deliveries/{package.package_code}/download"
                if stale_reason is None
                else None
            ),
            is_current=stale_reason is None,
            stale_reason=stale_reason,
        )

    @staticmethod
    def _get_quality_gate_blocker(
        gate: QualityGateSummary,
    ) -> str | None:
        """判断当前任务质量门禁是否具备成果生成条件。

        Args:
            gate: 当前任务图斑质量门禁汇总。

        Returns:
            str | None: 阻断原因；全部图斑通过且平均分达标时为空。
        """
        if gate.total_count == 0:
            return "当前任务没有可交付的有效图斑"
        if gate.checked_count < gate.total_count:
            return (
                "质量检查尚未覆盖全部图斑：" f"{gate.checked_count}/{gate.total_count}"
            )
        if gate.passing_count < gate.total_count:
            return "仍有图斑未通过质量门禁：" f"{gate.passing_count}/{gate.total_count}"
        if gate.average_score is None or gate.average_score < 80:
            return "任务平均质量得分不足 80"
        return None

    async def list_packages(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> DeliveryListResponse:
        """查询任务交付包和当前生成条件。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            DeliveryListResponse: 交付包列表和生成条件。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        packages = await self.dao.get_packages(db, task.id)
        open_issue_count = await self.workbench_dao.count_open_issues(db, task.id)
        pending_field_count = (
            await self.workbench_dao.count_pending_field_verifications(
                db,
                task.id,
            )
        )
        if task.status != "completed":
            generate_blocker = "任务需完成三级审核后才能生成成果包"
        elif open_issue_count > 0:
            generate_blocker = f"仍有 {open_issue_count} 条问题未关闭"
        elif pending_field_count > 0:
            generate_blocker = f"仍有 {pending_field_count} 条外业疑点未处置"
        else:
            imagery = await self.workbench_dao.get_latest_imagery(
                db,
                task.project_id,
            )
            if imagery is None:
                generate_blocker = "缺少具备实体校验的业务影像"
            else:
                quality_gate = await self.workbench_dao.get_quality_gate_summary(
                    db,
                    task.id,
                )
                generate_blocker = self._get_quality_gate_blocker(quality_gate)
        can_generate = generate_blocker is None
        return DeliveryListResponse(
            task_code=task_code,
            can_generate=can_generate,
            generate_blocker=generate_blocker,
            packages=[self._to_response(package, task) for package in packages],
        )

    async def generate_package(
        self,
        db: AsyncSession,
        task_code: str,
        request: DeliveryGenerateRequest,
    ) -> DeliveryPackageResponse:
        """汇集业务数据并生成实体 ZIP 成果包。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 操作人和成果包名称。

        Returns:
            DeliveryPackageResponse: 已生成成果包。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "completed":
            raise ValidationException("任务需完成三级审核后才能生成成果包")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_delivery",
        )
        open_issue_count = await self.workbench_dao.count_open_issues(db, task.id)
        if open_issue_count > 0:
            raise ValidationException(
                f"仍有 {open_issue_count} 条问题未关闭，不能生成成果包"
            )
        pending_field_count = (
            await self.workbench_dao.count_pending_field_verifications(
                db,
                task.id,
            )
        )
        if pending_field_count > 0:
            raise ValidationException(
                f"仍有 {pending_field_count} 条外业疑点未处置，不能生成成果包"
            )
        imagery = await self.workbench_dao.get_latest_imagery(db, task.project_id)
        if imagery is None:
            raise ValidationException("缺少具备实体校验的业务影像，不能生成成果包")
        quality_gate = await self.workbench_dao.get_quality_gate_summary(
            db,
            task.id,
        )
        quality_gate_blocker = self._get_quality_gate_blocker(quality_gate)
        if quality_gate_blocker is not None:
            raise ValidationException(f"{quality_gate_blocker}，不能生成成果包")

        version = await self.dao.get_next_version(db, task.id)
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        package_code = f"{task_code}-DELIVERY-v{version}-{timestamp}"
        package = await self.dao.add_package(
            db,
            DeliveryPackage(
                task_id=task.id,
                package_code=package_code,
                package_name=(
                    request.package_name or f"{task.task_name}遥感监测成果包 v{version}"
                ),
                version=version,
                status="generating",
                generated_by=operator.display_name,
                generated_by_code=operator.user_code,
                generated_by_role=operator.role_code,
                manifest=[],
                quality_summary={},
            ),
        )

        source_data = await self._load_source_data(db, task)
        manifest = self._build_manifest(source_data)
        quality_summary = self._build_quality_summary(task, source_data)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        package_path = self.storage_dir / f"{package_code}.zip"
        temporary_path = package_path.with_suffix(".zip.tmp")
        try:
            self._write_zip(
                temporary_path,
                task,
                source_data,
                manifest,
                quality_summary,
            )
            temporary_path.replace(package_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        package.status = "completed"
        package.file_uri = str(package_path)
        package.file_size_bytes = package_path.stat().st_size
        package.checksum_sha256 = self._calculate_sha256(package_path)
        package.manifest = manifest
        package.quality_summary = quality_summary
        package.completed_at = datetime.now(UTC)
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="delivery",
                action="delivery_package_generated",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"生成成果交付包 {package_code}，版本 v{version}",
            ),
        )
        await db.commit()
        await db.refresh(package)
        return self._to_response(package, task)

    async def get_package_for_download(
        self,
        db: AsyncSession,
        package_code: str,
        user_code: str,
    ) -> DeliveryPackage:
        """校验并返回可下载成果包。

        Args:
            db: 异步数据库会话。
            package_code: 成果包编号。
            user_code: 当前项目用户稳定编码。

        Returns:
            DeliveryPackage: 可供下载的成果包模型。
        """
        package = await self.dao.get_package_by_code(db, package_code)
        if package is None:
            raise NotFoundException(f"未找到成果包 {package_code}")
        task = await self.workbench_dao.get_task_by_id(db, package.task_id)
        if task is None:
            raise NotFoundException("成果包关联任务不存在")
        await self.project_user_service.require_capability(
            db,
            task.project_id,
            user_code,
            "download_delivery",
        )
        if package.status not in {"completed", "superseded"} or not package.file_uri:
            raise ValidationException("成果包尚未生成完成")
        stale_reason = self._get_stale_reason(package, task)
        if stale_reason is not None:
            raise ValidationException(f"成果包已失效：{stale_reason}")
        if not Path(package.file_uri).is_file():
            raise NotFoundException("成果包文件不存在，请重新生成")
        package_path = Path(package.file_uri)
        if (
            package.file_size_bytes is None
            or package_path.stat().st_size != package.file_size_bytes
        ):
            raise ValidationException("成果包文件大小校验失败，请重新生成")
        if (
            not package.checksum_sha256
            or self._calculate_sha256(package_path) != package.checksum_sha256
        ):
            raise ValidationException("成果包完整性校验失败，请重新生成")
        return package

    async def _load_source_data(
        self,
        db: AsyncSession,
        task: object,
    ) -> dict:
        """加载成果包所需的全部业务数据。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            dict: 图斑、统计、灾害、外业、质量和审核数据。
        """
        plot_rows = await self.dao.get_plot_rows(db, task.id)
        statistics = await self.statistics_service.get_area_statistics(
            db,
            task.task_code,
        )
        disasters = await self.disaster_service.get_summary(db, task.task_code)
        quality_issues = await self.dao.get_quality_issues(db, task.id)
        field_rows = await self.dao.get_field_rows(db, task.id)
        reviews = await self.workbench_dao.get_reviews(db, task.id)
        quality_gate = await self.workbench_dao.get_quality_gate_summary(
            db,
            task.id,
        )
        imagery = await self.workbench_dao.get_latest_imagery(
            db,
            task.project_id,
        )
        return {
            "plot_rows": plot_rows,
            "statistics": statistics,
            "disasters": disasters,
            "quality_issues": quality_issues,
            "field_rows": field_rows,
            "reviews": reviews,
            "quality_gate": quality_gate,
            "imagery": imagery,
        }

    @staticmethod
    def _build_manifest(source_data: dict) -> list[dict]:
        """构建成果文件清单。

        Args:
            source_data: 成果包源数据。

        Returns:
            list[dict]: 成果文件清单。
        """
        return [
            {
                "path": "vector/farmland_plots.geojson",
                "category": "矢量成果",
                "format": "GeoJSON",
                "record_count": len(source_data["plot_rows"]),
                "description": "最终地块边界及种植属性",
            },
            {
                "path": "statistics/area_statistics.csv",
                "category": "统计成果",
                "format": "CSV",
                "record_count": len(source_data["statistics"].by_village),
                "description": "村级、地类和作物面积汇总",
            },
            {
                "path": "disasters/disaster_patches.geojson",
                "category": "灾害成果",
                "format": "GeoJSON",
                "record_count": source_data["disasters"].total_patches,
                "description": "灾害等级和受灾范围图斑",
            },
            {
                "path": "field/field_verifications.geojson",
                "category": "外业核查",
                "format": "GeoJSON",
                "record_count": len(source_data["field_rows"]),
                "description": "外业核查点及空间匹配结论",
            },
            {
                "path": "quality/quality_issues.json",
                "category": "质量检查",
                "format": "JSON",
                "record_count": len(source_data["quality_issues"]),
                "description": "质量问题和整改状态清单",
            },
            {
                "path": "review/review_records.json",
                "category": "审核记录",
                "format": "JSON",
                "record_count": len(source_data["reviews"]),
                "description": "三级审核、版本和操作审计记录",
            },
            {
                "path": "reports/quality_report.md",
                "category": "质量报告",
                "format": "Markdown",
                "record_count": None,
                "description": "成果质量检查报告",
            },
            {
                "path": "reports/acceptance_report.md",
                "category": "验收报告",
                "format": "Markdown",
                "record_count": None,
                "description": "项目成果验收报告",
            },
            {
                "path": "manifest.json",
                "category": "成果清单",
                "format": "JSON",
                "record_count": 9,
                "description": "交付包内容和校验元数据",
            },
        ]

    @staticmethod
    def _build_quality_summary(task: object, source_data: dict) -> dict:
        """构建交付包质量与验收摘要。

        Args:
            task: 当前作业任务。
            source_data: 成果包源数据。

        Returns:
            dict: 可持久化质量摘要。
        """
        issues = source_data["quality_issues"]
        field_rows = source_data["field_rows"]
        quality_gate = source_data["quality_gate"]
        imagery = source_data["imagery"]
        field_count = len(field_rows)
        disaster_count = source_data["disasters"].total_patches
        return {
            "quality_score": float(quality_gate.average_score or 0),
            "plot_count": len(source_data["plot_rows"]),
            "quality_total_count": quality_gate.total_count,
            "quality_checked_count": quality_gate.checked_count,
            "quality_passing_count": quality_gate.passing_count,
            "quality_gate_complete": (
                DeliveryService._get_quality_gate_blocker(quality_gate) is None
            ),
            "open_issue_count": sum(issue.status == "open" for issue in issues),
            "resolved_issue_count": sum(issue.status != "open" for issue in issues),
            "field_verification_count": field_count,
            "pending_field_count": sum(
                item.resolution_status == "pending" for item, _ in field_rows
            ),
            "field_evidence_status": (
                "provided" if field_count > 0 else "not_provided"
            ),
            "disaster_patch_count": disaster_count,
            "affected_area_ha": source_data["disasters"].affected_area_ha,
            "disaster_evidence_status": (
                "provided" if disaster_count > 0 else "not_provided"
            ),
            "imagery_asset_code": getattr(imagery, "asset_code", None),
            "imagery_acquired_at": getattr(imagery, "acquired_at", None),
            "imagery_processing_complete": bool(
                imagery
                and imagery.calibration_status == "completed"
                and imagery.correction_status == "completed"
            ),
            "review_record_count": len(source_data["reviews"]),
            "task_status": task.status,
        }

    def _write_zip(
        self,
        package_path: Path,
        task: object,
        source_data: dict,
        manifest: list[dict],
        quality_summary: dict,
    ) -> None:
        """将业务数据和报告写入 ZIP 文件。

        Args:
            package_path: ZIP 输出路径。
            task: 当前作业任务。
            source_data: 成果包源数据。
            manifest: 成果文件清单。
            quality_summary: 质量与验收摘要。

        Returns:
            None: 无返回值。
        """
        with ZipFile(package_path, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "vector/farmland_plots.geojson",
                self._build_plot_geojson(source_data["plot_rows"]),
            )
            archive.writestr(
                "statistics/area_statistics.csv",
                self._build_statistics_csv(source_data["statistics"]),
            )
            archive.writestr(
                "disasters/disaster_patches.geojson",
                self._json_text(source_data["disasters"].feature_collection),
            )
            archive.writestr(
                "field/field_verifications.geojson",
                self._build_field_geojson(source_data["field_rows"]),
            )
            archive.writestr(
                "quality/quality_issues.json",
                self._json_text(
                    [
                        {
                            "plot_code": item.plot_code,
                            "rule_code": item.rule_code,
                            "issue_type": item.issue_type,
                            "severity": item.severity,
                            "description": item.description,
                            "status": item.status,
                            "source": item.source,
                            "created_at": item.created_at,
                        }
                        for item in source_data["quality_issues"]
                    ]
                ),
            )
            archive.writestr(
                "review/review_records.json",
                self._json_text(
                    [
                        {
                            "review_level": item.review_level,
                            "action": item.action,
                            "reviewer": item.reviewer,
                            "reviewer_code": item.reviewer_code,
                            "reviewer_role": item.reviewer_role,
                            "comment": item.comment,
                            "created_at": item.created_at,
                        }
                        for item in source_data["reviews"]
                    ]
                ),
            )
            archive.writestr(
                "reports/quality_report.md",
                self._build_quality_report(task, quality_summary),
            )
            archive.writestr(
                "reports/acceptance_report.md",
                self._build_acceptance_report(task, source_data, quality_summary),
            )
            archive.writestr(
                "manifest.json",
                self._json_text(
                    {"manifest": manifest, "quality_summary": quality_summary}
                ),
            )

    @staticmethod
    def _build_plot_geojson(rows: list[object]) -> str:
        """生成最终图斑 GeoJSON。

        Args:
            rows: 图斑数据库行。

        Returns:
            str: GeoJSON 文本。
        """
        features = []
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(row.geometry),
                    "properties": {
                        "plot_code": row.plot_code,
                        "owner_village": row.owner_village,
                        "area_ha": float(row.area_ha)
                        if row.area_ha is not None
                        else None,
                        "land_class": row.land_class,
                        "crop_type": row.crop_type,
                        "planting_mode": row.planting_mode,
                        "irrigation_condition": row.irrigation_condition,
                        "interpretation_status": row.interpretation_status,
                        "version": row.version,
                    },
                }
            )
        return DeliveryService._json_text(
            {"type": "FeatureCollection", "features": features}
        )

    @staticmethod
    def _build_field_geojson(rows: list[tuple[object, str]]) -> str:
        """生成外业核查点 GeoJSON。

        Args:
            rows: 外业记录和点位几何。

        Returns:
            str: GeoJSON 文本。
        """
        features = [
            {
                "type": "Feature",
                "geometry": json.loads(geometry),
                "properties": {
                    "verification_code": item.verification_code,
                    "investigator": item.investigator,
                    "observed_land_class": item.observed_land_class,
                    "observed_crop_type": item.observed_crop_type,
                    "matched_plot_code": item.matched_plot_code,
                    "offset_distance_m": float(item.offset_distance_m)
                    if item.offset_distance_m is not None
                    else None,
                    "match_status": item.match_status,
                    "resolution_status": item.resolution_status,
                    "resolution_decision": item.resolution_decision,
                    "captured_at": item.captured_at,
                },
            }
            for item, geometry in rows
        ]
        return DeliveryService._json_text(
            {"type": "FeatureCollection", "features": features}
        )

    @staticmethod
    def _build_statistics_csv(statistics: object) -> str:
        """生成多维面积统计 CSV。

        Args:
            statistics: 面积统计响应。

        Returns:
            str: UTF-8 CSV 文本。
        """
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            ["统计维度", "分类", "图斑数", "面积(公顷)", "面积(亩)", "占比(%)"]
        )
        for dimension, items in (
            ("地类", statistics.by_land_class),
            ("作物", statistics.by_crop_type),
            ("权属村", statistics.by_village),
        ):
            for item in items:
                writer.writerow(
                    [
                        dimension,
                        item.label,
                        item.plot_count,
                        item.area_ha,
                        item.area_mu,
                        item.percentage,
                    ]
                )
        return "\ufeff" + output.getvalue()

    @staticmethod
    def _build_quality_report(task: object, summary: dict) -> str:
        """生成质量检查报告。

        Args:
            task: 当前作业任务。
            summary: 质量与验收摘要。

        Returns:
            str: Markdown 质量报告。
        """
        imagery_text = (
            f"{summary['imagery_asset_code']} / {summary['imagery_acquired_at']}"
            if summary["imagery_asset_code"]
            else "未关联可验证业务影像"
        )
        field_text = (
            f"已纳入 {summary['field_verification_count']} 条外业核查记录，"
            "待处置记录为 0。"
            if summary["field_verification_count"] > 0
            else "本成果包未包含外业核查记录，不作外业一致性结论。"
        )
        return f"""# 遥感监测成果质量检查报告

- 作业任务：{task.task_code} / {task.task_name}
- 行政区域：{task.administrative_region}
- 业务影像：{imagery_text}
- 质量得分：{summary['quality_score']}
- 最终图斑数：{summary['plot_count']}
- 质量检查覆盖：{summary['quality_checked_count']} / {summary['quality_total_count']}
- 质量门禁通过：{summary['quality_passing_count']} / {summary['quality_total_count']}
- 未关闭问题：{summary['open_issue_count']}
- 已整改问题：{summary['resolved_issue_count']}
- 外业核查记录：{summary['field_verification_count']}
- 待处置外业记录：{summary['pending_field_count']}

## 质量结论

当前任务质量门禁已覆盖全部交付图斑，所有阻断规则均已通过，
且任务已完成三级成果审核。具体逐图规则、问题整改和版本证据
以交付包内 JSON 数据为准。

{field_text}
"""

    @staticmethod
    def _build_acceptance_report(
        task: object,
        source_data: dict,
        summary: dict,
    ) -> str:
        """生成项目验收报告。

        Args:
            task: 当前作业任务。
            source_data: 成果包源数据。
            summary: 质量与验收摘要。

        Returns:
            str: Markdown 验收报告。
        """
        statistics = source_data["statistics"]
        field_text = (
            f"已提供 {summary['field_verification_count']} 条外业核查记录"
            if summary["field_verification_count"] > 0
            else "未提供外业核查记录，外业文件为空集合"
        )
        disaster_text = (
            f"已提供 {summary['disaster_patch_count']} 个灾害斑块"
            if summary["disaster_patch_count"] > 0
            else "未导入灾害模型成果，灾害文件为空集合"
        )
        return f"""# 遥感监测项目验收报告

## 基本信息

- 任务编号：{task.task_code}
- 作业单元：{task.task_name}
- 监测区域：{task.administrative_region}
- 审核状态：三级审核完成

## 工作量与成果

- 图斑数量：{summary['plot_count']} 个
- 监测面积：{statistics.total_area_ha} 公顷 / {statistics.total_area_mu} 亩
- 灾害斑块：{summary['disaster_patch_count']} 个
- 受灾面积：{summary['affected_area_ha']} 公顷
- 外业核查：{summary['field_verification_count']} 条
- 审核及操作记录：{summary['review_record_count']} 条

## 专项证据状态

- 外业核查：{field_text}
- 灾害监测：{disaster_text}
- 业务影像：{summary['imagery_asset_code'] or '未关联'}

## 验收结论

本成果包包含最终地块数据、属性、面积统计、完整质量问题清单、审核记录和质量报告。外业与灾害文件是否包含业务记录以上述专项证据状态为准，不以空集合冒充已完成成果。

文件清单与校验摘要已写入 manifest.json，可进入甲方成果交付和归档环节。
"""

    @staticmethod
    def _json_text(value: object) -> str:
        """序列化为格式化中文 JSON。

        Args:
            value: 待序列化对象。

        Returns:
            str: JSON 文本。
        """
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)

    @staticmethod
    def _calculate_sha256(path: Path) -> str:
        """计算文件 SHA-256 校验值。

        Args:
            path: 待校验文件路径。

        Returns:
            str: 十六进制 SHA-256。
        """
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
