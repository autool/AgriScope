"""双景影像配准输入校验、实体生成、残差验收和下载服务。"""

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
from app.dao.imagery_registration_dao import (
    ImageryRegistrationDAO,
    RegistrationSourceRecord,
)
from app.dao.workbench_dao import WorkbenchDAO
from app.models.imagery_registration import (
    ImageryRegistrationEvent,
    ImageryRegistrationJob,
)
from app.schemas.imagery_registration import (
    ImageryRegistrationCreateRequest,
    ImageryRegistrationJobResponse,
    ImageryRegistrationOverviewResponse,
    ImageryRegistrationSourceResponse,
)
from app.services.imagery_registration_engine import (
    ImageryRegistrationEngine,
    RegistrationSource,
)
from app.services.imagery_service import ImageryService
from app.services.project_user_service import ProjectUserService
from app.services.rule_config_service import RuleConfigService


@dataclass(frozen=True)
class RegistrationDownload:
    """已通过实体复核的配准成果下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


class ImageryRegistrationService:
    """编排真实双景配准并保存可追溯残差和用户角色证据。"""

    def __init__(
        self,
        dao: ImageryRegistrationDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        rule_service: RuleConfigService | None = None,
        imagery_service: ImageryService | None = None,
        engine: ImageryRegistrationEngine | None = None,
    ) -> None:
        """初始化影像配准服务。

        Args:
            dao: 配准 DAO。
            workbench_dao: 项目任务 DAO。
            user_service: 稳定项目用户服务。
            rule_service: 项目规则服务。
            imagery_service: 单景步骤实体校验服务。
            engine: 自动配准引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryRegistrationDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.rule_service = rule_service or RuleConfigService()
        self.imagery_service = imagery_service or ImageryService()
        self.engine = engine or ImageryRegistrationEngine(
            max_output_pixels=settings.max_imagery_registration_pixels,
            preview_max_dimension=settings.imagery_registration_preview_max_dimension,
        )
        self.storage_root = (
            Path(__file__).resolve().parents[2]
            / "storage"
            / "imagery-registration"
        ).resolve()

    def _source_response(
        self,
        record: RegistrationSourceRecord,
    ) -> tuple[ImageryRegistrationSourceResponse, RegistrationSource]:
        """重新校验步骤实体并读取栅格结构与 WGS84 范围。

        Args:
            record: 影像资产和处理步骤记录。

        Returns:
            tuple: API 来源响应和引擎来源。
        """
        path, evidence = self.imagery_service.resolve_verified_step_artifact_path(
            record.step
        )
        try:
            with rasterio.open(path) as dataset:
                if dataset.crs is None:
                    raise ValidationException("配准来源必须具有可验证 CRS")
                eligible = record.asset.data_status == "operational"
                response = ImageryRegistrationSourceResponse(
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
                    data_status=record.asset.data_status,
                    eligible=eligible,
                    eligibility_reason=(
                        None
                        if eligible
                        else "演示影像不能作为正式自动配准生产输入"
                    ),
                )
        except RasterioIOError as exc:
            raise ValidationException("配准来源无法由 Rasterio 读取") from exc
        source = RegistrationSource(
            asset_id=record.asset.id,
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

    def _verify_job_file(self, job: ImageryRegistrationJob) -> Path:
        """复核配准成果受控路径、大小和 SHA-256。

        Args:
            job: 配准任务。

        Returns:
            Path: 校验通过的 GeoTIFF。
        """
        prefix = "storage://imagery-registration/"
        if not job.output_uri.startswith(prefix):
            raise ValidationException("配准成果地址不受控")
        path = (self.storage_root / job.output_uri.removeprefix(prefix)).resolve()
        if self.storage_root not in path.parents or not path.is_file():
            raise ValidationException("配准成果不存在或路径越界")
        if path.stat().st_size != job.file_size_bytes:
            raise ValidationException("配准成果大小校验失败")
        if calculate_sha256(path) != job.checksum_sha256:
            raise ValidationException("配准成果 SHA-256 校验失败")
        return path

    async def _job_response(
        self,
        job: ImageryRegistrationJob,
    ) -> ImageryRegistrationJobResponse:
        """把配准任务与当前实体状态转换为 API 响应。

        Args:
            job: 配准任务。

        Returns:
            ImageryRegistrationJobResponse: 完整任务响应。
        """
        artifact_verified = True
        artifact_error = None
        try:
            await asyncio.to_thread(self._verify_job_file, job)
        except ValidationException as exc:
            artifact_verified = False
            artifact_error = str(exc)
        return ImageryRegistrationJobResponse(
            job_code=job.job_code,
            job_name=job.job_name,
            reference_asset_code=job.reference_asset_code,
            moving_asset_code=job.moving_asset_code,
            reference_step_code=job.reference_step_code,
            moving_step_code=job.moving_step_code,
            reference_band_index=job.reference_band_index,
            moving_band_index=job.moving_band_index,
            resampling_method=job.resampling_method,
            initial_shift_x_pixels=float(job.initial_shift_x_pixels),
            initial_shift_y_pixels=float(job.initial_shift_y_pixels),
            initial_offset_pixels=float(job.initial_offset_pixels),
            residual_shift_x_pixels=float(job.residual_shift_x_pixels),
            residual_shift_y_pixels=float(job.residual_shift_y_pixels),
            residual_offset_pixels=float(job.residual_offset_pixels),
            overlap_ratio=float(job.overlap_ratio),
            peak_to_sidelobe_ratio=float(job.peak_to_sidelobe_ratio),
            residual_threshold_pixels=float(job.residual_threshold_pixels),
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
            bounds_wgs84=[float(value) for value in job.bounds_wgs84],
            manifest=job.manifest,
            created_by=job.created_by,
            created_by_code=job.created_by_code,
            created_by_role=job.created_by_role,
            created_at=job.created_at,
            artifact_verified=artifact_verified,
            artifact_error=artifact_error,
            download_url=(
                f"/api/v1/imagery-registrations/jobs/{job.job_code}/download"
                if artifact_verified
                else None
            ),
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> ImageryRegistrationOverviewResponse:
        """查询配准可用来源、项目精度规则和历史成果。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 当前稳定用户编码。

        Returns:
            ImageryRegistrationOverviewResponse: 配准总览。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException("未找到监测项目")
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "process_imagery",
        )
        config = await self.rule_service.ensure_for_project(db, project.id)
        available_sources = []
        for record in await self.dao.list_source_records(db, project.id):
            try:
                response, _ = self._source_response(record)
            except ValidationException:
                continue
            available_sources.append(response)
        jobs = [
            await self._job_response(job)
            for job in await self.dao.list_jobs(db, project.id)
        ]
        return ImageryRegistrationOverviewResponse(
            max_output_pixels=settings.max_imagery_registration_pixels,
            project_positional_accuracy_pixels=float(
                config.positional_accuracy_pixels
            ),
            available_sources=available_sources,
            jobs=jobs,
        )

    async def create_job(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ImageryRegistrationCreateRequest,
    ) -> ImageryRegistrationJobResponse:
        """执行自动配准并仅持久化通过项目残差门禁的实体。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 当前作业任务编号。
            request: 配准来源、算法门槛和操作人。

        Returns:
            ImageryRegistrationJobResponse: 已完成配准成果。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None or task is None or task.project_id != project.id:
            raise NotFoundException("未找到当前项目作业任务")
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "process_imagery",
        )
        if await self.dao.get_job_by_code(db, project.id, request.job_code):
            raise ValidationException("影像配准任务编号已存在")
        config = await self.rule_service.ensure_for_project(db, project.id)
        project_threshold = float(config.positional_accuracy_pixels)
        residual_threshold = min(
            request.max_residual_pixels,
            project_threshold,
        )
        records = await self.dao.list_source_records(db, project.id)
        record_map = {
            (record.asset.asset_code, record.step.step_code): record
            for record in records
        }
        reference_record = record_map.get((
            request.reference.asset_code,
            request.reference.step_code,
        ))
        moving_record = record_map.get((
            request.moving.asset_code,
            request.moving.step_code,
        ))
        if reference_record is None or moving_record is None:
            raise ValidationException("未找到已登记的配准来源步骤")
        reference_response, reference_source = self._source_response(
            reference_record
        )
        moving_response, moving_source = self._source_response(moving_record)
        for label, response in (
            ("参考影像", reference_response),
            ("待配准影像", moving_response),
        ):
            if not response.eligible:
                raise ValidationException(
                    f"{label}不可用于正式配准：{response.eligibility_reason}"
                )
        output_relative = (
            Path("jobs") / request.job_code / f"{uuid4().hex}.tif"
        )
        output_path = (self.storage_root / output_relative).resolve()
        if self.storage_root not in output_path.parents:
            raise ValidationException("配准输出路径越界")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = await asyncio.to_thread(
                self.engine.execute,
                reference_source,
                moving_source,
                output_path,
                request.reference.band_index,
                request.moving.band_index,
                request.resampling_method,
                request.max_initial_offset_pixels,
                residual_threshold,
                request.minimum_overlap_ratio,
                request.minimum_peak_to_sidelobe_ratio,
                request.job_code,
            )
            file_size = output_path.stat().st_size
            checksum = await asyncio.to_thread(calculate_sha256, output_path)
            output_uri = (
                "storage://imagery-registration/"
                f"{output_relative.as_posix()}"
            )
            manifest = {
                **result.manifest,
                "reference": {
                    "asset_code": reference_response.asset_code,
                    "step_code": reference_response.step_code,
                    "source_uri": reference_response.source_uri,
                    "source_size_bytes": reference_response.source_size_bytes,
                    "source_sha256": reference_response.source_sha256,
                    "band_index": request.reference.band_index,
                },
                "moving": {
                    "asset_code": moving_response.asset_code,
                    "step_code": moving_response.step_code,
                    "source_uri": moving_response.source_uri,
                    "source_size_bytes": moving_response.source_size_bytes,
                    "source_sha256": moving_response.source_sha256,
                    "band_index": request.moving.band_index,
                },
                "project_rule_version": config.version,
                "project_positional_accuracy_pixels": project_threshold,
                "requested_max_residual_pixels": request.max_residual_pixels,
                "effective_residual_threshold_pixels": residual_threshold,
                "output_uri": output_uri,
                "output_size_bytes": file_size,
                "output_sha256": checksum,
                "input_pair_digest_sha256": hashlib.sha256(
                    json.dumps(
                        {
                            "reference_sha256": reference_response.source_sha256,
                            "moving_sha256": moving_response.source_sha256,
                        },
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
            job = await self.dao.add_job(
                db,
                ImageryRegistrationJob(
                    project_id=project.id,
                    task_id=task.id,
                    job_code=request.job_code,
                    job_name=request.job_name,
                    reference_asset_id=reference_source.asset_id,
                    moving_asset_id=moving_source.asset_id,
                    reference_asset_code=reference_source.asset_code,
                    moving_asset_code=moving_source.asset_code,
                    reference_step_code=reference_source.step_code,
                    moving_step_code=moving_source.step_code,
                    reference_uri=reference_source.source_uri,
                    reference_size_bytes=reference_source.source_size_bytes,
                    reference_sha256=reference_source.source_sha256,
                    moving_uri=moving_source.source_uri,
                    moving_size_bytes=moving_source.source_size_bytes,
                    moving_sha256=moving_source.source_sha256,
                    reference_band_index=request.reference.band_index,
                    moving_band_index=request.moving.band_index,
                    resampling_method=request.resampling_method,
                    initial_shift_x_pixels=Decimal(str(
                        result.initial_shift_x_pixels
                    )),
                    initial_shift_y_pixels=Decimal(str(
                        result.initial_shift_y_pixels
                    )),
                    initial_offset_pixels=Decimal(str(
                        result.initial_offset_pixels
                    )),
                    residual_shift_x_pixels=Decimal(str(
                        result.residual_shift_x_pixels
                    )),
                    residual_shift_y_pixels=Decimal(str(
                        result.residual_shift_y_pixels
                    )),
                    residual_offset_pixels=Decimal(str(
                        result.residual_offset_pixels
                    )),
                    overlap_ratio=Decimal(str(result.overlap_ratio)),
                    peak_to_sidelobe_ratio=Decimal(str(
                        result.peak_to_sidelobe_ratio
                    )),
                    residual_threshold_pixels=Decimal(str(residual_threshold)),
                    output_uri=output_uri,
                    original_filename=f"{request.job_code}.tif",
                    file_size_bytes=file_size,
                    checksum_sha256=checksum,
                    output_crs=result.crs,
                    output_resolution_x=Decimal(str(result.resolution_x)),
                    output_resolution_y=Decimal(str(result.resolution_y)),
                    raster_width=result.width,
                    raster_height=result.height,
                    band_count=result.band_count,
                    dtype=result.dtype,
                    bounds_wgs84=result.bounds_wgs84,
                    manifest=manifest,
                    created_by=user.display_name,
                    created_by_code=user.user_code,
                    created_by_role=user.role_code,
                ),
            )
            await self.dao.add_event(
                db,
                ImageryRegistrationEvent(
                    project_id=project.id,
                    job_id=job.id,
                    event_type="registration_completed",
                    actor=user.display_name,
                    actor_code=user.user_code,
                    actor_role=user.role_code,
                    detail={
                        "initial_offset_pixels": result.initial_offset_pixels,
                        "residual_offset_pixels": result.residual_offset_pixels,
                        "residual_threshold_pixels": residual_threshold,
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
        return await self._job_response(job)

    async def get_download(
        self,
        db: AsyncSession,
        project_code: str,
        job_code: str,
        operator_code: str,
    ) -> RegistrationDownload:
        """鉴权、复核实体并写入下载审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            job_code: 配准任务编号。
            operator_code: 当前稳定用户编码。

        Returns:
            RegistrationDownload: 下载路径、文件名和 ETag。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException("未找到监测项目")
        user = await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "process_imagery",
        )
        job = await self.dao.get_job_by_code(db, project.id, job_code)
        if job is None:
            raise NotFoundException("未找到影像配准成果")
        path = await asyncio.to_thread(self._verify_job_file, job)
        await self.dao.add_event(
            db,
            ImageryRegistrationEvent(
                project_id=project.id,
                job_id=job.id,
                event_type="registration_downloaded",
                actor=user.display_name,
                actor_code=user.user_code,
                actor_role=user.role_code,
                detail={"checksum_sha256": job.checksum_sha256},
            ),
        )
        await db.commit()
        return RegistrationDownload(
            path=path,
            filename=job.original_filename,
            checksum_sha256=job.checksum_sha256,
        )

    async def resolve_verified_job(
        self,
        db: AsyncSession,
        project_id: int,
        job_code: str,
    ) -> tuple[ImageryRegistrationJob, Path]:
        """供变化检测等下游解析并复核配准成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_code: 配准任务编号。

        Returns:
            tuple: 配准任务和校验通过的实体路径。
        """
        job = await self.dao.get_job_by_code(db, project_id, job_code)
        if job is None:
            raise ValidationException("未找到已完成影像配准任务")
        path = await asyncio.to_thread(self._verify_job_file, job)
        return job, path

    async def resolve_verified_job_by_id(
        self,
        db: AsyncSession,
        project_id: int,
        job_id: int,
    ) -> tuple[ImageryRegistrationJob, Path]:
        """按主键解析并复核配准成果。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            job_id: 配准任务主键。

        Returns:
            tuple: 配准任务和校验通过的实体路径。
        """
        job = await self.dao.get_job_by_id(db, project_id, job_id)
        if job is None:
            raise ValidationException("变化检测绑定的配准成果不存在")
        path = await asyncio.to_thread(self._verify_job_file, job)
        return job, path

    async def list_project_job_responses(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[ImageryRegistrationJobResponse]:
        """供项目内其他业务列出配准成果及当前实体状态。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[ImageryRegistrationJobResponse]: 配准任务响应。
        """
        return [
            await self._job_response(job)
            for job in await self.dao.list_jobs(db, project_id)
        ]
