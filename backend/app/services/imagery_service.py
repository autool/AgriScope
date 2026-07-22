"""遥感影像预处理流水线业务服务。"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import rasterio
from rasterio.errors import RasterioIOError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import (
    calculate_sha256,
    has_supported_raster_signature,
    resolve_imagery_path,
)
from app.dao.imagery_dao import ImageryDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import ReviewRecord
from app.schemas.imagery import (
    ImageryProcessingResponse,
    ImageryProcessingStepResponse,
    ImagerySourceLevelAcceptRequest,
    ImageryStepExecuteRequest,
    ImageryStepRunRequest,
)
from app.services.imagery_processing_engine import ImageryProcessingEngine
from app.services.project_user_service import ProjectUserService


class ImageryService:
    """查询影像处理进度并执行受控流水线步骤。"""

    SOURCE_LEVEL_ACCEPTANCE_STEPS = {
        "radiometric": "源文件已按 STAC 标度转换为 L2A 地表反射率",
        "atmospheric": "Sentinel-2 L2A 已完成大气校正并提供地表反射率",
    }
    SOURCE_LEVEL_REQUIRED_TAGS = (
        "PLATFORM",
        "INSTRUMENT",
        "PROCESSING_LEVEL",
        "SOURCE_PROVIDER",
        "SOURCE_PRODUCT_URI",
        "SOURCE_PROCESSING_BASELINE",
        "SOURCE_SCALE_APPLIED",
        "REFLECTANCE_QUANTITY",
    )

    def __init__(
        self,
        dao: ImageryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        processing_engine: ImageryProcessingEngine | None = None,
    ) -> None:
        """初始化影像预处理服务。

        Args:
            dao: 影像处理 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目成员能力服务。
            processing_engine: 栅格处理执行引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ImageryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.processing_engine = processing_engine or ImageryProcessingEngine()
        self.storage_dir = (
            Path(__file__).resolve().parents[2] / "storage" / "imagery"
        )

    def _resolve_artifact_path(self, relative_path: str) -> Path:
        """将受控相对路径解析到影像存储根目录。

        Args:
            relative_path: 相对于影像存储根目录的产物路径。

        Returns:
            Path: 已确认未越界的绝对路径。
        """
        try:
            return resolve_imagery_path(self.storage_dir, relative_path)
        except ValueError as exc:
            raise ValidationException(str(exc)) from exc

    def _inspect_step_artifact(
        self,
        step: object,
    ) -> tuple[bool, dict, str | None]:
        """校验步骤登记的实体产物仍存在且校验值一致。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            tuple[bool, dict, str | None]: 是否有效、证据信息和失败原因。
        """
        try:
            _, evidence = self.resolve_verified_step_artifact_path(step)
        except ValidationException as exc:
            evidence = (step.parameters or {}).get("artifact_evidence") or {}
            return False, evidence, exc.message
        return True, evidence, None

    def resolve_verified_step_artifact_path(
        self,
        step: object,
    ) -> tuple[Path, dict]:
        """解析并校验处理步骤实体产物路径、大小和 SHA256。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            tuple[Path, dict]: 已校验实体路径和产物证据。
        """
        evidence = (step.parameters or {}).get("artifact_evidence") or {}
        relative_path = evidence.get("relative_path")
        if not relative_path:
            raise ValidationException("尚未登记实体产物")
        try:
            artifact_path = self._resolve_artifact_path(str(relative_path))
        except ValidationException as exc:
            raise ValidationException("登记的产物路径不合法") from exc
        if not artifact_path.is_file():
            raise ValidationException("登记的实体产物不存在")
        if not has_supported_raster_signature(artifact_path):
            raise ValidationException("实体产物文件头与声明格式不一致")
        file_size = artifact_path.stat().st_size
        if file_size != evidence.get("file_size_bytes"):
            raise ValidationException("实体产物大小与登记值不一致")
        checksum = calculate_sha256(artifact_path)
        if checksum != evidence.get("checksum_sha256"):
            raise ValidationException("实体产物 SHA256 与登记值不一致")
        return artifact_path, evidence

    def _to_step_response(self, step: object) -> ImageryProcessingStepResponse:
        """组装包含实体产物校验状态的步骤响应。

        Args:
            step: 影像处理步骤 ORM 对象。

        Returns:
            ImageryProcessingStepResponse: 当前步骤和产物证据。
        """
        verified, evidence, error = self._inspect_step_artifact(step)
        effective_status = (
            "artifact_missing"
            if step.status == "completed" and not verified
            else step.status
        )
        return ImageryProcessingStepResponse(
            step_code=step.step_code,
            step_name=step.step_name,
            sequence=step.sequence,
            status=effective_status,
            progress=100 if verified else 0,
            parameters=step.parameters or {},
            output_uri=step.output_uri,
            output_verified=verified,
            output_size_bytes=evidence.get("file_size_bytes"),
            output_checksum_sha256=evidence.get("checksum_sha256"),
            processor_name=evidence.get("processor_name"),
            processor_version=evidence.get("processor_version"),
            artifact_error=error,
            started_at=step.started_at,
            completed_at=step.completed_at,
        )

    def resolve_verified_asset_source_path(self, asset: object) -> Path:
        """校验并解析原始影像资产实体文件。

        Args:
            asset: 影像资产 ORM 对象。

        Returns:
            Path: 已通过路径、大小、格式和 SHA256 校验的源文件。
        """
        file_uri = str(getattr(asset, "file_uri", "") or "")
        if not file_uri.startswith("storage://imagery/"):
            raise ValidationException("当前影像资产未关联可处理的实体文件")
        relative_path = file_uri.removeprefix("storage://imagery/")
        source_path = self._resolve_artifact_path(relative_path)
        if not source_path.is_file():
            raise ValidationException("当前影像资产实体文件不存在")
        if not has_supported_raster_signature(source_path):
            raise ValidationException("当前影像资产格式签名不合法")
        expected_size = getattr(asset, "file_size_bytes", None)
        if expected_size is not None and source_path.stat().st_size != expected_size:
            raise ValidationException("当前影像资产文件大小与数据库记录不一致")
        expected_checksum = getattr(asset, "checksum_sha256", None)
        if expected_checksum and calculate_sha256(source_path) != expected_checksum:
            raise ValidationException("当前影像资产 SHA256 与数据库记录不一致")
        return source_path

    def _resolve_step_source_path(
        self,
        asset: object,
        steps: list[object],
        step: object,
    ) -> Path:
        """解析当前步骤应使用的原始影像或上一环节产物。

        Args:
            asset: 影像资产 ORM 对象。
            steps: 资产全部处理步骤。
            step: 当前待执行步骤。

        Returns:
            Path: 已校验的上游实体栅格路径。
        """
        previous_steps = [item for item in steps if item.sequence < step.sequence]
        blockers = [
            item for item in previous_steps if not self._inspect_step_artifact(item)[0]
        ]
        if blockers:
            raise ValidationException(
                f"请先完成并校验步骤：{blockers[0].step_name}"
            )
        if not previous_steps:
            return self.resolve_verified_asset_source_path(asset)
        previous_step = max(previous_steps, key=lambda item: item.sequence)
        evidence = (previous_step.parameters or {}).get("artifact_evidence") or {}
        relative_path = str(evidence.get("relative_path") or "")
        if not relative_path:
            raise ValidationException("上一处理步骤缺少实体产物路径")
        return self._resolve_artifact_path(relative_path)

    @classmethod
    def _inspect_source_level_evidence(
        cls,
        source_path: Path,
        expected_processing_level: str,
    ) -> dict:
        """从当前实体栅格复核可承认的 Sentinel-2 L2A 证据。

        Args:
            source_path: 已通过路径、大小和 SHA256 校验的上游实体。
            expected_processing_level: 请求声明的产品级别。

        Returns:
            dict: 从物理文件读取的产品级别、血缘和栅格结构证据。
        """
        try:
            with rasterio.open(source_path) as dataset:
                tags = {
                    str(key).strip().upper(): str(value).strip()
                    for key, value in dataset.tags().items()
                }
                missing_tags = [
                    key for key in cls.SOURCE_LEVEL_REQUIRED_TAGS if not tags.get(key)
                ]
                if missing_tags:
                    raise ValidationException(
                        "源产品缺少受控承认标签：" + ", ".join(missing_tags)
                    )
                processing_level = tags["PROCESSING_LEVEL"].upper()
                if processing_level != expected_processing_level.upper():
                    raise ValidationException("源文件处理级别与承认请求不一致")
                if not tags["PLATFORM"].upper().startswith("SENTINEL-2"):
                    raise ValidationException("当前仅支持 Sentinel-2 L2A 源级承认")
                if tags["INSTRUMENT"].upper() != "MSI":
                    raise ValidationException("Sentinel-2 源产品载荷必须为 MSI")
                if tags["SOURCE_SCALE_APPLIED"].lower() != "true":
                    raise ValidationException("源文件尚未应用 STAC 反射率标度")
                if tags["REFLECTANCE_QUANTITY"].upper() != "BOA_REFLECTANCE":
                    raise ValidationException("源文件不是 L2A 地表反射率")
                if any(dtype not in {"float32", "float64"} for dtype in dataset.dtypes):
                    raise ValidationException("源文件像元尚未转换为浮点反射率")
                if tags.get("SECURITY_CLASSIFICATION", "").lower() == "public":
                    public_missing = [
                        key
                        for key in ("STAC_ITEM_ID", "SOURCE_LICENSE_URL")
                        if not tags.get(key)
                    ]
                    if public_missing:
                        raise ValidationException(
                            "公开源产品缺少来源许可标签："
                            + ", ".join(public_missing)
                        )
                return {
                    "platform": tags["PLATFORM"],
                    "instrument": tags["INSTRUMENT"],
                    "processing_level": processing_level,
                    "source_provider": tags["SOURCE_PROVIDER"],
                    "source_product_uri": tags["SOURCE_PRODUCT_URI"],
                    "source_processing_baseline": tags[
                        "SOURCE_PROCESSING_BASELINE"
                    ],
                    "stac_item_id": tags.get("STAC_ITEM_ID"),
                    "source_license_url": tags.get("SOURCE_LICENSE_URL"),
                    "security_classification": tags.get(
                        "SECURITY_CLASSIFICATION"
                    ),
                    "source_scale_applied": True,
                    "reflectance_quantity": tags["REFLECTANCE_QUANTITY"],
                    "raster_width": dataset.width,
                    "raster_height": dataset.height,
                    "band_count": dataset.count,
                    "dtypes": list(dataset.dtypes),
                    "crs": dataset.crs.to_string() if dataset.crs else None,
                    "band_descriptions": list(dataset.descriptions),
                }
        except RasterioIOError as exc:
            raise ValidationException("源产品无法由 Rasterio 读取") from exc

    @staticmethod
    def _update_asset_status(asset: object, step_code: str) -> None:
        """根据真实完成步骤更新资产处理状态。

        Args:
            asset: 影像资产 ORM 对象。
            step_code: 已完成步骤编码。

        Returns:
            None: 无返回值。
        """
        if step_code == "radiometric":
            asset.calibration_status = "completed"
            asset.correction_status = "pending"
        if step_code == "atmospheric":
            asset.correction_status = "in_progress"
        if step_code == "geometric":
            asset.correction_status = "completed"

    @staticmethod
    def _invalidate_downstream_steps(
        asset: object,
        steps: list[object],
        completed_step: object,
    ) -> list[str]:
        """重跑上游步骤时失效下游产物并保留历史证据。

        Args:
            asset: 当前影像资产。
            steps: 资产全部处理步骤。
            completed_step: 本次重新完成的步骤。

        Returns:
            list[str]: 被失效的下游步骤编码。
        """
        invalidated: list[str] = []
        superseded_at = datetime.now(UTC).isoformat()
        for downstream in steps:
            if downstream.sequence <= completed_step.sequence:
                continue
            parameters = dict(downstream.parameters or {})
            old_evidence = parameters.pop("artifact_evidence", None)
            if old_evidence:
                history = list(parameters.get("artifact_history") or [])
                history.append({
                    **old_evidence,
                    "superseded_at": superseded_at,
                    "superseded_by_step": completed_step.step_code,
                })
                parameters["artifact_history"] = history
            downstream.parameters = parameters
            downstream.status = "pending"
            downstream.progress = 0
            downstream.output_uri = None
            downstream.started_at = None
            downstream.completed_at = None
            invalidated.append(downstream.step_code)
        if completed_step.step_code == "radiometric":
            asset.correction_status = "pending"
        elif completed_step.step_code == "atmospheric":
            asset.correction_status = "in_progress"
        return invalidated

    async def _persist_step_completion(
        self,
        db: AsyncSession,
        task: object,
        asset: object,
        step: object,
        relative_path: str,
        processor_name: str,
        processor_version: str,
        operator: object,
        comment: str | None,
        evidence_extra: dict | None = None,
        action: str = "processing_step_completed",
    ) -> None:
        """保存处理产物证据、状态和不可变审核记录。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。
            asset: 当前影像资产。
            step: 已完成步骤。
            relative_path: 产物受控相对路径。
            processor_name: 处理器名称。
            processor_version: 处理器版本。
            operator: 已通过能力校验的项目用户。
            comment: 处理说明。
            evidence_extra: 内置处理器输出的附加证据。
            action: 审核动作编码。

        Returns:
            None: 完成数据库持久化后返回。
        """
        artifact_path = self._resolve_artifact_path(relative_path)
        file_size_bytes = artifact_path.stat().st_size
        checksum_sha256 = await asyncio.to_thread(calculate_sha256, artifact_path)
        now = datetime.now(UTC)
        step.status = "completed"
        step.progress = 100
        step.started_at = step.started_at or now
        step.completed_at = now
        step.updated_at = now
        step.output_uri = f"storage://imagery/{relative_path}"
        parameters = dict(step.parameters or {})
        parameters["artifact_evidence"] = {
            "relative_path": relative_path,
            "file_size_bytes": file_size_bytes,
            "checksum_sha256": checksum_sha256,
            "processor_name": processor_name,
            "processor_version": processor_version,
            "registered_at": now.isoformat(),
            **(evidence_extra or {}),
        }
        step.parameters = parameters
        self._update_asset_status(asset, step.step_code)
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="imagery_processing",
                action=action,
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=(
                    f"{asset.asset_code}/{step.step_name} - "
                    f"产物 {relative_path}，SHA256 {checksum_sha256} - "
                    f"{comment or '处理产物校验完成'}"
                ),
            ),
        )
        await db.commit()

    async def get_processing(
        self,
        db: AsyncSession,
        asset_code: str,
    ) -> ImageryProcessingResponse:
        """获取影像元数据和预处理步骤状态。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。

        Returns:
            ImageryProcessingResponse: 影像处理聚合信息。
        """
        asset = await self.dao.get_asset_by_code(db, asset_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        step_responses = [self._to_step_response(step) for step in steps]
        completion_rate = (
            round(
                sum(100 for step in step_responses if step.output_verified)
                / len(step_responses),
                2,
            )
            if step_responses
            else 0
        )
        return ImageryProcessingResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            sensor_type=asset.sensor_type,
            acquired_at=asset.acquired_at,
            cloud_cover=(
                float(asset.cloud_cover) if asset.cloud_cover is not None else None
            ),
            resolution_m=(
                float(asset.resolution_m) if asset.resolution_m is not None else None
            ),
            processing_level=asset.processing_level,
            completion_rate=completion_rate,
            completed_steps=sum(step.output_verified for step in step_responses),
            total_steps=len(step_responses),
            steps=step_responses,
        )

    async def run_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImageryStepRunRequest,
    ) -> ImageryProcessingResponse:
        """校验并登记指定预处理步骤的实体产物与审计日志。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 处理步骤编号。
            task_code: 作业任务编号。
            request: 操作人和说明。

        Returns:
            ImageryProcessingResponse: 更新后的处理流水线。
        """
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        blockers = [
            item
            for item in steps
            if item.sequence < step.sequence
            and not self._inspect_step_artifact(item)[0]
        ]
        if blockers:
            raise ValidationException(
                f"请先登记并校验步骤产物：{blockers[0].step_name}"
            )
        artifact_path = self._resolve_artifact_path(request.output_relative_path)
        if not artifact_path.is_file():
            raise ValidationException("指定影像产物不存在，不能标记步骤完成")
        file_size_bytes = artifact_path.stat().st_size
        if file_size_bytes <= 0:
            raise ValidationException("指定影像产物为空文件")
        if not has_supported_raster_signature(artifact_path):
            raise ValidationException("影像产物文件头与扩展名声明的格式不一致")
        invalidated_steps = self._invalidate_downstream_steps(asset, steps, step)
        await self._persist_step_completion(
            db,
            task,
            asset,
            step,
            request.output_relative_path,
            request.processor_name,
            request.processor_version,
            operator,
            request.comment,
            evidence_extra={
                "execution_mode": "external_registration",
                "invalidated_downstream_steps": invalidated_steps,
            },
        )
        return await self.get_processing(db, asset_code)

    async def execute_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImageryStepExecuteRequest,
    ) -> ImageryProcessingResponse:
        """使用平台内置处理器执行步骤并保存实体产物证据。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 标准处理步骤编号。
            task_code: 作业任务编号。
            request: 操作人编码、处理参数和说明。

        Returns:
            ImageryProcessingResponse: 执行后的完整流水线状态。
        """
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        source_path = self._resolve_step_source_path(asset, steps, step)
        boundary_geometry = None
        if step_code == "clip":
            boundary_code = str(request.parameters.get("boundary_code") or "")
            geometry_text = await self.dao.get_boundary_geometry(
                db,
                asset.project_id,
                boundary_code,
            )
            if geometry_text is None:
                raise ValidationException("未找到当前项目的行政区裁剪边界")
            boundary_geometry = json.loads(geometry_text)
        relative_path = (
            Path("processed")
            / asset.asset_code
            / (
                f"{step.sequence:02d}_{step.step_code}_"
                f"{uuid4().hex[:12]}.tif"
            )
        ).as_posix()
        output_path = self._resolve_artifact_path(relative_path)
        source_checksum = await asyncio.to_thread(calculate_sha256, source_path)
        try:
            result = await asyncio.to_thread(
                self.processing_engine.execute,
                step_code,
                source_path,
                output_path,
                request.parameters,
                boundary_geometry,
            )
            invalidated_steps = self._invalidate_downstream_steps(
                asset,
                steps,
                step,
            )
            await self._persist_step_completion(
                db,
                task,
                asset,
                step,
                relative_path,
                self.processing_engine.processor_name,
                self.processing_engine.processor_version,
                operator,
                request.comment,
                evidence_extra={
                    "execution_mode": "built_in",
                    "source_relative_path": source_path.relative_to(
                        self.storage_dir
                    ).as_posix(),
                    "source_checksum_sha256": source_checksum,
                    "execution_parameters": result.parameters,
                    "output_width": result.width,
                    "output_height": result.height,
                    "output_band_count": result.band_count,
                    "output_dtype": result.dtype,
                    "output_crs": result.crs,
                    "invalidated_downstream_steps": invalidated_steps,
                },
                action="processing_step_executed",
            )
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        return await self.get_processing(db, asset_code)

    async def accept_source_level_step(
        self,
        db: AsyncSession,
        asset_code: str,
        step_code: str,
        task_code: str,
        request: ImagerySourceLevelAcceptRequest,
    ) -> ImageryProcessingResponse:
        """用物理 L2A 源产品证据满足定标或大气校正要求。

        Args:
            db: 异步数据库会话。
            asset_code: 影像资产编号。
            step_code: 仅允许辐射定标或大气校正。
            task_code: 作业任务编号。
            request: 稳定用户、预期级别、无算法确认和承认依据。

        Returns:
            ImageryProcessingResponse: 承认后的完整流水线状态。
        """
        acceptance_basis = self.SOURCE_LEVEL_ACCEPTANCE_STEPS.get(step_code)
        if acceptance_basis is None:
            raise ValidationException("源产品级别只能承认辐射定标或大气校正步骤")
        asset = await self.dao.get_asset_by_code_for_update(db, asset_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if asset is None:
            raise NotFoundException(f"未找到影像资产 {asset_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != asset.project_id:
            raise ValidationException("作业任务与影像资产不属于同一项目")
        if str(asset.processing_level or "").upper() != (
            request.expected_processing_level
        ):
            raise ValidationException("资产处理级别与源产品承认请求不一致")
        operator = await self.project_user_service.require_capability(
            db,
            asset.project_id,
            request.operator_code,
            "process_imagery",
        )
        step = await self.dao.get_step_for_update(db, asset.id, step_code)
        if step is None:
            raise NotFoundException(f"未找到处理步骤 {step_code}")
        steps = list(await self.dao.get_steps(db, asset.id))
        source_path = self._resolve_step_source_path(asset, steps, step)
        source_evidence = await asyncio.to_thread(
            self._inspect_source_level_evidence,
            source_path,
            request.expected_processing_level,
        )
        invalidated_steps = self._invalidate_downstream_steps(asset, steps, step)
        relative_path = source_path.relative_to(self.storage_dir).as_posix()
        await self._persist_step_completion(
            db,
            task,
            asset,
            step,
            relative_path,
            "受控源产品级别承认",
            "sentinel-l2a-source-acceptance-v1",
            operator,
            request.justification,
            evidence_extra={
                "execution_mode": "source_level_acceptance",
                "algorithm_executed": False,
                "expected_processing_level": request.expected_processing_level,
                "acceptance_basis": acceptance_basis,
                "source_evidence": source_evidence,
                "invalidated_downstream_steps": invalidated_steps,
            },
            action="source_level_accepted",
        )
        return await self.get_processing(db, asset_code)
