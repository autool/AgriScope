"""无人机航空器、飞行任务、实体成果和疑点审核业务服务。"""

import asyncio
import math
import mimetypes
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import rasterio
from geoalchemy2.elements import WKTElement
from rasterio.warp import transform_bounds
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.uav_dao import ArtifactRecord, FindingRecord, MissionRecord, UavDAO
from app.models.uav import UavAircraft, UavArtifact, UavEvent, UavFinding, UavMission
from app.models.workbench import MonitoringProject, MonitoringTask, ProjectUser
from app.schemas.uav import (
    AircraftCreateRequest,
    AircraftResponse,
    ArtifactResponse,
    ArtifactUploadRequest,
    FindingCreateRequest,
    FindingResponse,
    FindingReviewRequest,
    MissionCreateRequest,
    MissionResponse,
    MissionStatusRequest,
    UavEventResponse,
    UavOverviewResponse,
)
from app.services.project_user_service import ProjectUserService


@dataclass(frozen=True)
class StoredUpload:
    """受控目录内完成大小与 SHA-256 校验的上传文件。"""

    path: Path
    relative_path: Path
    original_filename: str
    file_size_bytes: int
    checksum_sha256: str
    suffix: str
    created_new: bool


@dataclass(frozen=True)
class RasterInspection:
    """无人机正射或 DEM 实体栅格检查结果。"""

    driver: str
    crs: str
    resolution_cm: float
    width: int
    height: int
    footprint_wkt: str
    footprint_geojson: dict
    metadata: dict


@dataclass(frozen=True)
class ArtifactDownload:
    """通过实体大小和 SHA-256 复核的成果下载信息。"""

    path: Path
    filename: str
    media_type: str
    checksum_sha256: str


ARTIFACT_SUFFIXES: dict[str, set[str]] = {
    "raw_imagery": {".zip", ".tif", ".tiff", ".jpg", ".jpeg"},
    "flight_log": {".csv", ".json", ".gpx", ".txt", ".zip"},
    "photo": {".jpg", ".jpeg", ".png", ".tif", ".tiff"},
    "video": {".mp4", ".mov", ".avi"},
    "orthomosaic": {".tif", ".tiff"},
    "dem": {".tif", ".tiff"},
    "report": {".pdf", ".json", ".csv", ".docx"},
}


