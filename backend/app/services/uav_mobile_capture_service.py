"""无人机移动端 GPS、照片实体和空间疑点原子采集服务。"""

import asyncio
import hashlib
import json
import math
import warnings
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import BinaryIO

from PIL import Image, UnidentifiedImageError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.dao.uav_dao import ArtifactRecord, FindingRecord
from app.models.uav import UavArtifact, UavFinding
from app.schemas.uav import (
    MobileUavCaptureOverviewResponse,
    MobileUavCaptureRequest,
    MobileUavCaptureResponse,
)
from app.services.uav_service import UavService


class UavMobileCaptureService(UavService):
    """把移动端一次现场采集原子保存为照片实体和空间疑点。"""

    @staticmethod
    def _inspect_mobile_photo(path: Path) -> dict:
        """校验移动端照片签名、编码格式和像素尺寸。

        Args:
            path: 已落入受控目录的候选照片。

        Returns:
            dict: 图像格式和像素尺寸证据。
        """
        expected_formats = {
            ".jpg": "JPEG",
            ".jpeg": "JPEG",
            ".png": "PNG",
            ".webp": "WEBP",
        }
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image_format = (image.format or "").upper()
                    width, height = image.size
                    image.verify()
        except (
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
            OSError,
        ) as exc:
            raise ValidationException("移动采集照片不是安全有效的图像实体") from exc
        expected_format = expected_formats.get(path.suffix.lower())
        if expected_format is None or image_format != expected_format:
            raise ValidationException("移动采集照片扩展名与图像签名不一致")
        if width <= 0 or height <= 0:
            raise ValidationException("移动采集照片像素尺寸不合法")
        return {
            "image_format": image_format,
            "image_width": width,
            "image_height": height,
        }

    @staticmethod
    def _capture_codes(capture_code: str) -> tuple[str, str]:
        """为移动采集生成稳定照片和疑点编号。

        Args:
            capture_code: 移动端稳定幂等编号。

        Returns:
            tuple[str, str]: 照片成果编号和疑点编号。
        """
        return f"UAVMOB-A-{capture_code}", f"UAVMOB-F-{capture_code}"

    @staticmethod
    def _capture_digest(
        mission_code: str,
        request: MobileUavCaptureRequest,
    ) -> str:
        """计算移动采集规范化载荷摘要。

        Args:
            mission_code: 无人机任务编号。
            request: GPS、疑点和稳定操作人载荷。

        Returns:
            str: SHA-256 十六进制摘要。
        """
        payload = {
            "schema_version": "uav-mobile-capture-v1",
            "mission_code": mission_code,
            "capture_code": request.capture_code,
            "captured_at": request.captured_at.astimezone(UTC).isoformat(),
            "longitude": round(request.longitude, 8),
            "latitude": round(request.latitude, 8),
            "location_accuracy_m": round(request.location_accuracy_m, 2),
            "finding_type": request.finding_type,
            "severity": request.severity,
            "plot_code": request.plot_code,
            "description": request.description,
            "device_label": request.device_label,
            "operator_code": request.operator_code,
        }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _replay_matches(
        artifact: UavArtifact,
        finding: UavFinding,
        request: MobileUavCaptureRequest,
        payload_sha256: str,
        photo_sha256: str,
    ) -> bool:
        """判断同一移动采集编号是否为完全一致的安全重试。

        Args:
            artifact: 已存在照片实体。
            finding: 已存在空间疑点。
            request: 本次规范化业务载荷。
            payload_sha256: 本次载荷摘要。
            photo_sha256: 本次照片摘要。

        Returns:
            bool: 载荷、照片和关联对象完全一致时为真。
        """
        metadata = artifact.metadata_json or {}
        return (
            artifact.artifact_type == "photo"
            and artifact.verification_status == "verified"
            and artifact.checksum_sha256 == photo_sha256
            and metadata.get("mobile_capture_payload_sha256") == payload_sha256
            and finding.artifact_id == artifact.id
            and finding.finding_type == request.finding_type
            and finding.severity == request.severity
            and finding.plot_code == request.plot_code
            and finding.description == request.description
            and finding.created_by_code == request.operator_code
            and math.isclose(
                float(finding.longitude),
                request.longitude,
                abs_tol=1e-8,
            )
            and math.isclose(
                float(finding.latitude),
                request.latitude,
                abs_tol=1e-8,
            )
        )

    async def get_capture_overview(
        self,
        db: AsyncSession,
        project_code: str,
        operator_code: str,
    ) -> MobileUavCaptureOverviewResponse:
        """查询当前操作人可执行移动采集的轻量任务列表。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            operator_code: 移动采集人稳定编码。

        Returns:
            MobileUavCaptureOverviewResponse: 已启动或待处理的任务列表。
        """
        project, _ = await self._resolve_context(db, project_code)
        await self.user_service.require_capability(
            db,
            project.id,
            operator_code,
            "operate_uav_missions",
        )
        records = await self.dao.list_mission_records(db, project.id)
        eligible_records = [
            record
            for record in records
            if record.mission.status in {"in_progress", "captured", "processed"}
        ]
        return MobileUavCaptureOverviewResponse(
            project_code=project_code,
            mission_count=len(eligible_records),
            missions=[
                self._mission_response(record) for record in eligible_records
            ],
        )

    async def create_capture(
        self,
        db: AsyncSession,
        project_code: str,
        mission_code: str,
        request: MobileUavCaptureRequest,
        original_filename: str,
        photo_file: BinaryIO,
    ) -> MobileUavCaptureResponse:
        """原子保存移动 GPS、照片实体、疑点和审计事件。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            mission_code: 已启动的无人机任务编号。
            request: GPS、疑点、终端和幂等编号。
            original_filename: 照片原始文件名。
            photo_file: 相机或相册选择的照片二进制流。

        Returns:
            MobileUavCaptureResponse: 实体照片、空间疑点和重放状态。
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
            for_update=True,
        )
        if mission is None:
            raise NotFoundException("未找到无人机任务")
        if mission.status not in {"in_progress", "captured", "processed"}:
            raise ValidationException("任务启动后才能使用移动端采集疑点")
        if not await self.dao.point_within_mission(
            db,
            mission.id,
            request.longitude,
            request.latitude,
        ):
            raise ValidationException("移动采集坐标不在无人机任务范围内")
        if request.plot_code and not await self.dao.plot_belongs_to_task(
            db,
            mission.task_id,
            request.plot_code,
        ):
            raise ValidationException("关联图斑不属于当前作业任务")

        artifact_code, finding_code = self._capture_codes(request.capture_code)
        payload_sha256 = self._capture_digest(mission_code, request)
        existing_artifact = await self.dao.get_artifact_by_code(
            db,
            mission.id,
            artifact_code,
        )
        existing_finding = await self.dao.get_finding_by_code(
            db,
            mission.id,
            finding_code,
        )
        existing_path: Path | None = None
        if (existing_artifact is None) != (existing_finding is None):
            raise ValidationException("移动采集幂等记录不完整，禁止覆盖原证据")
        if existing_artifact is not None:
            existing_path = await asyncio.to_thread(
                self._require_verified_artifact_path,
                existing_artifact,
            )

        stored = await asyncio.to_thread(
            self._store_upload,
            photo_file,
            original_filename,
            Path("missions") / mission.mission_code / "mobile-captures",
            {".jpg", ".jpeg", ".png", ".webp"},
            settings.max_uav_mobile_photo_bytes,
        )
        try:
            photo_metadata = await asyncio.to_thread(
                self._inspect_mobile_photo,
                stored.path,
            )
            if existing_artifact is not None and existing_finding is not None:
                if not self._replay_matches(
                    existing_artifact,
                    existing_finding,
                    request,
                    payload_sha256,
                    stored.checksum_sha256,
                ):
                    raise ValidationException(
                        "移动采集编号已存在且载荷或照片不一致"
                    )
                if stored.created_new and stored.path != existing_path:
                    stored.path.unlink(missing_ok=True)
                await db.commit()
                return MobileUavCaptureResponse(
                    capture_code=request.capture_code,
                    artifact=self._artifact_response(
                        ArtifactRecord(
                            artifact=existing_artifact,
                            mission_code=mission.mission_code,
                            footprint_geojson=None,
                        )
                    ),
                    finding=self._finding_response(
                        FindingRecord(
                            finding=existing_finding,
                            mission_code=mission.mission_code,
                            artifact_code=existing_artifact.artifact_code,
                        )
                    ),
                    idempotent_replay=True,
                )

            metadata = {
                "source_name": "AgriScope 无人机移动采集端",
                "source_version": "uav-mobile-capture-v1",
                "capture_channel": "mobile_browser",
                "capture_code": request.capture_code,
                "mobile_capture_payload_sha256": payload_sha256,
                "device_label": request.device_label,
                "location": {
                    "longitude": round(request.longitude, 8),
                    "latitude": round(request.latitude, 8),
                    "horizontal_accuracy_m": round(
                        request.location_accuracy_m,
                        2,
                    ),
                },
                **photo_metadata,
            }
            artifact = await self.dao.add_artifact(
                db,
                UavArtifact(
                    mission_id=mission.id,
                    artifact_code=artifact_code,
                    artifact_type="photo",
                    original_filename=stored.original_filename,
                    file_uri=f"storage://uav/{stored.relative_path.as_posix()}",
                    file_size_bytes=stored.file_size_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    captured_at=request.captured_at,
                    file_format=photo_metadata["image_format"].lower(),
                    crs=None,
                    resolution_cm=None,
                    raster_width=photo_metadata["image_width"],
                    raster_height=photo_metadata["image_height"],
                    footprint=None,
                    metadata_json=metadata,
                    verification_status="verified",
                    uploaded_by=user.display_name,
                    uploaded_by_code=user.user_code,
                    uploaded_by_role=user.role_code,
                ),
            )
            finding = await self.dao.add_finding(
                db,
                UavFinding(
                    mission_id=mission.id,
                    artifact_id=artifact.id,
                    finding_code=finding_code,
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
                    "artifact",
                    artifact.artifact_code,
                    "mobile_photo_uploaded",
                    {
                        "capture_code": request.capture_code,
                        "file_size_bytes": artifact.file_size_bytes,
                        "checksum_sha256": artifact.checksum_sha256,
                        "payload_sha256": payload_sha256,
                        "location_accuracy_m": request.location_accuracy_m,
                    },
                    user,
                ),
            )
            await self.dao.add_event(
                db,
                self._event(
                    project.id,
                    mission.id,
                    "finding",
                    finding.finding_code,
                    "mobile_finding_created",
                    {
                        "capture_code": request.capture_code,
                        "artifact_code": artifact.artifact_code,
                        "longitude": float(finding.longitude),
                        "latitude": float(finding.latitude),
                        "plot_code": finding.plot_code,
                    },
                    user,
                ),
            )
            await db.commit()
            return MobileUavCaptureResponse(
                capture_code=request.capture_code,
                artifact=self._artifact_response(
                    ArtifactRecord(
                        artifact=artifact,
                        mission_code=mission.mission_code,
                        footprint_geojson=None,
                    )
                ),
                finding=self._finding_response(
                    FindingRecord(
                        finding=finding,
                        mission_code=mission.mission_code,
                        artifact_code=artifact.artifact_code,
                    )
                ),
                idempotent_replay=False,
            )
        except (SQLAlchemyError, ValidationException):
            await db.rollback()
            if stored.created_new:
                stored.path.unlink(missing_ok=True)
            raise
