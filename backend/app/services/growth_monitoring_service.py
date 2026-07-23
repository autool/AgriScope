"""多时相 NDVI 长势监测来源门禁、执行、持久化和下载服务。"""

import asyncio
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal
from uuid import uuid4

import rasterio
from rasterio.errors import RasterioIOError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256, has_supported_raster_signature
from app.dao.growth_monitoring_dao import (
    GrowthMonitoringDAO,
    GrowthSourceRow,
    GrowthTaskScope,
)
from app.dao.workbench_dao import WorkbenchDAO
from app.models.growth_monitoring import (
    GrowthMonitoringEvent,
    GrowthMonitoringRun,
    GrowthMonitoringZone,
)
from app.schemas.growth_monitoring import (
    GrowthMonitoringCreateRequest,
    GrowthMonitoringOverviewResponse,
    GrowthMonitoringRunResponse,
    GrowthMonitoringSourceResponse,
    GrowthMonitoringZoneCollectionResponse,
)
from app.services.growth_monitoring_engine import (
    GrowthMonitoringEngine,
    GrowthRasterSource,
)
from app.services.imagery_service import ImageryService
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class InspectedGrowthSource:
    """来源资格响应与可选栅格引擎输入。"""

    response: GrowthMonitoringSourceResponse
    engine_source: GrowthRasterSource | None
    step_id: int | None