class UavService:
    """编排 UAV 身份、范围、文件、状态门禁和疑点复核。"""

    def __init__(
        self,
        dao: UavDAO | None = None,
        user_service: ProjectUserService | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化无人机业务服务。

        Args:
            dao: 无人机 DAO。
            user_service: 项目身份服务。
            storage_root: 可注入的受控存储根目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or UavDAO()
        self.user_service = user_service or ProjectUserService()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "uav"
        )

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str | None = None,
    ) -> tuple[MonitoringProject, MonitoringTask | None]:
        """解析项目与可选任务并验证归属。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 可选作业任务编号。

        Returns:
            tuple[MonitoringProject, MonitoringTask | None]: 项目和任务。
        """
        project = await self.dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task_code is None:
            return project, None
        task = await self.dao.get_task_by_code(db, task_code)
        if task is None or task.project_id != project.id:
            raise NotFoundException(f"项目内未找到任务 {task_code}")
        return project, task

    @staticmethod
    def _event(
        project_id: int,
        mission_id: int | None,
        entity_type: str,
        entity_code: str,
        event_type: str,
        detail: dict,
        user: ProjectUser,
    ) -> UavEvent:
        """构造稳定身份无人机审计事件。

        Args:
            project_id: 项目主键。
            mission_id: 可选任务主键。
            entity_type: 实体类型。
            entity_code: 实体编号。
            event_type: 事件类型。
            detail: 结构化证据。
            user: 项目用户。

        Returns:
            UavEvent: 未持久化审计事件。
        """
        return UavEvent(
            project_id=project_id,
            mission_id=mission_id,
            entity_type=entity_type,
            entity_code=entity_code,
            event_type=event_type,
            detail=detail,
            actor=user.display_name,
            actor_code=user.user_code,
            actor_role=user.role_code,
        )

    def _store_upload(
        self,
        file_handle: BinaryIO,
        original_filename: str,
        scope: Path,
        allowed_suffixes: set[str],
        max_bytes: int | None = None,
    ) -> StoredUpload:
        """原子保存上传文件并由服务端计算大小和 SHA-256。

        Args:
            file_handle: 上传二进制流。
            original_filename: 原始文件名。
            scope: 存储相对目录。
            allowed_suffixes: 允许扩展名集合。
            max_bytes: 可选的当前业务文件大小上限。

        Returns:
            StoredUpload: 受控上传结果。
        """
        safe_name = Path(original_filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in allowed_suffixes:
            allowed = "、".join(sorted(allowed_suffixes))
            raise ValidationException(f"文件格式不受支持，仅允许 {allowed}")
        storage_root = self.storage_root.resolve()
        upload_dir = (storage_root / ".uploads").resolve()
        upload_dir.mkdir(parents=True, exist_ok=True)
        temporary_path = upload_dir / f"{uuid4().hex}{suffix}.part"
        file_size = 0
        size_limit = max_bytes or settings.max_uav_upload_bytes
        file_handle.seek(0)
        try:
            with temporary_path.open("wb") as output:
                while chunk := file_handle.read(1024 * 1024):
                    file_size += len(chunk)
                    if file_size > size_limit:
                        raise ValidationException(
                            "无人机文件超过平台允许的最大上传大小"
                        )
                    output.write(chunk)
            if file_size == 0:
                raise ValidationException("上传文件为空")
            checksum = calculate_sha256(temporary_path)
            relative_path = scope / f"{checksum[:16]}_{safe_name}"
            final_path = (storage_root / relative_path).resolve()
            if not final_path.is_relative_to(storage_root):
                raise ValidationException("无人机文件存储路径不合法")
            created_new = not final_path.exists()
            if not created_new:
                if final_path.stat().st_size != file_size or calculate_sha256(
                    final_path
                ) != checksum:
                    raise ValidationException("目标文件已存在但实体校验值不一致")
                temporary_path.unlink(missing_ok=True)
            else:
                final_path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(temporary_path, final_path)
            return StoredUpload(
                path=final_path,
                relative_path=relative_path,
                original_filename=safe_name,
                file_size_bytes=file_size,
                checksum_sha256=checksum,
                suffix=suffix,
                created_new=created_new,
            )
        finally:
            temporary_path.unlink(missing_ok=True)

    def _require_verified_artifact_path(self, artifact: UavArtifact) -> Path:
        """重新校验无人机成果受控路径、大小和 SHA-256。

        Args:
            artifact: 无人机实体成果记录。

        Returns:
            Path: 已通过完整性复核的实体路径。
        """
        prefix = "storage://uav/"
        if not artifact.file_uri.startswith(prefix):
            raise ValidationException("无人机成果不在受控存储中")
        path = (
            self.storage_root / artifact.file_uri.removeprefix(prefix)
        ).resolve()
        if not path.is_relative_to(self.storage_root.resolve()) or not path.is_file():
            raise ValidationException("无人机成果实体文件缺失")
        if path.stat().st_size != artifact.file_size_bytes:
            raise ValidationException("无人机成果实体大小已变化")
        if calculate_sha256(path) != artifact.checksum_sha256:
            raise ValidationException("无人机成果实体 SHA-256 校验失败")
        return path

    @staticmethod
    def _inspect_raster(path: Path) -> RasterInspection:
        """读取正射或 DEM 实体栅格的空间结构和 WGS84 覆盖范围。

        Args:
            path: 实体栅格路径。

        Returns:
            RasterInspection: 栅格检查结果。
        """
        try:
            with rasterio.open(path) as dataset:
                if dataset.crs is None:
                    raise ValidationException("无人机栅格缺少 CRS，不能作为空间成果")
                left, bottom, right, top = transform_bounds(
                    dataset.crs,
                    "EPSG:4326",
                    *dataset.bounds,
                    densify_pts=21,
                )
                if not all(
                    math.isfinite(value)
                    for value in (left, bottom, right, top)
                ):
                    raise ValidationException("无人机栅格 WGS84 覆盖范围不合法")
                if dataset.crs.is_projected:
                    _, factor = dataset.crs.linear_units_factor
                    resolution_m = max(abs(value) for value in dataset.res) * factor
                else:
                    center_latitude = math.radians((bottom + top) / 2)
                    x_resolution = abs(right - left) / max(dataset.width, 1)
                    y_resolution = abs(top - bottom) / max(dataset.height, 1)
                    resolution_m = max(
                        x_resolution * 111_320 * math.cos(center_latitude),
                        y_resolution * 110_540,
                    )
                footprint_wkt = (
                    f"POLYGON(({left} {bottom},{right} {bottom},"
                    f"{right} {top},{left} {top},{left} {bottom}))"
                )
                footprint_geojson = {
                    "type": "Polygon",
                    "coordinates": [[
                        [left, bottom],
                        [right, bottom],
                        [right, top],
                        [left, top],
                        [left, bottom],
                    ]],
                }
                return RasterInspection(
                    driver=dataset.driver,
                    crs=dataset.crs.to_string(),
                    resolution_cm=round(resolution_m * 100, 3),
                    width=dataset.width,
                    height=dataset.height,
                    footprint_wkt=footprint_wkt,
                    footprint_geojson=footprint_geojson,
                    metadata={
                        "band_count": dataset.count,
                        "dtypes": list(dataset.dtypes),
                        "bounds_wgs84": [left, bottom, right, top],
                    },
                )
        except rasterio.errors.RasterioError as exc:
            raise ValidationException("无法读取无人机栅格实体") from exc

    @staticmethod
    def _aircraft_response(aircraft: UavAircraft) -> AircraftResponse:
        """转换航空器响应。

        Args:
            aircraft: 航空器模型。

        Returns:
            AircraftResponse: 航空器响应。
        """
        return AircraftResponse.model_validate(aircraft, from_attributes=True)

    @staticmethod
    def _mission_response(record: MissionRecord) -> MissionResponse:
        """转换任务响应。

        Args:
            record: 带关联身份的任务记录。

        Returns:
            MissionResponse: 任务响应。
        """
        mission = record.mission
        return MissionResponse(
            mission_code=mission.mission_code,
            mission_name=mission.mission_name,
            task_code=record.task_code,
            aircraft_code=record.aircraft_code,
            aircraft_name=record.aircraft_name,
            district_code=mission.district_code,
            district_name=mission.district_name,
            flight_boundary=record.boundary_geojson,
            planned_area_ha=float(mission.planned_area_ha),
            pilot_name=mission.pilot_name,
            pilot_license_number=mission.pilot_license_number,
            pilot_license_uri=mission.pilot_license_uri,
            pilot_license_filename=mission.pilot_license_filename,
            pilot_license_size_bytes=mission.pilot_license_size_bytes,
            pilot_license_sha256=mission.pilot_license_sha256,
            planned_start_at=mission.planned_start_at,
            planned_end_at=mission.planned_end_at,
            actual_start_at=mission.actual_start_at,
            actual_end_at=mission.actual_end_at,
            altitude_m=float(mission.altitude_m),
            expected_resolution_cm=float(mission.expected_resolution_cm),
            forward_overlap_percent=float(mission.forward_overlap_percent),
            side_overlap_percent=float(mission.side_overlap_percent),
            weather_note=mission.weather_note,
            status=mission.status,
            cancellation_reason=mission.cancellation_reason,
            created_by=mission.created_by,
            created_by_code=mission.created_by_code,
            created_by_role=mission.created_by_role,
            created_at=mission.created_at,
        )

    @staticmethod
    def _artifact_response(record: ArtifactRecord) -> ArtifactResponse:
        """转换实体成果响应。

        Args:
            record: 带任务和覆盖范围的成果记录。

        Returns:
            ArtifactResponse: 成果响应。
        """
        artifact = record.artifact
        return ArtifactResponse(
            mission_code=record.mission_code,
            artifact_code=artifact.artifact_code,
            artifact_type=artifact.artifact_type,
            original_filename=artifact.original_filename,
            file_uri=artifact.file_uri,
            file_size_bytes=artifact.file_size_bytes,
            checksum_sha256=artifact.checksum_sha256,
            captured_at=artifact.captured_at,
            file_format=artifact.file_format,
            crs=artifact.crs,
            resolution_cm=(
                float(artifact.resolution_cm)
                if artifact.resolution_cm is not None
                else None
            ),
            raster_width=artifact.raster_width,
            raster_height=artifact.raster_height,
            footprint=record.footprint_geojson,
            metadata=artifact.metadata_json or {},
            verification_status=artifact.verification_status,
            uploaded_by=artifact.uploaded_by,
            uploaded_by_code=artifact.uploaded_by_code,
            uploaded_by_role=artifact.uploaded_by_role,
            created_at=artifact.created_at,
        )

    @staticmethod
    def _finding_response(record: FindingRecord) -> FindingResponse:
        """转换疑点响应。

        Args:
            record: 带任务和成果编号的疑点记录。

        Returns:
            FindingResponse: 疑点响应。
        """
        finding = record.finding
        return FindingResponse(
            mission_code=record.mission_code,
            artifact_code=record.artifact_code,
            finding_code=finding.finding_code,
            finding_type=finding.finding_type,
            severity=finding.severity,
            longitude=float(finding.longitude),
            latitude=float(finding.latitude),
            plot_code=finding.plot_code,
            description=finding.description,
            status=finding.status,
            created_by=finding.created_by,
            created_by_code=finding.created_by_code,
            created_by_role=finding.created_by_role,
            review_comment=finding.review_comment,
            reviewed_by=finding.reviewed_by,
            reviewed_by_code=finding.reviewed_by_code,
            reviewed_by_role=finding.reviewed_by_role,
            reviewed_at=finding.reviewed_at,
            created_at=finding.created_at,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> UavOverviewResponse:
        """查询无人机资源、任务、实体成果和疑点真实总览。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 当前用户编码。

        Returns:
            UavOverviewResponse: 无人机工作台总览。
        """
        project, _ = await self._resolve_context(db, project_code)
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "view_uav",
        )
        aircraft = list(await self.dao.list_aircraft(db, project.id))
        missions = await self.dao.list_mission_records(db, project.id)
        artifacts = await self.dao.list_artifact_records(db, project.id)
        findings = await self.dao.list_finding_records(db, project.id)
        events = list(await self.dao.list_events(db, project.id))
        return UavOverviewResponse(
            aircraft_count=len(aircraft),
            mission_count=len(missions),
            active_mission_count=sum(
                record.mission.status in {"planned", "in_progress"}
                for record in missions
            ),
            pending_processing_count=sum(
                record.mission.status == "captured" for record in missions
            ),
            pending_finding_count=sum(
                record.finding.status == "pending_review" for record in findings
            ),
            verified_artifact_count=sum(
                record.artifact.verification_status == "verified"
                for record in artifacts
            ),
            aircraft=[self._aircraft_response(item) for item in aircraft],
            missions=[self._mission_response(item) for item in missions],
            artifacts=[self._artifact_response(item) for item in artifacts],
            findings=[self._finding_response(item) for item in findings],
            events=[
                UavEventResponse(
                    entity_type=item.entity_type,
                    entity_code=item.entity_code,
                    event_type=item.event_type,
                    detail=item.detail or {},
                    actor=item.actor,
                    actor_code=item.actor_code,
                    actor_role=item.actor_role,
                    created_at=item.created_at,
                )
                for item in events
            ],
        )

    async def register_aircraft(
        self,
        db: AsyncSession,
        project_code: str,
        request: AircraftCreateRequest,
        certificate_filename: str,
        certificate_file: BinaryIO,
    ) -> AircraftResponse:
        """上传证书实体并登记航空器和传感器身份。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            request: 航空器和操作人信息。
            certificate_filename: 证书原始文件名。
            certificate_file: 证书二进制流。

        Returns:
            AircraftResponse: 已登记航空器。
        """
        project, _ = await self._resolve_context(db, project_code)
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_uav_aircraft",
        )
        if await self.dao.get_aircraft_by_code(
            db,
            project.id,
            request.aircraft_code,
        ):
            raise ValidationException("航空器编号已存在")
        stored = await asyncio.to_thread(
            self._store_upload,
            certificate_file,
            certificate_filename,
            Path("aircraft") / request.aircraft_code,
            {".pdf", ".jpg", ".jpeg", ".png"},
        )
        try:
            aircraft = await self.dao.add_aircraft(
                db,
                UavAircraft(
                    project_id=project.id,
                    aircraft_code=request.aircraft_code,
                    aircraft_name=request.aircraft_name,
                    manufacturer=request.manufacturer,
                    model_number=request.model_number,
                    serial_number=request.serial_number,
                    registration_number=request.registration_number,
                    sensor_name=request.sensor_name,
                    sensor_model=request.sensor_model,
                    sensor_serial_number=request.sensor_serial_number,
                    owner_department=request.owner_department,
                    certificate_uri=f"storage://uav/{stored.relative_path.as_posix()}",
                    certificate_filename=stored.original_filename,
                    certificate_size_bytes=stored.file_size_bytes,
                    certificate_sha256=stored.checksum_sha256,
                    status=request.status,
                    registered_by=user.display_name,
                    registered_by_code=user.user_code,
                    registered_by_role=user.role_code,
                ),
            )
            await self.dao.add_event(
                db,
                self._event(
                    project.id,
                    None,
                    "aircraft",
                    aircraft.aircraft_code,
                    "aircraft_registered",
                    {
                        "registration_number": aircraft.registration_number,
                        "sensor_serial_number": aircraft.sensor_serial_number,
                        "certificate_sha256": aircraft.certificate_sha256,
                    },
                    user,
                ),
            )
            await db.commit()
            return self._aircraft_response(aircraft)
        except SQLAlchemyError:
            await db.rollback()
            if stored.created_new:
                stored.path.unlink(missing_ok=True)
            raise

    async def create_mission(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: MissionCreateRequest,
        license_filename: str,
        license_file: BinaryIO,
    ) -> MissionResponse:
        """创建边界完全位于真实县区的飞行任务。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            request: 飞行范围、参数和飞手信息。
            license_filename: 飞手资质原始文件名。
            license_file: 飞手资质二进制流。

        Returns:
            MissionResponse: 已创建飞行任务。
        """
        project, task = await self._resolve_context(db, project_code, task_code)
        assert task is not None
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_uav_missions",
        )
        if await self.dao.get_mission_by_code(
            db,
            project.id,
            request.mission_code,
        ):
            raise ValidationException("无人机任务编号已存在")
        aircraft = await self.dao.get_aircraft_by_code(
            db,
            project.id,
            request.aircraft_code,
        )
        if aircraft is None:
            raise NotFoundException("未找到任务航空器")
        if aircraft.status != "active":
            raise ValidationException("只有活动航空器可以创建飞行任务")
        stored = await asyncio.to_thread(
            self._store_upload,
            license_file,
            license_filename,
            Path("missions") / request.mission_code / "pilot",
            {".pdf", ".jpg", ".jpeg", ".png"},
        )
        try:
            mission = await self.dao.create_mission_with_validated_boundary(
                db,
                project_id=project.id,
                task_id=task.id,
                aircraft_id=aircraft.id,
                mission=UavMission(
                    project_id=project.id,
                    task_id=task.id,
                    aircraft_id=aircraft.id,
                    mission_code=request.mission_code,
                    mission_name=request.mission_name,
                    district_code=request.district_code,
                    pilot_name=request.pilot_name,
                    pilot_license_number=request.pilot_license_number,
                    pilot_license_uri=(
                        f"storage://uav/{stored.relative_path.as_posix()}"
                    ),
                    pilot_license_filename=stored.original_filename,
                    pilot_license_size_bytes=stored.file_size_bytes,
                    pilot_license_sha256=stored.checksum_sha256,
                    planned_start_at=request.planned_start_at,
                    planned_end_at=request.planned_end_at,
                    altitude_m=Decimal(str(request.altitude_m)),
                    expected_resolution_cm=Decimal(
                        str(request.expected_resolution_cm)
                    ),
                    forward_overlap_percent=Decimal(
                        str(request.forward_overlap_percent)
                    ),
                    side_overlap_percent=Decimal(
                        str(request.side_overlap_percent)
                    ),
                    weather_note=request.weather_note,
                    status="planned",
                    created_by=user.display_name,
                    created_by_code=user.user_code,
                    created_by_role=user.role_code,
                ),
                boundary_geojson=request.flight_boundary,
            )
            if mission is None:
                raise ValidationException("飞行范围无效或未完全位于申报县区内")
            await self.dao.add_event(
                db,
                self._event(
                    project.id,
                    mission.id,
                    "mission",
                    mission.mission_code,
                    "mission_created",
                    {
                        "district_code": mission.district_code,
                        "aircraft_code": aircraft.aircraft_code,
                        "planned_area_ha": float(mission.planned_area_ha),
                        "pilot_license_sha256": mission.pilot_license_sha256,
                    },
                    user,
                ),
            )
            await db.commit()
            records = await self.dao.list_mission_records(db, project.id)
            record = next(
                item
                for item in records
                if item.mission.mission_code == mission.mission_code
            )
            return self._mission_response(record)
        except (SQLAlchemyError, ValidationException):
            await db.rollback()
            if stored.created_new:
                stored.path.unlink(missing_ok=True)
            raise

    async def upload_artifact(
        self,
        db: AsyncSession,
        project_code: str,
        mission_code: str,
        request: ArtifactUploadRequest,
        original_filename: str,
        file_handle: BinaryIO,
    ) -> ArtifactResponse:
        """上传任务实体成果并执行格式、栅格和覆盖范围校验。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            mission_code: 无人机任务编号。
            request: 成果类型、采集时间和来源元数据。
            original_filename: 上传原始文件名。
            file_handle: 文件二进制流。

        Returns:
            ArtifactResponse: 已校验成果。
        """
        project, _ = await self._resolve_context(db, project_code)
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "operate_uav_missions",
        )
        mission = await self.dao.get_mission_by_code(
            db,
            project.id,
            mission_code,
        )
        if mission is None:
            raise NotFoundException("未找到无人机任务")
        if mission.status in {"reviewed", "cancelled"}:
            raise ValidationException("已结束任务不能继续上传成果")
        if await self.dao.get_artifact_by_code(
            db,
            mission.id,
            request.artifact_code,
        ):
            raise ValidationException("任务成果编号已存在")
        stored = await asyncio.to_thread(
            self._store_upload,
            file_handle,
            original_filename,
            Path("missions") / mission.mission_code / "artifacts",
            ARTIFACT_SUFFIXES[request.artifact_type],
        )
        try:
            inspection = None
            if request.artifact_type in {"orthomosaic", "dem"}:
                inspection = await asyncio.to_thread(
                    self._inspect_raster,
                    stored.path,
                )
            metadata = {
                **request.metadata,
                "source_name": request.source_name,
                "source_version": request.source_version,
            }
            if inspection:
                metadata = {**metadata, **inspection.metadata}
            artifact = await self.dao.add_artifact(
                db,
                UavArtifact(
                    mission_id=mission.id,
                    artifact_code=request.artifact_code,
                    artifact_type=request.artifact_type,
                    original_filename=stored.original_filename,
                    file_uri=f"storage://uav/{stored.relative_path.as_posix()}",
                    file_size_bytes=stored.file_size_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    captured_at=request.captured_at,
                    file_format=(
                        inspection.driver if inspection else stored.suffix.lstrip(".")
                    ),
                    crs=inspection.crs if inspection else None,
                    resolution_cm=(
                        Decimal(str(inspection.resolution_cm)) if inspection else None
                    ),
                    raster_width=inspection.width if inspection else None,
                    raster_height=inspection.height if inspection else None,
                    footprint=(
                        WKTElement(inspection.footprint_wkt, srid=4326)
                        if inspection
                        else None
                    ),
                    metadata_json=metadata,
                    verification_status="verified",
                    uploaded_by=user.display_name,
                    uploaded_by_code=user.user_code,
                    uploaded_by_role=user.role_code,
                ),
            )
            if request.artifact_type == "orthomosaic":
                covers_mission = await self.dao.artifact_footprint_covers_mission(
                    db,
                    artifact.id,
                    mission.id,
                )
                if not covers_mission:
                    raise ValidationException("正射成果未完整覆盖无人机任务范围")
            await self.dao.add_event(
                db,
                self._event(
                    project.id,
                    mission.id,
                    "artifact",
                    artifact.artifact_code,
                    "artifact_uploaded",
                    {
                        "artifact_type": artifact.artifact_type,
                        "file_size_bytes": artifact.file_size_bytes,
                        "checksum_sha256": artifact.checksum_sha256,
                        "crs": artifact.crs,
                        "resolution_cm": (
                            float(artifact.resolution_cm)
                            if artifact.resolution_cm is not None
                            else None
                        ),
                    },
                    user,
                ),
            )
            await db.commit()
            records = await self.dao.list_artifact_records(db, project.id)
            record = next(
                item
                for item in records
                if item.artifact.id == artifact.id
            )
            return self._artifact_response(record)
        except (SQLAlchemyError, ValidationException):
            await db.rollback()
            if stored.created_new:
                stored.path.unlink(missing_ok=True)
            raise

    async def transition_mission(
        self,
        db: AsyncSession,
        project_code: str,
        mission_code: str,
        request: MissionStatusRequest,
    ) -> MissionResponse:
        """按实体成果和疑点门禁执行任务状态动作。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            mission_code: 任务编号。
            request: 状态动作、说明和实际时间。

        Returns:
            MissionResponse: 更新后的任务。
        """
        project, _ = await self._resolve_context(db, project_code)
        capability = (
            "review_uav_findings"
            if request.action == "complete_review"
            else "operate_uav_missions"
        )
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            capability,
        )
        mission = await self.dao.get_mission_by_code(
            db,
            project.id,
            mission_code,
            for_update=True,
        )
        if mission is None:
            raise NotFoundException("未找到无人机任务")
        transitions = {
            "start": ("planned", "in_progress"),
            "complete_capture": ("in_progress", "captured"),
            "complete_processing": ("captured", "processed"),
            "complete_review": ("processed", "reviewed"),
        }
        if request.action == "cancel":
            if mission.status in {"reviewed", "cancelled"}:
                raise ValidationException("当前任务状态不能取消")
            mission.status = "cancelled"
            mission.cancellation_reason = request.comment
        else:
            expected, target = transitions[request.action]
            if mission.status != expected:
                raise ValidationException(
                    f"任务当前状态 {mission.status} 不能执行 {request.action}"
                )
            artifacts = [
                item
                for item in await self.dao.list_artifact_records(db, project.id)
                if item.artifact.mission_id == mission.id
            ]
            artifact_types = {
                item.artifact.artifact_type
                for item in artifacts
                if item.artifact.verification_status == "verified"
            }
            if request.action == "complete_capture" and not {
                "raw_imagery",
                "flight_log",
            }.issubset(artifact_types):
                raise ValidationException("完成采集前必须上传原始影像和航迹实体")
            if request.action == "complete_processing":
                orthomosaics = [
                    item.artifact
                    for item in artifacts
                    if item.artifact.artifact_type == "orthomosaic"
                    and item.artifact.verification_status == "verified"
                ]
                if not orthomosaics:
                    raise ValidationException("完成处理前必须上传已校验正射成果")
                best_resolution = min(
                    float(item.resolution_cm)
                    for item in orthomosaics
                    if item.resolution_cm is not None
                )
                if best_resolution > float(mission.expected_resolution_cm) * 1.2:
                    raise ValidationException("正射成果分辨率未达到任务计划要求")
            if request.action == "complete_review":
                pending_findings = await self.dao.count_pending_findings(
                    db,
                    mission.id,
                )
                if pending_findings:
                    raise ValidationException("仍有无人机疑点未完成人工复核")
            mission.status = target
            actual_time = request.actual_time or datetime.now(UTC)
            if request.action == "start":
                mission.actual_start_at = actual_time
            if request.action == "complete_capture":
                mission.actual_end_at = actual_time
        await self.dao.add_event(
            db,
            self._event(
                project.id,
                mission.id,
                "mission",
                mission.mission_code,
                "mission_status_changed",
                {
                    "action": request.action,
                    "status": mission.status,
                    "comment": request.comment,
                },
                user,
            ),
        )
        await db.commit()
        records = await self.dao.list_mission_records(db, project.id)
        record = next(
            item
            for item in records
            if item.mission.mission_code == mission.mission_code
        )
        return self._mission_response(record)

    async def create_finding(
        self,
        db: AsyncSession,
        project_code: str,
        mission_code: str,
        request: FindingCreateRequest,
    ) -> FindingResponse:
        """登记范围内、证据可追溯的无人机空间疑点。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            mission_code: 任务编号。
            request: 疑点位置、类型和证据成果。

        Returns:
            FindingResponse: 待人工复核疑点。
        """
        project, _ = await self._resolve_context(db, project_code)
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "operate_uav_missions",
        )
        mission = await self.dao.get_mission_by_code(
            db,
            project.id,
            mission_code,
        )
        if mission is None:
            raise NotFoundException("未找到无人机任务")
        if mission.status not in {"captured", "processed"}:
            raise ValidationException("只有已采集或已处理任务可以登记疑点")
        if await self.dao.get_finding_by_code(
            db,
            mission.id,
            request.finding_code,
        ):
            raise ValidationException("无人机疑点编号已存在")
        artifact = await self.dao.get_artifact_by_code(
            db,
            mission.id,
            request.artifact_code,
        )
        if artifact is None or artifact.verification_status != "verified":
            raise ValidationException("疑点必须绑定任务内已校验实体成果")
        if not await self.dao.point_within_mission(
            db,
            mission.id,
            request.longitude,
            request.latitude,
        ):
            raise ValidationException("疑点坐标不在无人机任务范围内")
        if request.plot_code and not await self.dao.plot_belongs_to_task(
            db,
            mission.task_id,
            request.plot_code,
        ):
            raise ValidationException("关联图斑不属于当前作业任务")
        finding = await self.dao.add_finding(
            db,
            UavFinding(
                mission_id=mission.id,
                artifact_id=artifact.id,
                finding_code=request.finding_code,
                finding_type=request.finding_type,
                severity=request.severity,
                longitude=Decimal(str(request.longitude)),
                latitude=Decimal(str(request.latitude)),
                plot_code=request.plot_code,
                description=request.description,
                status="pending_review",
                created_by=user.display_name,
                created_by_code=user.user_code,
                created_by_role=user.role_code,
            ),
        )
        await self.dao.add_event(
            db,
            self._event(
                project.id,
                mission.id,
                "finding",
                finding.finding_code,
                "finding_created",
                {
                    "artifact_code": artifact.artifact_code,
                    "longitude": float(finding.longitude),
                    "latitude": float(finding.latitude),
                    "plot_code": finding.plot_code,
                },
                user,
            ),
        )
        await db.commit()
        return self._finding_response(
            FindingRecord(
                finding=finding,
                mission_code=mission.mission_code,
                artifact_code=artifact.artifact_code,
            )
        )

    async def review_finding(
        self,
        db: AsyncSession,
        project_code: str,
        mission_code: str,
        finding_code: str,
        request: FindingReviewRequest,
    ) -> FindingResponse:
        """人工确认或排除无人机疑点并保留稳定身份。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            mission_code: 任务编号。
            finding_code: 疑点编号。
            request: 复核结论、说明和操作人。

        Returns:
            FindingResponse: 已复核疑点。
        """
        project, _ = await self._resolve_context(db, project_code)
        user = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "review_uav_findings",
        )
        mission = await self.dao.get_mission_by_code(
            db,
            project.id,
            mission_code,
        )
        if mission is None:
            raise NotFoundException("未找到无人机任务")
        finding = await self.dao.get_finding_by_code(
            db,
            mission.id,
            finding_code,
            for_update=True,
        )
        if finding is None:
            raise NotFoundException("未找到无人机疑点")
        if finding.status != "pending_review":
            raise ValidationException("无人机疑点已经完成复核")
        finding.status = "confirmed" if request.decision == "confirm" else "dismissed"
        finding.review_comment = request.comment
        finding.reviewed_by = user.display_name
        finding.reviewed_by_code = user.user_code
        finding.reviewed_by_role = user.role_code
        finding.reviewed_at = datetime.now(UTC)
        await self.dao.add_event(
            db,
            self._event(
                project.id,
                mission.id,
                "finding",
                finding.finding_code,
                "finding_reviewed",
                {
                    "decision": request.decision,
                    "comment": request.comment,
                },
                user,
            ),
        )
        await db.commit()
        records = await self.dao.list_finding_records(db, project.id)
        record = next(
            item
            for item in records
            if item.finding.id == finding.id
        )
        return self._finding_response(record)

    async def get_artifact_download(
        self,
        db: AsyncSession,
        project_code: str,
        artifact_code: str,
        operator_code: str,
    ) -> ArtifactDownload:
        """复核实体大小和 SHA-256 后返回成果下载信息。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            artifact_code: 成果编号。
            operator_code: 当前用户编码。

        Returns:
            ArtifactDownload: 已校验下载信息。
        """
        project, _ = await self._resolve_context(db, project_code)
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "download_uav_artifacts",
        )
        records = await self.dao.list_artifact_records(db, project.id)
        record = next(
            (
                item
                for item in records
                if item.artifact.artifact_code == artifact_code
            ),
            None,
        )
        if record is None:
            raise NotFoundException("未找到无人机实体成果")
        artifact = record.artifact
        path = await asyncio.to_thread(
            self._require_verified_artifact_path,
            artifact,
        )
        media_type = mimetypes.guess_type(artifact.original_filename)[0]
        return ArtifactDownload(
            path=path,
            filename=artifact.original_filename,
            media_type=media_type or "application/octet-stream",
            checksum_sha256=artifact.checksum_sha256,
        )
