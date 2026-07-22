"""历史影像覆盖矩阵、实体质量与问题追溯业务服务。"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_history_dao import ImageryHistoryDAO
from app.dao.rule_config_dao import RuleConfigDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import ImageryAsset, ImageryProcessingStep
from app.schemas.imagery_history import (
    ImageryCoverageCellResponse,
    ImageryHistoryAssetResponse,
    ImageryHistoryBoundaryResponse,
    ImageryHistoryOverviewResponse,
    ImageryTraceEventResponse,
)
from app.services.imagery_asset_service import ImageryAssetService
from app.services.imagery_service import ImageryService


class ImageryHistoryService:
    """生成基于真实边界、实体校验和不可变步骤证据的历史总览。"""

    def __init__(
        self,
        dao: ImageryHistoryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        rule_dao: RuleConfigDAO | None = None,
        asset_service: ImageryAssetService | None = None,
        imagery_service: ImageryService | None = None,
    ) -> None:
        """初始化历史影像服务。

        Args:
            dao: 历史影像聚合 DAO。
            workbench_dao: 项目公共 DAO。
            rule_dao: 项目规则 DAO。
            asset_service: 源影像实体校验服务。
            imagery_service: 处理步骤实体校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryHistoryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.rule_dao = rule_dao or RuleConfigDAO()
        self.asset_service = asset_service or ImageryAssetService()
        self.imagery_service = imagery_service or ImageryService()

    @staticmethod
    def _as_datetime(value: object, fallback: datetime) -> datetime:
        """把历史证据时间规范为带时区时间。

        Args:
            value: ISO 字符串、datetime 或空值。
            fallback: 无法解析时使用的时间。

        Returns:
            datetime: 带时区时间。
        """
        parsed = fallback
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                parsed = fallback
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _verify_source(self, asset: ImageryAsset) -> tuple[bool, str | None]:
        """重新校验源影像受控路径、大小、格式和 SHA-256。

        Args:
            asset: 影像资产。

        Returns:
            tuple[bool, str | None]: 是否有效及安全错误说明。
        """
        try:
            path = self.asset_service.resolve_verified_asset_path(asset)
        except ValidationException as exc:
            return False, exc.message
        if not asset.checksum_sha256:
            return False, "源影像未登记 SHA-256"
        if calculate_sha256(path) != asset.checksum_sha256:
            return False, "源影像 SHA-256 与资产记录不一致"
        return True, None

    def _verify_step(
        self,
        step: ImageryProcessingStep,
    ) -> tuple[bool, dict[str, Any], str | None]:
        """重新校验处理步骤实体和证据。

        Args:
            step: 影像处理步骤。

        Returns:
            tuple[bool, dict[str, Any], str | None]: 校验结果、证据和错误。
        """
        evidence = (step.parameters or {}).get("artifact_evidence") or {}
        try:
            resolver = self.imagery_service.resolve_verified_step_artifact_path
            _, verified_evidence = resolver(step)
        except ValidationException as exc:
            return False, evidence, exc.message
        return True, verified_evidence, None

    @staticmethod
    def _coverage_status(coverage_percent: float) -> str:
        """按真实覆盖百分比返回矩阵状态。

        Args:
            coverage_percent: 0–100 覆盖百分比。

        Returns:
            str: none、partial 或 complete。
        """
        if coverage_percent <= 0:
            return "none"
        if coverage_percent >= 99.5:
            return "complete"
        return "partial"

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
    ) -> ImageryHistoryOverviewResponse:
        """查询历史影像覆盖矩阵和处理问题追溯时间线。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。

        Returns:
            ImageryHistoryOverviewResponse: 真实覆盖、实体状态和事件时间线。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        assets = list(await self.dao.list_assets(db, project.id))
        steps = list(await self.dao.list_steps(db, [asset.id for asset in assets]))
        boundary_rows = await self.dao.list_boundaries(db, project.id)
        coverage_rows = await self.dao.list_county_coverage(db, project.id)
        rule = await self.rule_dao.get_by_project_id(db, project.id)

        boundaries = [
            ImageryHistoryBoundaryResponse(**dict(row)) for row in boundary_rows
        ]
        prefecture_count = sum(
            boundary.boundary_level == "city" for boundary in boundaries
        )
        county_count = sum(
            boundary.boundary_level == "district" for boundary in boundaries
        )
        steps_by_asset: dict[int, list[ImageryProcessingStep]] = defaultdict(list)
        for step in steps:
            steps_by_asset[step.asset_id].append(step)

        coverage_cells: list[ImageryCoverageCellResponse] = []
        coverage_by_asset: dict[
            str,
            list[ImageryCoverageCellResponse],
        ] = defaultdict(list)
        for row in coverage_rows:
            county_area_ha = float(row["county_area_ha"] or 0)
            covered_area_ha = min(
                max(float(row["covered_area_ha"] or 0), 0),
                county_area_ha,
            )
            coverage_percent = (
                covered_area_ha / county_area_ha * 100 if county_area_ha > 0 else 0
            )
            cell = ImageryCoverageCellResponse(
                asset_code=str(row["asset_code"]),
                prefecture_code=str(row["prefecture_code"]),
                prefecture_name=str(row["prefecture_name"]),
                county_code=str(row["county_code"]),
                county_name=str(row["county_name"]),
                county_area_ha=round(county_area_ha, 4),
                covered_area_ha=round(covered_area_ha, 4),
                coverage_percent=round(coverage_percent, 4),
                coverage_status=self._coverage_status(coverage_percent),
            )
            coverage_cells.append(cell)
            coverage_by_asset[cell.asset_code].append(cell)

        latest_operational_code = next(
            (
                asset.asset_code
                for asset in assets
                if asset.data_status == "operational"
            ),
            None,
        )
        trace_events: list[ImageryTraceEventResponse] = []
        asset_responses: list[ImageryHistoryAssetResponse] = []
        max_cloud = (
            float(rule.max_cloud_cover_percent)
            if rule is not None and rule.max_cloud_cover_percent is not None
            else None
        )
        for asset in assets:
            file_verified, file_error = self._verify_source(asset)
            asset_events: list[ImageryTraceEventResponse] = [
                ImageryTraceEventResponse(
                    event_code=f"{asset.asset_code}:asset_imported",
                    asset_code=asset.asset_code,
                    asset_name=asset.asset_name,
                    occurred_at=asset.created_at,
                    event_type="asset_imported",
                    severity="success" if file_verified else "warning",
                    title="影像资产入库",
                    detail=(
                        f"{asset.sensor_type} · "
                        f"{asset.processing_level or '处理级别未登记'}"
                        f" · {asset.data_status}"
                    ),
                    step_code=None,
                    evidence_uri=asset.file_uri,
                    evidence_sha256=asset.checksum_sha256,
                )
            ]
            if asset.data_status == "demo":
                asset_events.append(
                    ImageryTraceEventResponse(
                        event_code=f"{asset.asset_code}:demo_notice",
                        asset_code=asset.asset_code,
                        asset_name=asset.asset_name,
                        occurred_at=asset.created_at,
                        event_type="demo_notice",
                        severity="warning",
                        title="明确演示数据",
                        detail="该影像只用于功能联调，不计入正式业务覆盖和成果证据。",
                        step_code=None,
                        evidence_uri=asset.file_uri,
                        evidence_sha256=asset.checksum_sha256,
                    )
                )
            if not file_verified:
                asset_events.append(
                    ImageryTraceEventResponse(
                        event_code=f"{asset.asset_code}:source_file_invalid",
                        asset_code=asset.asset_code,
                        asset_name=asset.asset_name,
                        occurred_at=asset.created_at,
                        event_type="source_file_invalid",
                        severity="error",
                        title="源影像实体校验失败",
                        detail=file_error or "源影像实体不可用",
                        step_code=None,
                        evidence_uri=asset.file_uri,
                        evidence_sha256=asset.checksum_sha256,
                    )
                )
            if (
                asset.data_status == "operational"
                and max_cloud is not None
                and asset.cloud_cover is not None
                and float(asset.cloud_cover) > max_cloud
            ):
                asset_events.append(
                    ImageryTraceEventResponse(
                        event_code=f"{asset.asset_code}:cloud_threshold_exceeded",
                        asset_code=asset.asset_code,
                        asset_name=asset.asset_name,
                        occurred_at=asset.created_at,
                        event_type="cloud_threshold_exceeded",
                        severity="warning",
                        title="云量超过项目规则",
                        detail=(
                            f"实际云量 {float(asset.cloud_cover):.2f}% > "
                            f"项目上限 {max_cloud:.2f}%"
                        ),
                        step_code=None,
                        evidence_uri=asset.file_uri,
                        evidence_sha256=asset.checksum_sha256,
                    )
                )

            required_count = 0
            verified_required_count = 0
            for step in steps_by_asset.get(asset.id, []):
                if step.is_required:
                    required_count += 1
                verified, evidence, artifact_error = self._verify_step(step)
                occurred_at = step.completed_at or step.updated_at
                if step.status == "completed" and verified:
                    if step.is_required:
                        verified_required_count += 1
                    asset_events.append(
                        ImageryTraceEventResponse(
                            event_code=f"{asset.asset_code}:{step.step_code}:completed",
                            asset_code=asset.asset_code,
                            asset_name=asset.asset_name,
                            occurred_at=occurred_at,
                            event_type="step_completed",
                            severity="success",
                            title=f"{step.step_name}完成",
                            detail=(
                                f"{evidence.get('processor_name') or '受控处理器'} · "
                                f"{evidence.get('file_size_bytes') or 0} bytes"
                            ),
                            step_code=step.step_code,
                            evidence_uri=step.output_uri,
                            evidence_sha256=evidence.get("checksum_sha256"),
                        )
                    )
                elif step.status == "completed":
                    asset_events.append(
                        ImageryTraceEventResponse(
                            event_code=f"{asset.asset_code}:{step.step_code}:invalid",
                            asset_code=asset.asset_code,
                            asset_name=asset.asset_name,
                            occurred_at=occurred_at,
                            event_type="step_artifact_invalid",
                            severity="error",
                            title=f"{step.step_name}产物失效",
                            detail=artifact_error or "处理步骤实体产物不可用",
                            step_code=step.step_code,
                            evidence_uri=step.output_uri,
                            evidence_sha256=evidence.get("checksum_sha256"),
                        )
                    )
                elif step.is_required:
                    asset_events.append(
                        ImageryTraceEventResponse(
                            event_code=f"{asset.asset_code}:{step.step_code}:pending",
                            asset_code=asset.asset_code,
                            asset_name=asset.asset_name,
                            occurred_at=step.updated_at,
                            event_type="required_step_pending",
                            severity="warning",
                            title=f"{step.step_name}待处理",
                            detail=(
                                "必选步骤尚无通过实体文件、大小和 SHA-256 "
                                "复核的成果。"
                            ),
                            step_code=step.step_code,
                            evidence_uri=step.output_uri,
                            evidence_sha256=None,
                        )
                    )
                history = (step.parameters or {}).get("artifact_history") or []
                if isinstance(history, list):
                    for index, historical in enumerate(history, start=1):
                        if not isinstance(historical, dict):
                            continue
                        asset_events.append(
                            ImageryTraceEventResponse(
                                event_code=(
                                    f"{asset.asset_code}:{step.step_code}:superseded:{index}"
                                ),
                                asset_code=asset.asset_code,
                                asset_name=asset.asset_name,
                                occurred_at=self._as_datetime(
                                    historical.get("registered_at"),
                                    step.updated_at,
                                ),
                                event_type="artifact_superseded",
                                severity="info",
                                title=f"{step.step_name}历史产物已替代",
                                detail="旧实体证据保留在步骤历史中，不再作为当前成果。",
                                step_code=step.step_code,
                                evidence_uri=historical.get("output_uri"),
                                evidence_sha256=historical.get("checksum_sha256"),
                            )
                        )

            cells = coverage_by_asset.get(asset.asset_code, [])
            county_area = sum(cell.county_area_ha for cell in cells)
            covered_area = sum(cell.covered_area_ha for cell in cells)
            issue_count = sum(
                event.severity in {"warning", "error"} for event in asset_events
            )
            asset_responses.append(
                ImageryHistoryAssetResponse(
                    asset_code=asset.asset_code,
                    asset_name=asset.asset_name,
                    sensor_type=asset.sensor_type,
                    acquired_at=asset.acquired_at,
                    cloud_cover=(
                        float(asset.cloud_cover)
                        if asset.cloud_cover is not None
                        else None
                    ),
                    resolution_m=(
                        float(asset.resolution_m)
                        if asset.resolution_m is not None
                        else None
                    ),
                    processing_level=asset.processing_level,
                    data_status=asset.data_status,
                    file_verified=file_verified,
                    file_error=file_error,
                    checksum_sha256=asset.checksum_sha256,
                    crs=asset.crs,
                    required_step_count=required_count,
                    verified_required_step_count=verified_required_count,
                    processing_completion_rate=round(
                        verified_required_count / required_count * 100
                        if required_count
                        else 0,
                        2,
                    ),
                    covered_prefecture_count=len(
                        {
                            cell.prefecture_code
                            for cell in cells
                            if cell.coverage_percent > 0
                        }
                    ),
                    covered_county_count=sum(
                        cell.coverage_percent > 0 for cell in cells
                    ),
                    province_coverage_percent=round(
                        covered_area / county_area * 100 if county_area > 0 else 0,
                        6,
                    ),
                    issue_count=issue_count,
                    is_latest_operational=asset.asset_code == latest_operational_code,
                )
            )
            trace_events.extend(asset_events)

        trace_events.sort(
            key=lambda event: (event.occurred_at, event.event_code),
            reverse=True,
        )
        operational_assets = [
            asset for asset in asset_responses if asset.data_status == "operational"
        ]
        acquired_times = [asset.acquired_at for asset in asset_responses]
        return ImageryHistoryOverviewResponse(
            project_code=project_code,
            generated_at=datetime.now(UTC),
            asset_count=len(asset_responses),
            operational_asset_count=len(operational_assets),
            verified_operational_asset_count=sum(
                asset.file_verified for asset in operational_assets
            ),
            prefecture_count=prefecture_count,
            county_count=county_count,
            time_start=min(acquired_times) if acquired_times else None,
            time_end=max(acquired_times) if acquired_times else None,
            boundaries=boundaries,
            assets=asset_responses,
            coverage_cells=coverage_cells,
            trace_events=trace_events,
        )