@dataclass(frozen=True)
class GrowthArtifactDownload:
    """已鉴权并重新校验的长势监测成果下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str
    media_type: str


class GrowthMonitoringService:
    """编排真实 NDVI 来源、任务图斑掩膜、分级成果和审计。"""

    def __init__(
        self,
        dao: GrowthMonitoringDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        imagery_service: ImageryService | None = None,
        engine: GrowthMonitoringEngine | None = None,
    ) -> None:
        """初始化长势监测服务。

        Args:
            dao: 长势监测 DAO。
            workbench_dao: 项目任务 DAO。
            user_service: 稳定用户权限服务。
            imagery_service: 影像步骤实体校验服务。
            engine: NDVI 长势分级引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or GrowthMonitoringDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.imagery_service = imagery_service or ImageryService()
        self.engine = engine or GrowthMonitoringEngine(
            max_output_pixels=settings.max_growth_monitoring_pixels,
        )
        self.storage_root = (
            Path(__file__).resolve().parents[2] / "storage" / "growth-monitoring"
        ).resolve()

    def _inspect_source(self, row: GrowthSourceRow) -> InspectedGrowthSource:
        """重新校验业务影像的波段产品实体和 NDVI 波段。

        Args:
            row: 影像资产和波段产品步骤。

        Returns:
            InspectedGrowthSource: 来源资格及可选引擎输入。
        """
        asset = row.asset
        common = {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "acquired_at": asset.acquired_at,
            "data_status": asset.data_status,
        }
        if asset.data_status != "operational":
            return InspectedGrowthSource(
                response=GrowthMonitoringSourceResponse(
                    **common,
                    source_uri=None,
                    source_size_bytes=None,
                    source_sha256=None,
                    ndvi_band_index=None,
                    eligible=False,
                    unavailable_reason="演示影像不得作为正式长势监测输入",
                ),
                engine_source=None,
                step_id=getattr(row.step, "id", None),
            )
        if row.step is None:
            return InspectedGrowthSource(
                response=GrowthMonitoringSourceResponse(
                    **common,
                    source_uri=None,
                    source_size_bytes=None,
                    source_sha256=None,
                    ndvi_band_index=None,
                    eligible=False,
                    unavailable_reason="尚未生成波段与 NDVI 实体产物",
                ),
                engine_source=None,
                step_id=None,
            )
        if row.step.status != "completed":
            return InspectedGrowthSource(
                response=GrowthMonitoringSourceResponse(
                    **common,
                    source_uri=row.step.output_uri,
                    source_size_bytes=None,
                    source_sha256=None,
                    ndvi_band_index=None,
                    eligible=False,
                    unavailable_reason="波段与 NDVI 产品步骤尚未完成",
                ),
                engine_source=None,
                step_id=row.step.id,
            )
        try:
            path, evidence = self.imagery_service.resolve_verified_step_artifact_path(
                row.step
            )
            with rasterio.open(path) as dataset:
                ndvi_band_index = self.engine.find_ndvi_band(dataset)
            source_size = int(evidence.get("file_size_bytes") or 0)
            source_sha = str(evidence.get("checksum_sha256") or "")
            if source_size <= 0 or len(source_sha) != 64:
                raise ValidationException("NDVI 实体缺少完整大小或 SHA-256 证据")
            source_uri = str(row.step.output_uri or "")
            response = GrowthMonitoringSourceResponse(
                **common,
                source_uri=source_uri,
                source_size_bytes=source_size,
                source_sha256=source_sha,
                ndvi_band_index=ndvi_band_index,
                eligible=True,
                unavailable_reason=None,
            )
            return InspectedGrowthSource(
                response=response,
                engine_source=GrowthRasterSource(
                    path=path,
                    asset_code=asset.asset_code,
                    source_uri=source_uri,
                    source_size_bytes=source_size,
                    source_sha256=source_sha,
                    ndvi_band_index=ndvi_band_index,
                ),
                step_id=row.step.id,
            )
        except (RasterioIOError, ValidationException) as exc:
            reason = (
                exc.message
                if isinstance(exc, ValidationException)
                else "NDVI 实体无法读取"
            )
            return InspectedGrowthSource(
                response=GrowthMonitoringSourceResponse(
                    **common,
                    source_uri=row.step.output_uri,
                    source_size_bytes=None,
                    source_sha256=None,
                    ndvi_band_index=None,
                    eligible=False,
                    unavailable_reason=reason,
                ),
                engine_source=None,
                step_id=row.step.id,
            )

    def _resolve_artifact(
        self,
        uri: str,
        size_bytes: int,
        checksum_sha256: str,
        artifact_type: Literal["classification", "anomalies"],
        expected_zone_count: int,
    ) -> tuple[Path, str | None]:
        """解析并复核长势监测成果的路径、签名、大小和 SHA-256。

        Args:
            uri: 受控 storage URI。
            size_bytes: 数据库登记大小。
            checksum_sha256: 数据库登记 SHA-256。
            artifact_type: classification 或 anomalies。
            expected_zone_count: GeoJSON 应包含的异常区数量。

        Returns:
            tuple[Path, str | None]: 文件路径和校验错误。
        """
        prefix = "storage://growth-monitoring/"
        if not uri.startswith(prefix):
            return self.storage_root, "长势成果 URI 不在受控目录"
        path = (self.storage_root / uri.removeprefix(prefix)).resolve()
        if not path.is_relative_to(self.storage_root) or not path.is_file():
            return path, "长势成果实体不存在"
        if path.stat().st_size != size_bytes:
            return path, "长势成果大小与登记值不一致"
        if calculate_sha256(path) != checksum_sha256:
            return path, "长势成果 SHA-256 与登记值不一致"
        if artifact_type == "classification":
            if not has_supported_raster_signature(path):
                return path, "长势分级 GeoTIFF 格式签名不合法"
            try:
                with rasterio.open(path) as dataset:
                    if dataset.count != 1 or dataset.dtypes[0] != "uint8":
                        return path, "长势分级栅格结构与登记规则不一致"
                    if dataset.descriptions[0] != "growth_class":
                        return path, "长势分级栅格缺少明确波段描述"
            except RasterioIOError:
                return path, "长势分级 GeoTIFF 无法重新打开"
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return path, "长势异常区 GeoJSON 无法解析"
            features = payload.get("features") if isinstance(payload, dict) else None
            if payload.get("type") != "FeatureCollection" or not isinstance(
                features,
                list,
            ):
                return path, "长势异常区文件不是标准 FeatureCollection"
            if len(features) != expected_zone_count:
                return path, "长势异常区实体数量与数据库不一致"
        return path, None

    def verify_run_artifacts(
        self,
        run: GrowthMonitoringRun,
    ) -> tuple[Path, Path]:
        """重新校验一个长势监测任务的两个物理成果。

        Args:
            run: 长势监测任务。

        Returns:
            tuple[Path, Path]: 分级 GeoTIFF 和异常区 GeoJSON 路径。
        """
        classification_path, classification_error = self._resolve_artifact(
            run.classification_uri,
            run.classification_size_bytes,
            run.classification_sha256,
            "classification",
            run.anomaly_zone_count,
        )
        if classification_error:
            raise ValidationException(classification_error)
        anomaly_path, anomaly_error = self._resolve_artifact(
            run.anomaly_uri,
            run.anomaly_size_bytes,
            run.anomaly_sha256,
            "anomalies",
            run.anomaly_zone_count,
        )
        if anomaly_error:
            raise ValidationException(anomaly_error)
        return classification_path, anomaly_path

    def _verify_source_step_snapshot(
        self,
        step: object,
        expected_uri: str,
        expected_size_bytes: int,
        expected_sha256: str,
        expected_ndvi_band_index: int,
        period_label: str,
    ) -> None:
        """重新校验一个长势来源步骤及其物理 NDVI 实体。

        Args:
            step: 当前数据库中的影像处理步骤。
            expected_uri: 长势任务快照登记的来源 URI。
            expected_size_bytes: 长势任务快照登记的实体大小。
            expected_sha256: 长势任务快照登记的 SHA-256。
            expected_ndvi_band_index: 长势任务快照登记的 NDVI 波段。
            period_label: 基准期或监测期标签。

        Returns:
            None: 校验通过时无返回值。
        """
        if getattr(step, "status", None) != "completed":
            raise ValidationException(f"{period_label} band_products 已不再是完成状态")
        if getattr(step, "output_uri", None) != expected_uri:
            raise ValidationException(f"{period_label} NDVI 来源 URI 已变化")
        path, evidence = self.imagery_service.resolve_verified_step_artifact_path(step)
        actual_size = int(evidence.get("file_size_bytes") or 0)
        actual_sha256 = str(evidence.get("checksum_sha256") or "")
        if actual_size != expected_size_bytes:
            raise ValidationException(f"{period_label} NDVI 来源大小已变化")
        if actual_sha256 != expected_sha256:
            raise ValidationException(f"{period_label} NDVI 来源 SHA-256 已变化")
        try:
            with rasterio.open(path) as dataset:
                actual_ndvi_band = self.engine.find_ndvi_band(dataset)
        except RasterioIOError as exc:
            raise ValidationException(f"{period_label} NDVI 来源无法重新打开") from exc
        if actual_ndvi_band != expected_ndvi_band_index:
            raise ValidationException(f"{period_label} NDVI 波段位置已变化")

    async def verify_run_sources(
        self,
        db: AsyncSession,
        run: GrowthMonitoringRun,
    ) -> None:
        """重新读取并校验长势任务引用的两个来源步骤。

        Args:
            db: 异步数据库会话。
            run: 长势监测任务。

        Returns:
            None: 两期来源均与任务快照一致时无返回值。
        """
        steps = await self.dao.get_source_steps(
            db,
            [run.baseline_step_id, run.current_step_id],
        )
        step_by_id = {step.id: step for step in steps}
        baseline_step = step_by_id.get(run.baseline_step_id)
        current_step = step_by_id.get(run.current_step_id)
        if baseline_step is None or current_step is None:
            raise ValidationException("长势监测引用的 band_products 步骤已不存在")
        baseline_manifest = (run.manifest or {}).get("baseline", {})
        current_manifest = (run.manifest or {}).get("current", {})
        await asyncio.to_thread(
            self._verify_source_step_snapshot,
            baseline_step,
            run.baseline_source_uri,
            run.baseline_source_size_bytes,
            run.baseline_source_sha256,
            int(baseline_manifest.get("ndvi_band_index") or 0),
            "基准期",
        )
        await asyncio.to_thread(
            self._verify_source_step_snapshot,
            current_step,
            run.current_source_uri,
            run.current_source_size_bytes,
            run.current_source_sha256,
            int(current_manifest.get("ndvi_band_index") or 0),
            "监测期",
        )

    async def verify_run_for_delivery(
        self,
        db: AsyncSession,
        run: GrowthMonitoringRun,
    ) -> tuple[Path, Path]:
        """交付前重新校验两期来源和两个长势成果实体。

        Args:
            db: 异步数据库会话。
            run: 待纳入交付包的长势任务。

        Returns:
            tuple[Path, Path]: 分级 GeoTIFF 与异常区 GeoJSON 路径。
        """
        await self.verify_run_sources(db, run)
        return await asyncio.to_thread(self.verify_run_artifacts, run)

    @staticmethod
    def _source_snapshot_error(
        run: GrowthMonitoringRun,
        inspected_by_step_id: dict[int, InspectedGrowthSource],
    ) -> str | None:
        """比较总览已复核来源与长势任务来源快照。

        Args:
            run: 长势监测任务。
            inspected_by_step_id: 当前来源步骤资格结果。

        Returns:
            str | None: 来源变化原因；一致时为空。
        """
        manifest = run.manifest or {}
        pairs = (
            (
                "基准期",
                run.baseline_step_id,
                run.baseline_source_uri,
                run.baseline_source_size_bytes,
                run.baseline_source_sha256,
                int((manifest.get("baseline") or {}).get("ndvi_band_index") or 0),
            ),
            (
                "监测期",
                run.current_step_id,
                run.current_source_uri,
                run.current_source_size_bytes,
                run.current_source_sha256,
                int((manifest.get("current") or {}).get("ndvi_band_index") or 0),
            ),
        )
        for label, step_id, uri, size_bytes, sha256, ndvi_band_index in pairs:
            inspected = inspected_by_step_id.get(step_id)
            if inspected is None or not inspected.response.eligible:
                return f"{label} NDVI 来源当前不可验证"
            if inspected.response.source_uri != uri:
                return f"{label} NDVI 来源 URI 已变化"
            if inspected.response.source_size_bytes != size_bytes:
                return f"{label} NDVI 来源大小已变化"
            if inspected.response.source_sha256 != sha256:
                return f"{label} NDVI 来源 SHA-256 已变化"
            if inspected.response.ndvi_band_index != ndvi_band_index:
                return f"{label} NDVI 波段位置已变化"
        return None

    def _run_response(
        self,
        run: GrowthMonitoringRun,
        current_scope: GrowthTaskScope | None,
        source_error: str | None = None,
    ) -> GrowthMonitoringRunResponse:
        """组装包含实体校验和任务快照状态的任务响应。

        Args:
            run: 长势监测任务。
            current_scope: 当前任务耕地图斑范围快照。
            source_error: 当前两期来源与任务快照不一致原因。

        Returns:
            GrowthMonitoringRunResponse: 长势监测任务响应。
        """
        _, classification_error = self._resolve_artifact(
            run.classification_uri,
            run.classification_size_bytes,
            run.classification_sha256,
            "classification",
            run.anomaly_zone_count,
        )
        _, anomaly_error = self._resolve_artifact(
            run.anomaly_uri,
            run.anomaly_size_bytes,
            run.anomaly_sha256,
            "anomalies",
            run.anomaly_zone_count,
        )
        stale_reason = None
        if current_scope is None:
            stale_reason = "当前任务已没有可监测耕地图斑"
        elif current_scope.plot_count != run.task_plot_count:
            stale_reason = "任务耕地图斑数量已变化"
        elif current_scope.task_updated_at != run.task_updated_at:
            stale_reason = "任务数据在长势监测后发生变化"
        artifact_error = source_error or classification_error or anomaly_error
        return GrowthMonitoringRunResponse(
            run_code=run.run_code,
            run_name=run.run_name,
            baseline_asset_code=run.baseline_asset_code,
            baseline_asset_name=run.baseline_asset_name,
            baseline_acquired_at=run.baseline_acquired_at,
            current_asset_code=run.current_asset_code,
            current_asset_name=run.current_asset_name,
            current_acquired_at=run.current_acquired_at,
            poor_delta_threshold=float(run.poor_delta_threshold),
            good_delta_threshold=float(run.good_delta_threshold),
            minimum_zone_area_ha=float(run.minimum_zone_area_ha),
            minimum_spatial_coverage_ratio=float(
                run.minimum_spatial_coverage_ratio
            ),
            minimum_valid_pixel_ratio=float(run.minimum_valid_pixel_ratio),
            algorithm_code=run.algorithm_code,
            algorithm_version=run.algorithm_version,
            task_plot_count=run.task_plot_count,
            task_updated_at=run.task_updated_at,
            output_crs=run.output_crs,
            output_resolution_x=float(run.output_resolution_x),
            output_resolution_y=float(run.output_resolution_y),
            raster_width=run.raster_width,
            raster_height=run.raster_height,
            bounds_wgs84=list(run.bounds_wgs84),
            task_farmland_area_ha=float(run.task_farmland_area_ha),
            common_footprint_farmland_area_ha=float(
                run.common_footprint_farmland_area_ha
            ),
            spatial_coverage_ratio=float(run.spatial_coverage_ratio),
            common_footprint_mask_pixel_count=(
                run.common_footprint_mask_pixel_count
            ),
            valid_pixel_count=run.valid_pixel_count,
            valid_pixel_ratio=float(run.valid_pixel_ratio),
            poor_pixel_count=run.poor_pixel_count,
            normal_pixel_count=run.normal_pixel_count,
            good_pixel_count=run.good_pixel_count,
            anomaly_zone_count=run.anomaly_zone_count,
            anomaly_area_ha=float(run.anomaly_area_ha),
            classification_filename=run.classification_filename,
            classification_size_bytes=run.classification_size_bytes,
            classification_sha256=run.classification_sha256,
            anomaly_filename=run.anomaly_filename,
            anomaly_size_bytes=run.anomaly_size_bytes,
            anomaly_sha256=run.anomaly_sha256,
            manifest=run.manifest or {},
            created_by=run.created_by,
            created_by_code=run.created_by_code,
            created_by_role=run.created_by_role,
            comment=run.comment,
            created_at=run.created_at,
            task_snapshot_current=stale_reason is None,
            stale_reason=stale_reason,
            classification_verified=classification_error is None,
            anomaly_verified=anomaly_error is None,
            source_verified=source_error is None,
            source_error=source_error,
            artifact_error=artifact_error,
            classification_download_url=(
                f"/api/v1/growth-monitoring/runs/{run.run_code}/download"
                "?artifact=classification"
                if classification_error is None and source_error is None
                else None
            ),
            anomaly_download_url=(
                f"/api/v1/growth-monitoring/runs/{run.run_code}/download"
                "?artifact=anomalies"
                if anomaly_error is None and source_error is None
                else None
            ),
        )

    async def _zone_collection(
        self,
        db: AsyncSession,
        run: GrowthMonitoringRun,
    ) -> GrowthMonitoringZoneCollectionResponse:
        """构造指定任务的长势转差异常区 GeoJSON。

        Args:
            db: 异步数据库会话。
            run: 长势监测任务。

        Returns:
            GrowthMonitoringZoneCollectionResponse: 异常区集合。
        """
        rows = await self.dao.list_zone_rows(db, run.id)
        features = []
        for row in rows:
            zone = row[GrowthMonitoringZone]
            features.append(
                {
                    "type": "Feature",
                    "geometry": json.loads(row["geometry"]),
                    "properties": {
                        "zone_code": zone.zone_code,
                        "run_code": run.run_code,
                        "growth_level": "差",
                        "area_ha": float(zone.area_ha),
                        "baseline_ndvi_mean": float(zone.baseline_ndvi_mean),
                        "current_ndvi_mean": float(zone.current_ndvi_mean),
                        "ndvi_delta_mean": float(zone.ndvi_delta_mean),
                    },
                }
            )
        return GrowthMonitoringZoneCollectionResponse(
            run_code=run.run_code,
            zone_count=len(features),
            anomaly_area_ha=round(
                sum(item["properties"]["area_ha"] for item in features),
                4,
            ),
            feature_collection={"type": "FeatureCollection", "features": features},
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        operator_code: str,
        selected_run_code: str | None = None,
    ) -> GrowthMonitoringOverviewResponse:
        """查询来源资格、历史任务和选中异常区。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            operator_code: 当前稳定用户编码。
            selected_run_code: 可选历史任务编号。

        Returns:
            GrowthMonitoringOverviewResponse: 长势监测总览。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"未找到当前项目任务 {task_code}")
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "view_growth_monitoring",
        )
        source_rows = await self.dao.list_source_rows(db, project.id)
        inspected_sources = [self._inspect_source(row) for row in source_rows]
        inspected_by_step_id = {
            item.step_id: item
            for item in inspected_sources
            if item.step_id is not None
        }
        runs = list(await self.dao.list_runs(db, task.id))
        current_scope = await self.dao.get_task_scope(db, task.id)
        selected = None
        if selected_run_code:
            selected = next(
                (item for item in runs if item.run_code == selected_run_code),
                None,
            )
            if selected is None:
                raise NotFoundException(f"未找到当前任务长势监测 {selected_run_code}")
        elif runs:
            selected = runs[0]
        zones = (
            await self._zone_collection(db, selected)
            if selected is not None
            else GrowthMonitoringZoneCollectionResponse(
                run_code="",
                zone_count=0,
                anomaly_area_ha=0,
                feature_collection={"type": "FeatureCollection", "features": []},
            )
        )
        return GrowthMonitoringOverviewResponse(
            project_code=project_code,
            task_code=task_code,
            max_output_pixels=self.engine.max_output_pixels,
            sources=[item.response for item in inspected_sources],
            runs=[
                self._run_response(
                    item,
                    current_scope,
                    self._source_snapshot_error(item, inspected_by_step_id),
                )
                for item in runs
            ],
            selected_run_code=selected.run_code if selected else None,
            feature_collection=zones.feature_collection,
        )

    async def create_run(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: GrowthMonitoringCreateRequest,
    ) -> GrowthMonitoringRunResponse:
        """执行真实多时相 NDVI 长势分级并保存物理证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            request: 两期影像、阈值、面积门槛和稳定用户。

        Returns:
            GrowthMonitoringRunResponse: 已完成的长势监测任务。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"未找到当前项目任务 {task_code}")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "generate_growth_monitoring",
        )
        if await self.dao.get_run(db, project.id, request.run_code) is not None:
            raise ValidationException(f"长势监测任务 {request.run_code} 已存在")
        baseline_row = await self.dao.get_source_row(
            db,
            project.id,
            request.baseline_asset_code,
        )
        current_row = await self.dao.get_source_row(
            db,
            project.id,
            request.current_asset_code,
        )
        if baseline_row is None or current_row is None:
            raise ValidationException("长势监测输入影像不存在或不属于当前项目")
        baseline = self._inspect_source(baseline_row)
        current = self._inspect_source(current_row)
        if not baseline.response.eligible or baseline.engine_source is None:
            raise ValidationException(
                baseline.response.unavailable_reason or "基准期 NDVI 来源不可用"
            )
        if not current.response.eligible or current.engine_source is None:
            raise ValidationException(
                current.response.unavailable_reason or "监测期 NDVI 来源不可用"
            )
        if baseline_row.asset.acquired_at >= current_row.asset.acquired_at:
            raise ValidationException("基准期影像采集时间必须早于监测期影像")
        task_scope = await self.dao.get_task_scope(db, task.id)
        if task_scope is None or task_scope.plot_count <= 0:
            raise ValidationException("当前任务没有可用于作物长势监测的有效耕地图斑")
        coverage_scope = await self.dao.get_coverage_scope(
            db,
            task.id,
            baseline_row.asset.id,
            current_row.asset.id,
        )
        if coverage_scope is None:
            raise ValidationException("两期影像真实足迹没有共同覆盖当前任务耕地")
        if (
            coverage_scope.spatial_coverage_ratio
            < request.minimum_spatial_coverage_ratio
        ):
            raise ValidationException(
                "两期影像足迹对完整任务耕地的空间覆盖率 "
                f"{coverage_scope.spatial_coverage_ratio:.4f} 低于门槛 "
                f"{request.minimum_spatial_coverage_ratio:.4f}"
            )
        common_coverage_geometry = json.loads(coverage_scope.geometry_json)
        run_dir = Path("runs") / request.run_code
        classification_relative = run_dir / f"{uuid4().hex}-growth-class.tif"
        anomaly_relative = run_dir / f"{uuid4().hex}-anomalies.geojson"
        classification_path = self.storage_root / classification_relative
        anomaly_path = self.storage_root / anomaly_relative
        result = await asyncio.to_thread(
            self.engine.execute,
            baseline.engine_source,
            current.engine_source,
            common_coverage_geometry,
            classification_path,
            request.poor_delta_threshold,
            request.good_delta_threshold,
            request.minimum_valid_pixel_ratio,
            request.run_code,
        )
        classification_size = classification_path.stat().st_size
        classification_sha = calculate_sha256(classification_path)
        classification_uri = (
            f"storage://growth-monitoring/{classification_relative.as_posix()}"
        )
        anomaly_uri = f"storage://growth-monitoring/{anomaly_relative.as_posix()}"
        committed = False
        try:
            prepared_zones: list[dict[str, object]] = []
            anomaly_area = 0.0
            for raw_zone in result.raw_zones:
                analyzed = await self.dao.analyze_clipped_zone(
                    db,
                    task.id,
                    json.dumps(raw_zone.geometry, ensure_ascii=False),
                    request.minimum_zone_area_ha,
                )
                if analyzed is None:
                    continue
                zone_number = len(prepared_zones) + 1
                if zone_number > 500:
                    raise ValidationException("长势异常区超过单任务 500 个上限")
                area_ha = float(analyzed["area_ha"])
                zone_code = f"{request.run_code}-Z{zone_number:04d}"
                prepared_zones.append(
                    {
                        "zone_code": zone_code,
                        "geometry_json": str(analyzed["geometry_json"]),
                        "area_ha": area_ha,
                        "baseline_mean": raw_zone.baseline_mean,
                        "current_mean": raw_zone.current_mean,
                        "delta_mean": raw_zone.delta_mean,
                    }
                )
                anomaly_area += area_ha
            feature_collection = {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": json.loads(str(item["geometry_json"])),
                        "properties": {
                            "zone_code": item["zone_code"],
                            "run_code": request.run_code,
                            "growth_level": "差",
                            "area_ha": round(float(item["area_ha"]), 4),
                            "baseline_ndvi_mean": round(
                                float(item["baseline_mean"]),
                                5,
                            ),
                            "current_ndvi_mean": round(
                                float(item["current_mean"]),
                                5,
                            ),
                            "ndvi_delta_mean": round(
                                float(item["delta_mean"]),
                                5,
                            ),
                        },
                    }
                    for item in prepared_zones
                ],
            }
            anomaly_content = (
                json.dumps(
                    feature_collection,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
            anomaly_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_anomaly = anomaly_path.with_name(
                f".{anomaly_path.name}-{uuid4().hex}.tmp"
            )
            try:
                temporary_anomaly.write_bytes(anomaly_content)
                os.replace(temporary_anomaly, anomaly_path)
            finally:
                temporary_anomaly.unlink(missing_ok=True)
            anomaly_size = anomaly_path.stat().st_size
            anomaly_sha = calculate_sha256(anomaly_path)
            manifest = {
                **result.manifest,
                "baseline": {
                    "asset_code": baseline_row.asset.asset_code,
                    "acquired_at": baseline_row.asset.acquired_at.isoformat(),
                    "source_uri": baseline.engine_source.source_uri,
                    "source_size_bytes": baseline.engine_source.source_size_bytes,
                    "source_sha256": baseline.engine_source.source_sha256,
                    "ndvi_band_index": baseline.engine_source.ndvi_band_index,
                },
                "current": {
                    "asset_code": current_row.asset.asset_code,
                    "acquired_at": current_row.asset.acquired_at.isoformat(),
                    "source_uri": current.engine_source.source_uri,
                    "source_size_bytes": current.engine_source.source_size_bytes,
                    "source_sha256": current.engine_source.source_sha256,
                    "ndvi_band_index": current.engine_source.ndvi_band_index,
                },
                "task_scope": {
                    "task_code": task.task_code,
                    "farmland_plot_count": task_scope.plot_count,
                    "task_updated_at": task_scope.task_updated_at.isoformat(),
                    "task_farmland_area_ha": round(
                        coverage_scope.task_farmland_area_ha,
                        6,
                    ),
                    "common_footprint_farmland_area_ha": round(
                        coverage_scope.common_footprint_farmland_area_ha,
                        6,
                    ),
                    "spatial_coverage_ratio": (
                        coverage_scope.spatial_coverage_ratio
                    ),
                    "minimum_spatial_coverage_ratio": (
                        request.minimum_spatial_coverage_ratio
                    ),
                    "minimum_valid_pixel_ratio": (
                        request.minimum_valid_pixel_ratio
                    ),
                },
                "minimum_zone_area_ha": request.minimum_zone_area_ha,
                "accepted_anomaly_zone_count": len(prepared_zones),
                "accepted_anomaly_area_ha": round(anomaly_area, 4),
                "classification_artifact": {
                    "uri": classification_uri,
                    "size_bytes": classification_size,
                    "sha256": classification_sha,
                },
                "anomaly_artifact": {
                    "uri": anomaly_uri,
                    "size_bytes": anomaly_size,
                    "sha256": anomaly_sha,
                },
            }
            run = GrowthMonitoringRun(
                project_id=project.id,
                task_id=task.id,
                run_code=request.run_code,
                run_name=request.run_name,
                baseline_asset_id=baseline_row.asset.id,
                baseline_asset_code=baseline_row.asset.asset_code,
                baseline_asset_name=baseline_row.asset.asset_name,
                baseline_acquired_at=baseline_row.asset.acquired_at,
                baseline_step_id=int(baseline.step_id or 0),
                baseline_source_uri=baseline.engine_source.source_uri,
                baseline_source_size_bytes=baseline.engine_source.source_size_bytes,
                baseline_source_sha256=baseline.engine_source.source_sha256,
                current_asset_id=current_row.asset.id,
                current_asset_code=current_row.asset.asset_code,
                current_asset_name=current_row.asset.asset_name,
                current_acquired_at=current_row.asset.acquired_at,
                current_step_id=int(current.step_id or 0),
                current_source_uri=current.engine_source.source_uri,
                current_source_size_bytes=current.engine_source.source_size_bytes,
                current_source_sha256=current.engine_source.source_sha256,
                poor_delta_threshold=Decimal(str(request.poor_delta_threshold)),
                good_delta_threshold=Decimal(str(request.good_delta_threshold)),
                minimum_zone_area_ha=Decimal(str(request.minimum_zone_area_ha)),
                minimum_spatial_coverage_ratio=Decimal(
                    str(request.minimum_spatial_coverage_ratio)
                ),
                minimum_valid_pixel_ratio=Decimal(
                    str(request.minimum_valid_pixel_ratio)
                ),
                algorithm_code="ndvi_delta_common_footprint",
                algorithm_version=self.engine.processor_version,
                task_plot_count=task_scope.plot_count,
                task_updated_at=task_scope.task_updated_at,
                output_crs=result.crs,
                output_resolution_x=Decimal(str(result.resolution_x)),
                output_resolution_y=Decimal(str(result.resolution_y)),
                raster_width=result.width,
                raster_height=result.height,
                bounds_wgs84=result.bounds_wgs84,
                task_farmland_area_ha=Decimal(
                    str(coverage_scope.task_farmland_area_ha)
                ),
                common_footprint_farmland_area_ha=Decimal(
                    str(coverage_scope.common_footprint_farmland_area_ha)
                ),
                spatial_coverage_ratio=Decimal(
                    str(coverage_scope.spatial_coverage_ratio)
                ),
                common_footprint_mask_pixel_count=(
                    result.common_footprint_mask_pixel_count
                ),
                valid_pixel_count=result.valid_pixel_count,
                valid_pixel_ratio=Decimal(str(result.valid_pixel_ratio)),
                poor_pixel_count=result.poor_pixel_count,
                normal_pixel_count=result.normal_pixel_count,
                good_pixel_count=result.good_pixel_count,
                anomaly_zone_count=len(prepared_zones),
                anomaly_area_ha=Decimal(str(round(anomaly_area, 4))),
                classification_uri=classification_uri,
                classification_filename=f"{request.run_code}-growth-class.tif",
                classification_size_bytes=classification_size,
                classification_sha256=classification_sha,
                anomaly_uri=anomaly_uri,
                anomaly_filename=f"{request.run_code}-anomalies.geojson",
                anomaly_size_bytes=anomaly_size,
                anomaly_sha256=anomaly_sha,
                manifest=manifest,
                created_by=operator.display_name,
                created_by_code=operator.user_code,
                created_by_role=operator.role_code,
                comment=request.comment,
            )
            run = await self.dao.add_run(db, run)
            for item in prepared_zones:
                await self.dao.insert_zone(
                    db,
                    run.id,
                    str(item["zone_code"]),
                    str(item["geometry_json"]),
                    float(item["area_ha"]),
                    float(item["baseline_mean"]),
                    float(item["current_mean"]),
                    float(item["delta_mean"]),
                )
            await self.dao.add_event(
                db,
                GrowthMonitoringEvent(
                    project_id=project.id,
                    run_id=run.id,
                    event_type="growth_monitoring_completed",
                    actor=operator.display_name,
                    actor_code=operator.user_code,
                    actor_role=operator.role_code,
                    detail=manifest,
                    comment=request.comment,
                ),
            )
            await db.commit()
            committed = True
            await db.refresh(run)
        except (
            IntegrityError,
            SQLAlchemyError,
            ValidationException,
            OSError,
            RuntimeError,
        ):
            await db.rollback()
            raise
        finally:
            if not committed:
                classification_path.unlink(missing_ok=True)
                anomaly_path.unlink(missing_ok=True)
        return self._run_response(run, task_scope)

    async def get_zones(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
        operator_code: str,
    ) -> GrowthMonitoringZoneCollectionResponse:
        """鉴权并查询指定长势监测任务异常区。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 长势监测任务编号。
            operator_code: 当前稳定用户编码。

        Returns:
            GrowthMonitoringZoneCollectionResponse: 异常区 GeoJSON。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"未找到当前项目任务 {task_code}")
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "view_growth_monitoring",
        )
        run = await self.dao.get_run(db, project.id, run_code)
        if run is None or run.task_id != task.id:
            raise NotFoundException(f"未找到当前任务长势监测 {run_code}")
        return await self._zone_collection(db, run)

    async def get_download(
        self,
        db: AsyncSession,
        project_code: str,
        run_code: str,
        artifact: Literal["classification", "anomalies"],
        operator_code: str,
    ) -> GrowthArtifactDownload:
        """授权并重新校验长势监测物理成果后返回下载信息。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            run_code: 长势监测任务编号。
            artifact: classification 或 anomalies。
            operator_code: 下载人稳定编码。

        Returns:
            GrowthArtifactDownload: 受控下载信息。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "download_growth_monitoring",
        )
        run = await self.dao.get_run(db, project.id, run_code)
        if run is None:
            raise NotFoundException(f"未找到长势监测任务 {run_code}")
        await self.verify_run_sources(db, run)
        classification_path, anomaly_path = await asyncio.to_thread(
            self.verify_run_artifacts,
            run,
        )
        if artifact == "classification":
            download = GrowthArtifactDownload(
                classification_path,
                run.classification_filename,
                run.classification_sha256,
                "image/tiff",
            )
        else:
            download = GrowthArtifactDownload(
                anomaly_path,
                run.anomaly_filename,
                run.anomaly_sha256,
                "application/geo+json",
            )
        await self.dao.add_event(
            db,
            GrowthMonitoringEvent(
                project_id=project.id,
                run_id=run.id,
                event_type=f"growth_{artifact}_downloaded",
                actor=operator.display_name,
                actor_code=operator.user_code,
                actor_role=operator.role_code,
                detail={
                    "artifact": artifact,
                    "checksum_sha256": download.checksum_sha256,
                },
                comment="下载前已重新校验长势监测实体成果",
            ),
        )
        await db.commit()
        return download
