"""双时相真实栅格公共网格预览、缓存清单与图片读取服务。"""

import asyncio
import json
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode

import rasterio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.change_detection_dao import ChangeDetectionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.change_detection import ChangeDetectionRun
from app.models.workbench import ImageryAsset
from app.schemas.change_detection import (
    ChangeComparisonMetadataResponse,
    ChangeComparisonSourceResponse,
)
from app.services.change_comparison_renderer import ChangeComparisonRenderer
from app.services.imagery_asset_service import ImageryAssetService
from app.services.imagery_registration_service import ImageryRegistrationService


@dataclass(frozen=True)
class CachedChangeComparison:
    """已校验缓存元数据、图片路径和 ETag。"""

    metadata: ChangeComparisonMetadataResponse
    baseline_path: Path
    target_path: Path
    baseline_etag: str
    target_etag: str


class ChangeComparisonService:
    """生成并读取带来源校验与公共网格参数的双时相预览。"""

    def __init__(
        self,
        dao: ChangeDetectionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        imagery_service: ImageryAssetService | None = None,
        registration_service: ImageryRegistrationService | None = None,
        renderer: ChangeComparisonRenderer | None = None,
    ) -> None:
        """初始化双时相预览服务。

        Args:
            dao: 变化检测 DAO。
            workbench_dao: 项目任务公共 DAO。
            imagery_service: 影像实体路径校验服务。
            registration_service: 配准成果实体校验服务。
            renderer: 栅格公共网格渲染器。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ChangeDetectionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.imagery_service = imagery_service or ImageryAssetService()
        self.registration_service = (
            registration_service or ImageryRegistrationService()
        )
        self.renderer = renderer or ChangeComparisonRenderer()
        self.preview_root = (
            Path(__file__).resolve().parents[2]
            / "storage"
            / "change_detection"
            / "previews"
        )
        self._run_locks: dict[int, asyncio.Lock] = {}

    async def _resolve_context(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
    ) -> tuple[object, object, ChangeDetectionRun]:
        """解析项目、任务和任务作用域内检测任务。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 变化检测任务编号。

        Returns:
            tuple[object, object, ChangeDetectionRun]: 项目、任务和检测任务。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        run = await self.dao.get_run_by_code(db, task.id, run_code)
        if run is None:
            raise NotFoundException(f"未找到变化检测任务 {run_code}")
        if run.project_id != project.id:
            raise NotFoundException(f"未找到变化检测任务 {run_code}")
        return project, task, run

    async def _resolve_run_assets(
        self,
        db: AsyncSession,
        project_id: int,
        run: ChangeDetectionRun,
    ) -> tuple[ImageryAsset, ImageryAsset]:
        """查询并复核检测任务绑定的两期业务影像。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            run: 变化检测任务。

        Returns:
            tuple[ImageryAsset, ImageryAsset]: 前后时相影像。
        """
        assets = await self.dao.get_imagery_assets_by_ids(
            db,
            project_id,
            [run.baseline_asset_id, run.target_asset_id],
        )
        assets_by_id = {asset.id: asset for asset in assets}
        baseline = assets_by_id.get(run.baseline_asset_id)
        target = assets_by_id.get(run.target_asset_id)
        if baseline is None or target is None:
            raise ValidationException("检测任务绑定影像已不存在或不属于当前项目")
        for label, asset in (("前时相", baseline), ("后时相", target)):
            if asset.data_status != "operational":
                raise ValidationException(f"{label}演示影像不能生成正式对比预览")
            if not asset.checksum_sha256 or asset.file_size_bytes is None:
                raise ValidationException(f"{label}影像缺少实体校验值或文件大小")
            if (
                asset.calibration_status != "completed"
                or asset.correction_status != "completed"
            ):
                raise ValidationException(f"{label}影像预处理尚未完成")
        snapshot = run.source_snapshot or {}
        if (
            snapshot.get("baseline", {}).get("checksum_sha256")
            != baseline.checksum_sha256
            or snapshot.get("target", {}).get("checksum_sha256")
            != target.checksum_sha256
        ):
            raise ValidationException("检测任务影像快照与当前资产校验值不一致")
        return baseline, target

    @staticmethod
    def _source_state(
        asset: ImageryAsset,
        path: Path,
        checksum_sha256: str | None = None,
        evidence_type: str = "imagery_asset",
    ) -> dict[str, object]:
        """提取参与缓存指纹的影像实体状态。

        Args:
            asset: 影像资产。
            path: 已校验实体路径。
            checksum_sha256: 下游实体校验值；空值时使用资产校验值。
            evidence_type: 当前物理来源类别。

        Returns:
            dict[str, object]: 资产校验值、大小和文件修改时间。
        """
        stat = path.stat()
        return {
            "asset_code": asset.asset_code,
            "checksum_sha256": checksum_sha256 or asset.checksum_sha256,
            "file_size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "evidence_type": evidence_type,
        }

    def _fingerprint(
        self,
        run: ChangeDetectionRun,
        baseline_state: dict[str, object],
        target_state: dict[str, object],
    ) -> str:
        """计算渲染器、源实体和任务证据共同缓存指纹。

        Args:
            run: 变化检测任务。
            baseline_state: 前时相实体状态。
            target_state: 后时相实体状态。

        Returns:
            str: 小写十六进制 SHA-256 指纹。
        """
        payload = {
            "renderer_version": self.renderer.renderer_version,
            "max_dimension": settings.change_preview_max_dimension,
            "run_code": run.run_code,
            "rule_config_version": run.rule_config_version,
            "alignment_offset_pixels": float(run.alignment_offset_pixels),
            "baseline": baseline_state,
            "target": target_state,
        }
        return sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        """先写临时文件再原子替换预览或清单。

        Args:
            path: 最终文件路径。
            content: 待写入字节。

        Returns:
            None: 无返回值。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _read_manifest(manifest_path: Path) -> dict[str, object] | None:
        """安全读取缓存清单，损坏时返回空。

        Args:
            manifest_path: JSON 清单路径。

        Returns:
            dict[str, object] | None: 合法对象或空。
        """
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _cache_is_valid(
        manifest: dict[str, object] | None,
        fingerprint: str,
        baseline_path: Path,
        target_path: Path,
    ) -> bool:
        """校验缓存指纹、实体文件和预览 SHA-256。

        Args:
            manifest: 已读取清单。
            fingerprint: 当前源实体指纹。
            baseline_path: 前时相预览路径。
            target_path: 后时相预览路径。

        Returns:
            bool: 缓存完整且未失效时返回 True。
        """
        if manifest is None or manifest.get("fingerprint") != fingerprint:
            return False
        if not baseline_path.is_file() or not target_path.is_file():
            return False
        previews = manifest.get("previews")
        if not isinstance(previews, dict):
            return False
        try:
            return (
                calculate_sha256(baseline_path)
                == previews.get("baseline_sha256")
                and calculate_sha256(target_path)
                == previews.get("target_sha256")
            )
        except OSError:
            return False

    @staticmethod
    def _comparison_urls(
        run_code: str,
        project_code: str,
        task_code: str,
    ) -> tuple[str, str]:
        """生成包含项目任务作用域的双时相图片 URL。

        Args:
            run_code: 检测任务编号。
            project_code: 项目编号。
            task_code: 作业任务编号。

        Returns:
            tuple[str, str]: 前后时相图片 URL。
        """
        query = urlencode({"project_code": project_code, "task_code": task_code})
        prefix = f"/api/v1/change-detection/runs/{run_code}/comparison"
        return (
            f"{prefix}/baseline.png?{query}",
            f"{prefix}/target.png?{query}",
        )

    def _metadata_response(
        self,
        manifest: dict[str, object],
        baseline: ImageryAsset,
        target: ImageryAsset,
        run_code: str,
        project_code: str,
        task_code: str,
    ) -> ChangeComparisonMetadataResponse:
        """将已校验缓存清单转换为前端响应。

        Args:
            manifest: 缓存 JSON 清单。
            baseline: 前时相影像。
            target: 后时相影像。
            run_code: 检测任务编号。
            project_code: 项目编号。
            task_code: 作业任务编号。

        Returns:
            ChangeComparisonMetadataResponse: 可加载的双时相预览元数据。
        """
        baseline_url, target_url = self._comparison_urls(
            run_code,
            project_code,
            task_code,
        )
        sources = manifest["sources"]
        render = manifest["render"]
        previews = manifest["previews"]
        if not all(isinstance(item, dict) for item in (sources, render, previews)):
            raise ValidationException("双时相预览缓存清单结构无效")
        baseline_source = sources["baseline"]
        target_source = sources["target"]
        if not isinstance(baseline_source, dict) or not isinstance(
            target_source,
            dict,
        ):
            raise ValidationException("双时相预览来源清单无效")
        return ChangeComparisonMetadataResponse(
            run_code=run_code,
            baseline=ChangeComparisonSourceResponse(
                asset_code=baseline.asset_code,
                asset_name=baseline.asset_name,
                acquired_at=baseline.acquired_at,
                checksum_sha256=str(baseline.checksum_sha256),
                file_size_bytes=int(baseline.file_size_bytes or 0),
                band_indexes=tuple(baseline_source["band_indexes"]),
            ),
            target=ChangeComparisonSourceResponse(
                asset_code=target.asset_code,
                asset_name=target.asset_name,
                acquired_at=target.acquired_at,
                checksum_sha256=str(target_source["checksum_sha256"]),
                file_size_bytes=int(target_source["file_size_bytes"]),
                band_indexes=tuple(target_source["band_indexes"]),
            ),
            baseline_url=baseline_url,
            target_url=target_url,
            bounds_wgs84=tuple(render["bounds_wgs84"]),
            width=int(render["width"]),
            height=int(render["height"]),
            renderer_version=str(render["renderer_version"]),
            stretch_ranges=tuple(
                tuple(item) for item in render["stretch_ranges"]
            ),
            baseline_preview_sha256=str(previews["baseline_sha256"]),
            target_preview_sha256=str(previews["target_sha256"]),
            generated_at=datetime.fromisoformat(str(manifest["generated_at"])),
        )

    async def _ensure_cached(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
    ) -> CachedChangeComparison:
        """校验源文件并按需生成原子缓存及来源清单。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 检测任务编号。

        Returns:
            CachedChangeComparison: 已校验缓存。
        """
        project, _, run = await self._resolve_context(
            db,
            project_code,
            task_code,
            run_code,
        )
        baseline, target = await self._resolve_run_assets(db, project.id, run)
        if run.registration_job_id is None:
            raise ValidationException("检测任务未绑定可复核的实体配准成果")
        registration, target_source_path = (
            await self.registration_service.resolve_verified_job_by_id(
                db,
                project.id,
                run.registration_job_id,
            )
        )
        if (
            registration.task_id != run.task_id
            or registration.reference_asset_id != baseline.id
            or registration.moving_asset_id != target.id
        ):
            raise ValidationException("检测任务配准成果与两期影像或任务范围不一致")
        registration_snapshot = (run.source_snapshot or {}).get(
            "registration",
            {},
        )
        if (
            registration_snapshot.get("output_sha256")
            != registration.checksum_sha256
        ):
            raise ValidationException("检测任务配准成果快照与当前实体校验值不一致")
        baseline_source_path = self.imagery_service.resolve_verified_asset_path(
            baseline
        )
        baseline_state = self._source_state(baseline, baseline_source_path)
        target_state = self._source_state(
            target,
            target_source_path,
            registration.checksum_sha256,
            "imagery_registration",
        )
        fingerprint = self._fingerprint(run, baseline_state, target_state)
        cache_dir = self.preview_root / str(run.id) / fingerprint[:20]
        baseline_path = cache_dir / "baseline.png"
        target_path = cache_dir / "target.png"
        manifest_path = cache_dir / "manifest.json"

        async def load_valid_cache() -> CachedChangeComparison | None:
            manifest = await asyncio.to_thread(self._read_manifest, manifest_path)
            valid = await asyncio.to_thread(
                self._cache_is_valid,
                manifest,
                fingerprint,
                baseline_path,
                target_path,
            )
            if not valid or manifest is None:
                return None
            try:
                metadata = self._metadata_response(
                    manifest,
                    baseline,
                    target,
                    run_code,
                    project_code,
                    task_code,
                )
            except (KeyError, TypeError, ValueError, ValidationException):
                return None
            return CachedChangeComparison(
                metadata=metadata,
                baseline_path=baseline_path,
                target_path=target_path,
                baseline_etag=metadata.baseline_preview_sha256,
                target_etag=metadata.target_preview_sha256,
            )

        cached = await load_valid_cache()
        if cached is not None:
            return cached

        lock = self._run_locks.setdefault(run.id, asyncio.Lock())
        async with lock:
            cached = await load_valid_cache()
            if cached is not None:
                return cached
            actual_baseline_checksum, actual_target_checksum = await asyncio.gather(
                asyncio.to_thread(calculate_sha256, baseline_source_path),
                asyncio.to_thread(calculate_sha256, target_source_path),
            )
            if actual_baseline_checksum != baseline.checksum_sha256:
                raise ValidationException("前时相影像实体 SHA-256 与资产记录不一致")
            if actual_target_checksum != registration.checksum_sha256:
                raise ValidationException("后时相配准实体 SHA-256 与任务记录不一致")
            try:
                rendered = await asyncio.to_thread(
                    self.renderer.render_pair,
                    baseline_source_path,
                    target_source_path,
                    settings.change_preview_max_dimension,
                )
            except (OSError, ValueError, rasterio.errors.RasterioError) as exc:
                raise ValidationException(f"双时相栅格预览生成失败：{exc}") from exc
            baseline_preview_sha256 = sha256(rendered.baseline_png).hexdigest()
            target_preview_sha256 = sha256(rendered.target_png).hexdigest()
            generated_at = datetime.now(UTC)
            manifest: dict[str, object] = {
                "fingerprint": fingerprint,
                "generated_at": generated_at.isoformat(),
                "sources": {
                    "baseline": {
                        **baseline_state,
                        "band_indexes": list(rendered.baseline_band_indexes),
                    },
                    "target": {
                        **target_state,
                        "band_indexes": list(rendered.target_band_indexes),
                    },
                },
                "render": {
                    "renderer_version": self.renderer.renderer_version,
                    "bounds_wgs84": list(rendered.bounds_wgs84),
                    "width": rendered.width,
                    "height": rendered.height,
                    "stretch_ranges": [
                        list(item) for item in rendered.stretch_ranges
                    ],
                },
                "previews": {
                    "baseline_sha256": baseline_preview_sha256,
                    "target_sha256": target_preview_sha256,
                },
            }
            await asyncio.to_thread(
                self._write_atomic,
                baseline_path,
                rendered.baseline_png,
            )
            await asyncio.to_thread(
                self._write_atomic,
                target_path,
                rendered.target_png,
            )
            await asyncio.to_thread(
                self._write_atomic,
                manifest_path,
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
            metadata = self._metadata_response(
                manifest,
                baseline,
                target,
                run_code,
                project_code,
                task_code,
            )
            return CachedChangeComparison(
                metadata=metadata,
                baseline_path=baseline_path,
                target_path=target_path,
                baseline_etag=baseline_preview_sha256,
                target_etag=target_preview_sha256,
            )

    async def get_metadata(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
    ) -> ChangeComparisonMetadataResponse:
        """生成或复用双时相预览并返回清单。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 检测任务编号。

        Returns:
            ChangeComparisonMetadataResponse: 预览地址与来源证据。
        """
        return (
            await self._ensure_cached(db, project_code, task_code, run_code)
        ).metadata

    async def get_image(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
        side: str,
    ) -> tuple[bytes, str]:
        """读取已校验前或后时相 PNG 和 ETag。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 检测任务编号。
            side: `baseline` 或 `target`。

        Returns:
            tuple[bytes, str]: PNG 字节和 SHA-256 ETag。
        """
        cached = await self._ensure_cached(db, project_code, task_code, run_code)
        if side == "baseline":
            return await asyncio.to_thread(cached.baseline_path.read_bytes), (
                cached.baseline_etag
            )
        if side == "target":
            return await asyncio.to_thread(cached.target_path.read_bytes), (
                cached.target_etag
            )
        raise ValidationException("双时相预览类型不合法")
