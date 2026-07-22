"""多景影像输入校验、镶嵌执行、覆盖验收和下载服务。"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_mosaic_dao import ImageryMosaicDAO, MosaicSourceRecord
from app.dao.workbench_dao import WorkbenchDAO
from app.models.imagery_mosaic import (
    ImageryMosaicEvent,
    ImageryMosaicInput,
    ImageryMosaicJob,
)
from app.schemas.imagery_mosaic import (
    ImageryMosaicCreateRequest,
    ImageryMosaicJobResponse,
    ImageryMosaicOverviewResponse,
    ImageryMosaicSourceResponse,
)
from app.services.imagery_mosaic_engine import ImageryMosaicEngine, MosaicSource
from app.services.imagery_service import ImageryService
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class MosaicDownload:
    """已通过实体校验的镶嵌下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


class ImageryMosaicService:
    """编排多景影像生产并保持输入和输出校验可追溯。"""

    def __init__(
        self,
        dao: ImageryMosaicDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        imagery_service: ImageryService | None = None,
        engine: ImageryMosaicEngine | None = None,
    ) -> None:
        """初始化镶嵌服务。

        Args:
            dao: 镶嵌 DAO。
            workbench_dao: 项目任务 DAO。
            project_user_service: 稳定用户能力服务。
            imagery_service: 单景步骤实体校验服务。
            engine: Rasterio 镶嵌引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryMosaicDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.imagery_service = imagery_service or ImageryService()
        self.engine = engine or ImageryMosaicEngine(
            max_output_pixels=settings.max_imagery_mosaic_pixels
        )
        self.storage_root = (
            Path(__file__).resolve().parents[2] / "storage" / "imagery-mosaics"
        ).resolve()

    def _source_response(
        self,
        record: MosaicSourceRecord,
        balance_statistics: dict | None = None,
    ) -> tuple[ImageryMosaicSourceResponse, MosaicSource]:
        """重新校验候选步骤实体并读取真实栅格结构。

        Args:
            record: 资产与步骤数据库记录。
            balance_statistics: 已固化匀色统计。

        Returns:
            tuple: API 来源响应和引擎输入。
        """
        path, evidence = self.imagery_service.resolve_verified_step_artifact_path(
            record.step
        )
        try:
            with rasterio.open(path) as dataset:
                if dataset.crs is None:
                    raise ValidationException("镶嵌来源必须先完成空间校正")
                response = ImageryMosaicSourceResponse(
                    asset_code=record.asset.asset_code,
                    asset_name=record.asset.asset_name,
                    step_code=record.step.step_code,
                    step_name=record.step.step_name,
                    source_uri=record.step.output_uri or "",
                    source_size_bytes=int(evidence["file_size_bytes"]),
                    source_sha256=str(evidence["checksum_sha256"]),
                    source_crs=dataset.crs.to_string(),
                    source_width=dataset.width,
                    source_height=dataset.height,
                    source_band_count=dataset.count,
                    band_descriptions=list(dataset.descriptions),
                    bounds_wgs84=[
                        float(value)
                        for value in transform_bounds(
                            dataset.crs,
                            "EPSG:4326",
                            *dataset.bounds,
                            densify_pts=21,
                        )
                    ],
                    balance_statistics=balance_statistics or {},
                )
        except RasterioIOError as exc:
            raise ValidationException("镶嵌来源无法由 Rasterio 读取") from exc
        source = MosaicSource(
            asset_code=response.asset_code,
            asset_name=response.asset_name,
            step_code=response.step_code,
            step_name=response.step_name,
            path=path,
            source_uri=response.source_uri,
            source_size_bytes=response.source_size_bytes,
            source_sha256=response.source_sha256,
        )
        return response, source

    @staticmethod
    def _input_response(item: ImageryMosaicInput) -> ImageryMosaicSourceResponse:
        """把不可变输入模型转换为 API 响应。

        Args:
            item: 输入模型。

        Returns:
            ImageryMosaicSourceResponse: 输入血缘响应。
        """
        return ImageryMosaicSourceResponse(
            asset_code=item.asset_code,
            asset_name=item.asset_name,
            step_code=item.step_code,
            step_name=item.step_name,
            source_uri=item.source_uri,
            source_size_bytes=item.source_size_bytes,
            source_sha256=item.source_sha256,
            source_crs=item.source_crs,
            source_width=item.source_width,
            source_height=item.source_height,
            source_band_count=item.source_band_count,
            band_descriptions=item.band_descriptions,
            bounds_wgs84=None,
            balance_statistics=item.balance_statistics,
        )

    async def _job_response(
        self,
        db: AsyncSession,
        job: ImageryMosaicJob,
    ) -> ImageryMosaicJobResponse:
        """组装一个镶嵌任务和输入血缘。

        Args:
            db: 异步数据库会话。
            job: 镶嵌任务。

        Returns:
            ImageryMosaicJobResponse: 完整任务响应。
        """
        inputs = await self.dao.list_inputs(db, job.id)
        coverage_threshold = float(job.coverage_threshold)
        coverage_ratio = float(job.coverage_ratio)
        artifact_verified = True
        artifact_error = None
        try:
            await asyncio.to_thread(self._verify_job_file, job)
        except ValidationException as exc:
            artifact_verified = False
            artifact_error = str(exc)
        return ImageryMosaicJobResponse(
            job_code=job.job_code,
            job_name=job.job_name,
            boundary_code=job.boundary_code,
            boundary_name=job.boundary_name,
            target_crs=job.target_crs,
            target_resolution=float(job.target_resolution),
            color_balance_method=job.color_balance_method,
            blend_method=job.blend_method,
            resampling_method=job.resampling_method,
            coverage_threshold=coverage_threshold,
            coverage_ratio=coverage_ratio,
            meets_coverage=coverage_ratio >= coverage_threshold,
            boundary_pixel_count=job.boundary_pixel_count,
            covered_pixel_count=job.covered_pixel_count,
            source_count=job.source_count,
            raster_width=job.raster_width,
            raster_height=job.raster_height,
            band_count=job.band_count,
            dtype=job.dtype,
            original_filename=job.original_filename,
            file_size_bytes=job.file_size_bytes,
            checksum_sha256=job.checksum_sha256,
            bounds_wgs84=[float(value) for value in job.bounds_wgs84],
            manifest=job.manifest,
            created_by=job.created_by,
            created_by_code=job.created_by_code,
            created_by_role=job.created_by_role,
            created_at=job.created_at,
            inputs=[self._input_response(item) for item in inputs],
            artifact_verified=artifact_verified,
            artifact_error=artifact_error,
            download_url=(
                f"/api/v1/imagery-mosaics/jobs/{job.job_code}/download"
                if artifact_verified
                else None
            ),
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> ImageryMosaicOverviewResponse:
        """查询可用输入和真实镶嵌成果。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 当前稳定用户编码。

        Returns:
            ImageryMosaicOverviewResponse: 镶嵌总览。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException("未找到监测项目")
        await self.project_user_service.require_capability(
            db, project.id, operator_code, "process_imagery"
        )
        available_sources = []
        for record in await self.dao.list_source_records(db, project.id):
            try:
                response, _ = self._source_response(record)
            except ValidationException:
                continue
            available_sources.append(response)
        jobs = [
            await self._job_response(db, job)
            for job in await self.dao.list_jobs(db, project.id)
        ]
        return ImageryMosaicOverviewResponse(
            max_output_pixels=settings.max_imagery_mosaic_pixels,
            available_sources=available_sources,
            jobs=jobs,
        )

    async def create_job(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ImageryMosaicCreateRequest,
    ) -> ImageryMosaicJobResponse:
        """校验输入并生成通过覆盖门禁的镶嵌实体。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 当前任务编号。
            request: 镶嵌参数、来源和操作人。

        Returns:
            ImageryMosaicJobResponse: 已完成任务。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None or task is None or task.project_id != project.id:
            raise NotFoundException("未找到当前项目作业任务")
        user = await self.project_user_service.require_capability(
            db, project.id, request.operator_code, "process_imagery"
        )
        if await self.dao.get_job_by_code(db, project.id, request.job_code):
            raise ValidationException("镶嵌任务编号已存在")
        boundary = await self.dao.get_boundary_geojson(
            db, project.id, request.boundary_code
        )
        if boundary is None:
            raise ValidationException("未找到当前项目真实行政区边界")
        boundary_name, boundary_geojson = boundary
        records = await self.dao.list_source_records(db, project.id)
        record_map = {
            (record.asset.asset_code, record.step.step_code): record
            for record in records
        }
        source_responses = []
        engine_sources = []
        selected_records = []
        for selected in request.sources:
            record = record_map.get((selected.asset_code, selected.step_code))
            if record is None:
                raise ValidationException(
                    f"未找到已登记来源 {selected.asset_code}/{selected.step_code}"
                )
            response, source = self._source_response(record)
            source_responses.append(response)
            engine_sources.append(source)
            selected_records.append(record)
        filename = f"{request.job_code}.tif"
        relative_path = Path("jobs") / request.job_code / f"{uuid4().hex}.tif"
        output_path = (self.storage_root / relative_path).resolve()
        if self.storage_root not in output_path.parents:
            raise ValidationException("镶嵌输出路径越界")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = await asyncio.to_thread(
                self.engine.execute,
                engine_sources,
                output_path,
                json.loads(boundary_geojson),
                request.target_crs,
                request.target_resolution,
                request.color_balance_method,
                request.blend_method,
                request.resampling_method,
                request.coverage_threshold,
                request.job_code,
            )
            file_size = output_path.stat().st_size
            checksum = await asyncio.to_thread(calculate_sha256, output_path)
            manifest = {
                **result.manifest,
                "output_uri": (
                    f"storage://imagery-mosaics/{relative_path.as_posix()}"
                ),
                "output_size_bytes": file_size,
                "output_sha256": checksum,
                "boundary_code": request.boundary_code,
                "boundary_name": boundary_name,
                "inputs_digest_sha256": hashlib.sha256(
                    json.dumps(
                        [
                            {
                                "asset_code": item.asset_code,
                                "step_code": item.step_code,
                                "source_sha256": item.source_sha256,
                            }
                            for item in source_responses
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
            job = await self.dao.add_job(
                db,
                ImageryMosaicJob(
                    project_id=project.id,
                    task_id=task.id,
                    job_code=request.job_code,
                    job_name=request.job_name,
                    boundary_code=request.boundary_code,
                    boundary_name=boundary_name,
                    target_crs=result.crs,
                    target_resolution=Decimal(str(request.target_resolution)),
                    color_balance_method=request.color_balance_method,
                    blend_method=request.blend_method,
                    resampling_method=request.resampling_method,
                    coverage_threshold=Decimal(str(request.coverage_threshold)),
                    coverage_ratio=Decimal(str(result.coverage_ratio)),
                    boundary_pixel_count=result.boundary_pixel_count,
                    covered_pixel_count=result.covered_pixel_count,
                    source_count=len(result.inputs),
                    raster_width=result.width,
                    raster_height=result.height,
                    band_count=result.band_count,
                    dtype=result.dtype,
                    output_uri=(
                        f"storage://imagery-mosaics/{relative_path.as_posix()}"
                    ),
                    original_filename=filename,
                    file_size_bytes=file_size,
                    checksum_sha256=checksum,
                    bounds_wgs84=result.bounds_wgs84,
                    manifest=manifest,
                    created_by=user.display_name,
                    created_by_code=user.user_code,
                    created_by_role=user.role_code,
                ),
            )
            await self.dao.add_inputs(
                db,
                [
                    ImageryMosaicInput(
                        job_id=job.id,
                        asset_id=record.asset.id,
                        asset_code=evidence.source.asset_code,
                        asset_name=evidence.source.asset_name,
                        step_code=evidence.source.step_code,
                        step_name=evidence.source.step_name,
                        source_order=index,
                        source_uri=evidence.source.source_uri,
                        source_size_bytes=evidence.source.source_size_bytes,
                        source_sha256=evidence.source.source_sha256,
                        source_crs=evidence.crs,
                        source_width=evidence.width,
                        source_height=evidence.height,
                        source_band_count=evidence.band_count,
                        band_descriptions=evidence.band_descriptions,
                        balance_statistics=evidence.balance_statistics,
                    )
                    for index, (record, evidence) in enumerate(
                        zip(selected_records, result.inputs, strict=True),
                        start=1,
                    )
                ],
            )
            await self.dao.add_event(
                db,
                ImageryMosaicEvent(
                    project_id=project.id,
                    job_id=job.id,
                    event_type="mosaic_completed",
                    actor=user.display_name,
                    actor_code=user.user_code,
                    actor_role=user.role_code,
                    detail={
                        "coverage_ratio": result.coverage_ratio,
                        "coverage_threshold": request.coverage_threshold,
                        "source_count": len(result.inputs),
                        "output_sha256": checksum,
                    },
                    comment=request.comment,
                ),
            )
            await db.commit()
        except asyncio.CancelledError:
            await db.rollback()
            output_path.unlink(missing_ok=True)
            raise
        except Exception:
            await db.rollback()
            output_path.unlink(missing_ok=True)
            raise
        return await self._job_response(db, job)

    def _verify_job_file(self, job: ImageryMosaicJob) -> Path:
        """复核镶嵌成果受控路径、大小和 SHA-256。

        Args:
            job: 镶嵌任务。

        Returns:
            Path: 校验通过的文件。
        """
        prefix = "storage://imagery-mosaics/"
        if not job.output_uri.startswith(prefix):
            raise ValidationException("镶嵌成果地址不受控")
        path = (self.storage_root / job.output_uri.removeprefix(prefix)).resolve()
        if self.storage_root not in path.parents or not path.is_file():
            raise ValidationException("镶嵌成果不存在或路径越界")
        if path.stat().st_size != job.file_size_bytes:
            raise ValidationException("镶嵌成果大小校验失败")
        if calculate_sha256(path) != job.checksum_sha256:
            raise ValidationException("镶嵌成果 SHA-256 校验失败")
        return path

    async def get_download(
        self,
        db: AsyncSession,
        project_code: str,
        job_code: str,
        operator_code: str,
    ) -> MosaicDownload:
        """鉴权并复核镶嵌成果后返回下载信息。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            job_code: 镶嵌任务编号。
            operator_code: 当前稳定用户编码。

        Returns:
            MosaicDownload: 下载信息。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException("未找到监测项目")
        user = await self.project_user_service.require_capability(
            db, project.id, operator_code, "process_imagery"
        )
        job = await self.dao.get_job_by_code(db, project.id, job_code)
        if job is None:
            raise NotFoundException("未找到镶嵌成果")
        path = await asyncio.to_thread(self._verify_job_file, job)
        await self.dao.add_event(
            db,
            ImageryMosaicEvent(
                project_id=project.id,
                job_id=job.id,
                event_type="mosaic_downloaded",
                actor=user.display_name,
                actor_code=user.user_code,
                actor_role=user.role_code,
                detail={"checksum_sha256": job.checksum_sha256},
            ),
        )
        await db.commit()
        return MosaicDownload(
            path=path,
            filename=job.original_filename,
            checksum_sha256=job.checksum_sha256,
        )
