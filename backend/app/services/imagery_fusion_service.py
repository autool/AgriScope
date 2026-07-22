"""全色融合输入门禁、质量验收、持久化和下载业务服务。"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import rasterio
from rasterio.errors import RasterioIOError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256, has_supported_raster_signature
from app.dao.imagery_fusion_dao import ImageryFusionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.imagery_fusion import ImageryFusionEvent, ImageryFusionJob
from app.models.workbench import ImageryAsset
from app.schemas.imagery_fusion import (
    ImageryFusionCreateRequest,
    ImageryFusionJobResponse,
    ImageryFusionOverviewResponse,
    ImageryFusionSourceResponse,
)
from app.services.imagery_asset_service import ImageryAssetService
from app.services.imagery_fusion_engine import FusionSource, ImageryFusionEngine
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class FusionDownload:
    """已重新校验的融合成果下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


@dataclass(frozen=True)
class InspectedFusionSource:
    """一个经过实体、结构、标度和产品身份检查的融合来源。"""

    response: ImageryFusionSourceResponse
    engine_source: FusionSource | None


class ImageryFusionService:
    """编排真实多光谱/全色来源、融合执行和不可变审计。"""

    def __init__(
        self,
        dao: ImageryFusionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        asset_service: ImageryAssetService | None = None,
        engine: ImageryFusionEngine | None = None,
    ) -> None:
        """初始化全色融合服务。

        Args:
            dao: 融合 DAO。
            workbench_dao: 项目任务 DAO。
            user_service: 稳定用户能力服务。
            asset_service: 源影像实体校验服务。
            engine: 分块融合引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryFusionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.asset_service = asset_service or ImageryAssetService()
        self.engine = engine or ImageryFusionEngine(
            max_output_pixels=settings.max_imagery_fusion_pixels
        )
        self.storage_root = (
            Path(__file__).resolve().parents[2] / "storage" / "imagery-fusion"
        ).resolve()

    def _inspect_source(self, asset: ImageryAsset) -> InspectedFusionSource:
        """重新校验资产文件、SHA、栅格结构和融合资格。

        Args:
            asset: 项目影像资产。

        Returns:
            InspectedFusionSource: API 资格与可选引擎输入。
        """
        common = {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "sensor_type": asset.sensor_type,
            "acquired_at": asset.acquired_at,
            "data_status": asset.data_status,
            "source_uri": asset.file_uri,
            "source_size_bytes": asset.file_size_bytes,
            "source_sha256": asset.checksum_sha256,
        }
        try:
            path = self.asset_service.resolve_verified_asset_path(asset)
            if not asset.checksum_sha256:
                raise ValidationException("源影像未登记 SHA-256")
            if calculate_sha256(path) != asset.checksum_sha256:
                raise ValidationException("源影像 SHA-256 与资产记录不一致")
            with rasterio.open(path) as dataset:
                if dataset.crs is None:
                    raise ValidationException("融合来源缺少 CRS")
                tags = dataset.tags()
                calibration_applied = str(
                    tags.get("RADIOMETRIC_CALIBRATION_APPLIED")
                    or tags.get("SOURCE_SCALE_APPLIED")
                    or ""
                ).lower() == "true"
                reflectance_quantity = (
                    tags.get("REFLECTANCE_QUANTITY")
                    or tags.get("RADIOMETRIC_QUANTITY")
                )
                product_identity = (
                    tags.get("SOURCE_PRODUCT_URI")
                    or tags.get("STAC_ITEM_ID")
                    or tags.get("LANDSAT_PRODUCT_ID")
                )
                operational = asset.data_status == "operational"
                ms_reason = None
                pan_reason = None
                if not operational:
                    ms_reason = pan_reason = "演示影像不能作为正式融合输入"
                elif not calibration_applied or not reflectance_quantity:
                    ms_reason = pan_reason = "缺少可验证辐射定标和反射率数量标签"
                elif not product_identity:
                    ms_reason = pan_reason = "缺少同景产品身份标签"
                elif dataset.count < 3:
                    ms_reason = "多光谱来源至少需要三个波段"
                if pan_reason is None and dataset.count != 1:
                    pan_reason = "全色来源必须是单波段实体"
                response = ImageryFusionSourceResponse(
                    **common,
                    source_crs=dataset.crs.to_string(),
                    source_width=dataset.width,
                    source_height=dataset.height,
                    source_band_count=dataset.count,
                    resolution_x=abs(float(dataset.res[0])),
                    resolution_y=abs(float(dataset.res[1])),
                    band_descriptions=list(dataset.descriptions),
                    product_identity=product_identity,
                    reflectance_quantity=reflectance_quantity,
                    radiometric_calibration_applied=calibration_applied,
                    multispectral_eligible=ms_reason is None,
                    multispectral_reason=ms_reason,
                    panchromatic_eligible=pan_reason is None,
                    panchromatic_reason=pan_reason,
                )
            engine_source = FusionSource(
                path=path,
                asset_code=asset.asset_code,
                source_uri=asset.file_uri or "",
                source_size_bytes=asset.file_size_bytes or 0,
                source_sha256=asset.checksum_sha256,
            )
            return InspectedFusionSource(response=response, engine_source=engine_source)
        except (RasterioIOError, ValidationException) as exc:
            reason = (
                exc.message
                if isinstance(exc, ValidationException)
                else "实体栅格无法读取"
            )
            return InspectedFusionSource(
                response=ImageryFusionSourceResponse(
                    **common,
                    source_crs=asset.crs,
                    source_width=asset.raster_width,
                    source_height=asset.raster_height,
                    source_band_count=asset.band_count,
                    resolution_x=None,
                    resolution_y=None,
                    band_descriptions=[],
                    product_identity=None,
                    reflectance_quantity=None,
                    radiometric_calibration_applied=False,
                    multispectral_eligible=False,
                    multispectral_reason=reason,
                    panchromatic_eligible=False,
                    panchromatic_reason=reason,
                ),
                engine_source=None,
            )

    def _resolve_output(self, job: ImageryFusionJob) -> tuple[Path, str | None]:
        """解析并校验融合输出受控路径、签名、大小和 SHA-256。

        Args:
            job: 融合任务。

        Returns:
            tuple[Path, str | None]: 输出路径和错误；通过时错误为空。
        """
        prefix = "storage://imagery-fusion/"
        if not job.output_uri.startswith(prefix):
            return self.storage_root, "融合成果 URI 不在受控目录"
        path = (self.storage_root / job.output_uri.removeprefix(prefix)).resolve()
        if not path.is_relative_to(self.storage_root) or not path.is_file():
            return path, "融合成果实体不存在"
        if not has_supported_raster_signature(path):
            return path, "融合成果格式签名不合法"
        if path.stat().st_size != job.file_size_bytes:
            return path, "融合成果大小与登记值不一致"
        if calculate_sha256(path) != job.checksum_sha256:
            return path, "融合成果 SHA-256 与登记值不一致"
        return path, None

    def _job_response(self, job: ImageryFusionJob) -> ImageryFusionJobResponse:
        """组装带实体复核状态的融合任务响应。

        Args:
            job: 融合任务。

        Returns:
            ImageryFusionJobResponse: 融合成果响应。
        """
        _, error = self._resolve_output(job)
        return ImageryFusionJobResponse(
            job_code=job.job_code,
            job_name=job.job_name,
            multispectral_asset_code=job.multispectral_asset_code,
            multispectral_asset_name=job.multispectral_asset_name,
            panchromatic_asset_code=job.panchromatic_asset_code,
            panchromatic_asset_name=job.panchromatic_asset_name,
            multispectral_band_indexes=list(job.multispectral_band_indexes),
            panchromatic_band_index=job.panchromatic_band_index,
            algorithm_code=job.algorithm_code,
            algorithm_version=job.algorithm_version,
            resampling_method=job.resampling_method,
            overlap_ratio=float(job.overlap_ratio),
            spectral_correlations=[float(value) for value in job.spectral_correlations],
            minimum_spectral_correlation=float(job.minimum_spectral_correlation),
            mean_spectral_correlation=float(job.mean_spectral_correlation),
            spatial_detail_gain=float(job.spatial_detail_gain),
            output_crs=job.output_crs,
            output_resolution_x=float(job.output_resolution_x),
            output_resolution_y=float(job.output_resolution_y),
            raster_width=job.raster_width,
            raster_height=job.raster_height,
            band_count=job.band_count,
            dtype=job.dtype,
            original_filename=job.original_filename,
            file_size_bytes=job.file_size_bytes,
            checksum_sha256=job.checksum_sha256,
            bounds_wgs84=list(job.bounds_wgs84),
            manifest=job.manifest or {},
            created_by=job.created_by,
            created_by_code=job.created_by_code,
            created_by_role=job.created_by_role,
            created_at=job.created_at,
            artifact_verified=error is None,
            artifact_error=error,
            download_url=(
                f"/api/v1/imagery-fusions/jobs/{job.job_code}/download"
                if error is None
                else None
            ),
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> ImageryFusionOverviewResponse:
        """查询融合来源资格和历史成果。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 当前稳定用户编码。

        Returns:
            ImageryFusionOverviewResponse: 来源、上限和成果。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        await self.user_service.require_capability(
            db, project.id, operator_code, "process_imagery"
        )
        assets = await self.dao.list_assets(db, project.id)
        jobs = await self.dao.list_jobs(db, project.id)
        return ImageryFusionOverviewResponse(
            max_output_pixels=self.engine.max_output_pixels,
            sources=[self._inspect_source(asset).response for asset in assets],
            jobs=[self._job_response(job) for job in jobs],
        )

    async def create_job(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ImageryFusionCreateRequest,
    ) -> ImageryFusionJobResponse:
        """执行真实全色融合并保存质量和血缘证据。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 当前任务编号。
            request: 融合输入、波段和质量门槛。

        Returns:
            ImageryFusionJobResponse: 已通过门禁的融合成果。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"未找到当前项目任务 {task_code}")
        operator = await self.user_service.require_capability(
            db, project.id, request.operator_code, "process_imagery"
        )
        if await self.dao.get_job(db, project.id, request.job_code) is not None:
            raise ValidationException(f"融合任务 {request.job_code} 已存在")
        ms_asset = await self.dao.get_asset(
            db, project.id, request.multispectral_asset_code
        )
        pan_asset = await self.dao.get_asset(
            db, project.id, request.panchromatic_asset_code
        )
        if ms_asset is None or pan_asset is None:
            raise ValidationException("融合输入影像不存在或不属于当前项目")
        ms = self._inspect_source(ms_asset)
        pan = self._inspect_source(pan_asset)
        if not ms.response.multispectral_eligible or ms.engine_source is None:
            raise ValidationException(
                ms.response.multispectral_reason or "多光谱来源不符合融合条件"
            )
        if not pan.response.panchromatic_eligible or pan.engine_source is None:
            raise ValidationException(
                pan.response.panchromatic_reason or "全色来源不符合融合条件"
            )
        if ms.response.product_identity != pan.response.product_identity:
            raise ValidationException("多光谱与全色影像必须来自同一可追溯产品")
        time_gap = abs((ms_asset.acquired_at - pan_asset.acquired_at).total_seconds())
        if time_gap > 60:
            raise ValidationException("多光谱与全色影像采集时间相差超过 60 秒")
        output_relative = (
            Path("jobs") / request.job_code / f"{uuid4().hex}.tif"
        )
        output_path = self.storage_root / output_relative
        result = await asyncio.to_thread(
            self.engine.execute,
            ms.engine_source,
            pan.engine_source,
            output_path,
            request.multispectral_band_indexes,
            request.panchromatic_band_index,
            request.resampling_method,
            request.minimum_overlap_ratio,
            request.minimum_spectral_correlation,
            request.minimum_spatial_detail_gain,
            request.gain_limit,
            request.job_code,
        )
        file_size = output_path.stat().st_size
        checksum = calculate_sha256(output_path)
        output_uri = f"storage://imagery-fusion/{output_relative.as_posix()}"
        manifest = {
            **result.manifest,
            "multispectral": {
                "asset_code": ms_asset.asset_code,
                "source_uri": ms.engine_source.source_uri,
                "source_size_bytes": ms.engine_source.source_size_bytes,
                "source_sha256": ms.engine_source.source_sha256,
                "product_identity": ms.response.product_identity,
                "reflectance_quantity": ms.response.reflectance_quantity,
            },
            "panchromatic": {
                "asset_code": pan_asset.asset_code,
                "source_uri": pan.engine_source.source_uri,
                "source_size_bytes": pan.engine_source.source_size_bytes,
                "source_sha256": pan.engine_source.source_sha256,
                "product_identity": pan.response.product_identity,
                "reflectance_quantity": pan.response.reflectance_quantity,
            },
            "output_uri": output_uri,
            "output_size_bytes": file_size,
            "output_sha256": checksum,
            "overlap_ratio": result.overlap_ratio,
            "spectral_correlations": result.spectral_correlations,
            "spatial_detail_gain": result.spatial_detail_gain,
        }
        job = ImageryFusionJob(
            project_id=project.id,
            task_id=task.id,
            job_code=request.job_code,
            job_name=request.job_name,
            multispectral_asset_id=ms_asset.id,
            multispectral_asset_code=ms_asset.asset_code,
            multispectral_asset_name=ms_asset.asset_name,
            panchromatic_asset_id=pan_asset.id,
            panchromatic_asset_code=pan_asset.asset_code,
            panchromatic_asset_name=pan_asset.asset_name,
            multispectral_band_indexes=request.multispectral_band_indexes,
            panchromatic_band_index=request.panchromatic_band_index,
            algorithm_code="brovey_histogram_match",
            algorithm_version=self.engine.processor_version,
            resampling_method=request.resampling_method,
            overlap_ratio=Decimal(str(result.overlap_ratio)),
            spectral_correlations=result.spectral_correlations,
            minimum_spectral_correlation=Decimal(
                str(result.minimum_spectral_correlation)
            ),
            mean_spectral_correlation=Decimal(
                str(result.mean_spectral_correlation)
            ),
            spatial_detail_gain=Decimal(str(result.spatial_detail_gain)),
            output_crs=result.crs,
            output_resolution_x=Decimal(str(result.resolution_x)),
            output_resolution_y=Decimal(str(result.resolution_y)),
            raster_width=result.width,
            raster_height=result.height,
            band_count=result.band_count,
            dtype=result.dtype,
            output_uri=output_uri,
            original_filename=f"{request.job_code}.tif",
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            bounds_wgs84=result.bounds_wgs84,
            manifest=manifest,
            created_by=operator.display_name,
            created_by_code=operator.user_code,
            created_by_role=operator.role_code,
        )
        try:
            job = await self.dao.add_job(db, job)
            await self.dao.add_event(
                db,
                ImageryFusionEvent(
                    project_id=project.id,
                    job_id=job.id,
                    event_type="fusion_completed",
                    actor=operator.display_name,
                    actor_code=operator.user_code,
                    actor_role=operator.role_code,
                    detail=manifest,
                    comment=request.comment,
                ),
            )
            await db.commit()
            await db.refresh(job)
        except (IntegrityError, SQLAlchemyError):
            await db.rollback()
            output_path.unlink(missing_ok=True)
            raise
        return self._job_response(job)

    async def get_download(
        self,
        db: AsyncSession,
        project_code: str,
        job_code: str,
        operator_code: str,
    ) -> FusionDownload:
        """授权并重新校验融合成果后返回下载信息。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            job_code: 融合任务编号。
            operator_code: 下载人稳定编码。

        Returns:
            FusionDownload: 下载路径、文件名和校验值。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        operator = await self.user_service.require_capability(
            db, project.id, operator_code, "process_imagery"
        )
        job = await self.dao.get_job(db, project.id, job_code)
        if job is None:
            raise NotFoundException(f"未找到融合任务 {job_code}")
        path, error = self._resolve_output(job)
        if error:
            raise ValidationException(error)
        await self.dao.add_event(
            db,
            ImageryFusionEvent(
                project_id=project.id,
                job_id=job.id,
                event_type="fusion_downloaded",
                actor=operator.display_name,
                actor_code=operator.user_code,
                actor_role=operator.role_code,
                detail={"checksum_sha256": job.checksum_sha256},
                comment="下载前已重新校验融合成果",
            ),
        )
        await db.commit()
        return FusionDownload(path, job.original_filename, job.checksum_sha256)
