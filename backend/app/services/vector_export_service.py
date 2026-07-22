"""任务作用域多格式矢量成果生成、校验、下载与审计服务。"""

import asyncio
import json
import os
import secrets
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.vector_export_dao import VectorExportDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.vector_export import VectorExportPackage
from app.models.workbench import ReviewRecord
from app.schemas.vector_export import (
    VectorExportFilterOption,
    VectorExportGenerateRequest,
    VectorExportListResponse,
    VectorExportManifestFile,
    VectorExportOptionsResponse,
    VectorExportPackageResponse,
)
from app.services.project_user_service import ProjectUserService
from app.services.vector_export_renderer import VectorExportRenderer

MAX_VECTOR_EXPORT_FEATURES = 100_000
SUPPORTED_VECTOR_FORMATS = ["geojson", "shapefile", "kml", "filegdb"]
SUPPORTED_LAND_CLASSES = {"耕地", "园地", "林地", "草地", "水域", "建设用地"}


@dataclass(frozen=True)
class VectorExportDownload:
    """通过权限与实体复核的矢量成果下载信息。"""

    path: Path
    filename: str
    checksum_sha256: str


class VectorExportService:
    """生成真实 GeoJSON、Shapefile、KML 和 FileGDB 成果包。"""

    def __init__(
        self,
        dao: VectorExportDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        renderer: VectorExportRenderer | None = None,
        storage_root: Path | None = None,
    ) -> None:
        """初始化矢量成果导出服务。

        Args:
            dao: 矢量导出 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目用户能力服务。
            renderer: 多格式实体渲染器。
            storage_root: 可注入受控存储根目录。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or VectorExportDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.renderer = renderer or VectorExportRenderer()
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "vector-exports"
        )

    def _resolve_path(self, relative_path: str) -> Path:
        """解析并约束矢量成果受控路径。

        Args:
            relative_path: 相对于存储根目录的路径。

        Returns:
            Path: 未越界绝对路径。
        """
        root = self.storage_root.resolve()
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValidationException("矢量成果导出存储路径越界")
        return path

    @staticmethod
    def _same_datetime(left: datetime, right: datetime) -> bool:
        """比较可能由数据库驱动返回的时区时间。

        Args:
            left: 左侧时间。
            right: 右侧时间。

        Returns:
            bool: 表示同一时刻时为真。
        """
        left_value = left if left.tzinfo else left.replace(tzinfo=UTC)
        right_value = right if right.tzinfo else right.replace(tzinfo=UTC)
        return left_value.astimezone(UTC) == right_value.astimezone(UTC)

    @classmethod
    def get_stale_reason(
        cls,
        package: VectorExportPackage,
        task: object,
        current_task_plot_count: int,
    ) -> str | None:
        """判断导出包是否仍对应当前任务数据版本。

        Args:
            package: 导出包模型。
            task: 当前作业任务。
            current_task_plot_count: 当前任务有效图斑数。

        Returns:
            str | None: 失效原因；当前有效时为空。
        """
        if package.status == "invalid":
            return "导出包实体已损坏或缺失"
        if package.status == "superseded":
            return "导出包已被新版本替代"
        if package.status != "completed":
            return "导出包未处于已完成状态"
        if package.task_plot_count != current_task_plot_count:
            return "任务有效图斑数量在导出后发生变化"
        if not cls._same_datetime(
            package.task_updated_at_snapshot,
            task.updated_at,
        ):
            return "任务图斑或属性在导出后发生更新"
        return None

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        """解析 manifest 中的 ISO 时间。

        Args:
            value: JSON 时间值。

        Returns:
            datetime: 解析后的时间。
        """
        if not isinstance(value, str):
            raise ValidationException("矢量成果 manifest 时间字段类型不合法")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationException("矢量成果 manifest 时间格式不合法") from exc

    @classmethod
    def _validate_manifest(
        cls,
        package: VectorExportPackage,
        manifest: dict,
        member_contents: dict[str, bytes],
    ) -> None:
        """交叉校验 manifest、数据库快照和 ZIP 成员。

        Args:
            package: 导出包模型。
            manifest: ZIP 内 manifest。
            member_contents: 不含 manifest 的成员字节。

        Returns:
            None: 证据一致时无返回值。
        """
        if (
            manifest.get("schema_version") != "vector-export-v1"
            or manifest.get("export_code") != package.export_code
            or manifest.get("version") != package.version
            or manifest.get("feature_count") != package.feature_count
            or manifest.get("formats") != package.formats
        ):
            raise ValidationException("矢量成果 manifest 身份或数量不一致")
        filters = manifest.get("filters")
        if (
            not isinstance(filters, dict)
            or filters.get("district_codes") != package.district_codes
            or filters.get("land_classes") != package.land_classes
        ):
            raise ValidationException("矢量成果 manifest 筛选快照不一致")
        task_snapshot = manifest.get("task")
        if (
            not isinstance(task_snapshot, dict)
            or task_snapshot.get("task_plot_count") != package.task_plot_count
            or not cls._same_datetime(
                cls._parse_datetime(
                    task_snapshot.get("task_updated_at_snapshot")
                ),
                package.task_updated_at_snapshot,
            )
        ):
            raise ValidationException("矢量成果 manifest 任务快照不一致")
        files = manifest.get("files")
        if not isinstance(files, list) or len(files) != len(member_contents):
            raise ValidationException("矢量成果 manifest 文件清单不完整")
        file_map = {
            item.get("path"): item
            for item in files
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        if set(file_map) != set(member_contents):
            raise ValidationException("矢量成果 manifest 文件名不一致")
        for path, content in member_contents.items():
            item = file_map[path]
            if (
                item.get("file_size_bytes") != len(content)
                or item.get("checksum_sha256") != sha256(content).hexdigest()
            ):
                raise ValidationException(
                    f"矢量成果 manifest 文件证据不一致：{path}"
                )

    def verify_package_file(self, package: VectorExportPackage) -> Path:
        """复核 ZIP、逐成员校验值和四种真实格式可读性。

        Args:
            package: 导出包模型。

        Returns:
            Path: 已验证 ZIP 路径。
        """
        prefix = "storage://vector-exports/"
        if not package.file_uri.startswith(prefix):
            raise ValidationException("矢量成果导出未登记受控文件地址")
        path = self._resolve_path(package.file_uri.removeprefix(prefix))
        if not path.is_file():
            raise NotFoundException("矢量成果导出实体不存在")
        if path.stat().st_size != package.file_size_bytes:
            raise ValidationException("矢量成果导出 ZIP 大小校验失败")
        if path.read_bytes()[:4] != b"PK\x03\x04":
            raise ValidationException("矢量成果导出不是有效 ZIP")
        if calculate_sha256(path) != package.checksum_sha256:
            raise ValidationException("矢量成果导出 ZIP SHA-256 校验失败")
        try:
            with ZipFile(path) as archive:
                names = archive.namelist()
                if (
                    len(names) > 256
                    or len(names) != len(set(names))
                    or "manifest.json" not in names
                    or any(
                        name.startswith("/")
                        or ".." in Path(name).parts
                        for name in names
                    )
                ):
                    raise ValidationException("矢量成果 ZIP 成员路径不安全")
                manifest = json.loads(
                    archive.read("manifest.json").decode("utf-8")
                )
                member_contents = {
                    name: archive.read(name)
                    for name in names
                    if name != "manifest.json"
                }
        except (BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("矢量成果 ZIP 或 manifest 结构损坏") from exc
        if manifest != package.export_manifest:
            raise ValidationException("矢量成果 manifest 与数据库快照不一致")
        self._validate_manifest(package, manifest, member_contents)
        with tempfile.TemporaryDirectory(prefix="agriscope-vector-verify-") as temp:
            root = Path(temp)
            for name, content in member_contents.items():
                target = (root / name).resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValidationException("矢量成果解压路径越界")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self.renderer.validate_directory(
                root,
                package.formats,
                package.feature_count,
            )
        return path

    def read_verified_members(
        self,
        package: VectorExportPackage,
    ) -> dict[str, bytes]:
        """读取已通过完整格式复核的 ZIP 成员。

        Args:
            package: 导出包模型。

        Returns:
            dict[str, bytes]: 以归档相对路径索引的成员。
        """
        path = self.verify_package_file(package)
        with ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}

    async def require_current_package(
        self,
        db: AsyncSession,
        package: VectorExportPackage,
        task: object,
    ) -> None:
        """要求导出包仍对应当前任务版本。

        Args:
            db: 异步数据库会话。
            package: 待归档导出包。
            task: 当前作业任务。

        Returns:
            None: 当前有效时无返回值。
        """
        current_count = await self.dao.count_features(db, task.id)
        stale_reason = self.get_stale_reason(package, task, current_count)
        if stale_reason is not None:
            raise ValidationException(f"矢量成果导出已失效：{stale_reason}")

    def _to_response(
        self,
        package: VectorExportPackage,
        task: object,
        current_task_plot_count: int,
    ) -> VectorExportPackageResponse:
        """转换导出包响应并计算动态失效状态。

        Args:
            package: 导出包模型。
            task: 当前作业任务。
            current_task_plot_count: 当前任务有效图斑数。

        Returns:
            VectorExportPackageResponse: 前端版本摘要。
        """
        stale_reason = self.get_stale_reason(
            package,
            task,
            current_task_plot_count,
        )
        effective_status = package.status
        if effective_status == "completed" and stale_reason is not None:
            effective_status = "superseded"
        is_current = effective_status == "completed" and stale_reason is None
        return VectorExportPackageResponse(
            export_code=package.export_code,
            export_title=package.export_title,
            version=package.version,
            status=effective_status,
            formats=package.formats,
            district_codes=package.district_codes,
            land_classes=package.land_classes,
            feature_count=package.feature_count,
            task_plot_count=package.task_plot_count,
            task_updated_at_snapshot=package.task_updated_at_snapshot,
            file_size_bytes=package.file_size_bytes,
            checksum_sha256=package.checksum_sha256,
            files=[
                VectorExportManifestFile(**item)
                for item in package.export_manifest.get("files", [])
            ],
            generation_comment=package.generation_comment,
            generated_by=package.generated_by,
            generated_by_code=package.generated_by_code,
            generated_by_role=package.generated_by_role,
            generated_at=package.generated_at,
            download_url=(
                f"/api/v1/vector-exports/{package.export_code}/download"
                if package.status != "invalid"
                else None
            ),
            is_current=is_current,
            stale_reason=stale_reason,
        )

    async def list_packages(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> VectorExportListResponse:
        """查询导出历史，不扫描全部历史 ZIP。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            VectorExportListResponse: 当前与历史导出版本。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        current_count = await self.dao.count_features(db, task.id)
        packages = await self.dao.list_packages(db, task.id)
        return VectorExportListResponse(
            task_code=task_code,
            items=[
                self._to_response(package, task, current_count)
                for package in packages
            ],
        )

    async def get_options(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> VectorExportOptionsResponse:
        """查询真实县区、地类范围和格式能力。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            VectorExportOptionsResponse: 前端筛选项和数量门禁。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        total_count = await self.dao.count_features(db, task.id)
        district_rows = await self.dao.get_district_options(db, task.id)
        land_rows = await self.dao.get_land_class_options(db, task.id)
        return VectorExportOptionsResponse(
            task_code=task_code,
            total_feature_count=total_count,
            max_feature_count=MAX_VECTOR_EXPORT_FEATURES,
            supported_formats=SUPPORTED_VECTOR_FORMATS,
            districts=[
                VectorExportFilterOption(
                    code=row.code,
                    label=row.label,
                    parent_label=row.parent_label,
                    feature_count=int(row.feature_count),
                )
                for row in district_rows
                if row.code is not None
            ],
            land_classes=[
                VectorExportFilterOption(
                    label=row.label,
                    feature_count=int(row.feature_count),
                )
                for row in land_rows
                if row.label in SUPPORTED_LAND_CLASSES
            ],
        )

    async def generate_package(
        self,
        db: AsyncSession,
        task_code: str,
        request: VectorExportGenerateRequest,
    ) -> VectorExportPackageResponse:
        """生成真实多格式矢量成果 ZIP。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 格式、筛选、标题和审计依据。

        Returns:
            VectorExportPackageResponse: 新生成导出包。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "generate_vector_export",
        )
        task_plot_count = await self.dao.count_features(db, task.id)
        feature_count = await self.dao.count_features(
            db,
            task.id,
            request.district_codes,
            request.land_classes,
        )
        if feature_count <= 0:
            raise ValidationException("当前筛选条件没有可导出的任务图斑")
        if feature_count > MAX_VECTOR_EXPORT_FEATURES:
            raise ValidationException(
                f"当前筛选命中 {feature_count} 个图斑，超过单包 "
                f"{MAX_VECTOR_EXPORT_FEATURES} 个上限，请按县区或地类拆分"
            )
        rows = list(
            await self.dao.get_export_rows(
                db,
                task.id,
                request.district_codes,
                request.land_classes,
            )
        )
        if len(rows) != feature_count:
            raise ValidationException("导出范围在生成期间发生变化，请重新发起")
        version = await self.dao.get_next_version(db, task.id)
        generated_at = datetime.now(UTC)
        export_code = (
            f"VEXP-{task_code}-V{version:03d}-"
            f"{generated_at:%Y%m%dT%H%M%S}-{secrets.token_hex(4)}"
        )
        content, manifest = await asyncio.to_thread(
            self.renderer.build_archive,
            rows,
            request.formats,
            request.district_codes,
            request.land_classes,
            task,
            task_plot_count,
            export_code,
            request.export_title,
            version,
            generated_at,
            operator,
            request.comment,
        )
        relative_path = f"{task_code}/{export_code}.zip"
        final_path = self._resolve_path(relative_path)
        temporary_path = self._resolve_path(
            f"{task_code}/.{export_code}.{secrets.token_hex(6)}.tmp"
        )
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(temporary_path.write_bytes, content)
            await asyncio.to_thread(os.replace, temporary_path, final_path)
        except OSError as exc:
            await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
            raise ValidationException("矢量成果导出原子发布失败") from exc
        package = VectorExportPackage(
            task_id=task.id,
            export_code=export_code,
            export_title=request.export_title,
            version=version,
            status="completed",
            formats=request.formats,
            district_codes=request.district_codes,
            land_classes=request.land_classes,
            feature_count=feature_count,
            task_plot_count=task_plot_count,
            task_updated_at_snapshot=task.updated_at,
            file_uri=f"storage://vector-exports/{relative_path}",
            file_size_bytes=final_path.stat().st_size,
            checksum_sha256=calculate_sha256(final_path),
            export_manifest=manifest,
            generation_comment=request.comment,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generated_at=generated_at,
        )
        try:
            superseded_count = await self.dao.supersede_completed_packages(
                db,
                task.id,
            )
            package = await self.dao.add_package(db, package)
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="vector_export",
                    action="vector_export_generated",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"生成矢量成果 {export_code} V{version}；"
                        f"格式 {request.formats}；图斑 {feature_count} 个；"
                        f"县区筛选 {request.district_codes or '全部'}；"
                        f"地类筛选 {request.land_classes or '全部'}；"
                        f"替代历史版本 {superseded_count} 个；"
                        f"ZIP SHA256 {package.checksum_sha256}；"
                        f"{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except SQLAlchemyError:
            await db.rollback()
            await asyncio.to_thread(final_path.unlink, missing_ok=True)
            raise
        return self._to_response(package, task, task_plot_count)

    async def authorize_download(
        self,
        db: AsyncSession,
        export_code: str,
        requester_code: str,
    ) -> VectorExportDownload:
        """鉴权、复核并审计矢量成果下载。

        Args:
            db: 异步数据库会话。
            export_code: 导出包业务编号。
            requester_code: 下载人稳定用户编码。

        Returns:
            VectorExportDownload: 已验证下载信息。
        """
        package = await self.dao.get_package_by_code(db, export_code)
        if package is None:
            raise NotFoundException(f"未找到矢量成果导出 {export_code}")
        task = await self.workbench_dao.get_task_by_id(db, package.task_id)
        if task is None:
            raise NotFoundException("矢量成果导出关联任务不存在")
        requester = await self.project_user_service.require_capability(
            db,
            task.project_id,
            requester_code,
            "download_vector_export",
        )
        try:
            path = await asyncio.to_thread(self.verify_package_file, package)
        except (NotFoundException, ValidationException):
            package.status = "invalid"
            await db.commit()
            raise
        current_count = await self.dao.count_features(db, task.id)
        stale_reason = self.get_stale_reason(package, task, current_count)
        if package.status == "completed" and stale_reason is not None:
            package.status = "superseded"
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="vector_export",
                action="vector_export_downloaded",
                reviewer=requester.display_name,
                reviewer_code=requester.user_code,
                reviewer_role=requester.role_code,
                comment=(
                    f"下载矢量成果 {package.export_code} V{package.version}；"
                    f"状态 {package.status}；ZIP SHA256 {package.checksum_sha256}"
                ),
            ),
        )
        await db.commit()
        return VectorExportDownload(
            path=path,
            filename=f"{package.export_code}.zip",
            checksum_sha256=package.checksum_sha256,
        )
