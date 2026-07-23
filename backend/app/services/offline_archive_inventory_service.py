"""离线介质封存受控来源盘点与容量摘要服务。"""

import asyncio
import re
from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationException
from app.dao.offline_archive_dao import OfflineArchiveDAO
from app.schemas.offline_archive import OfflineArchiveSourceSummary
from app.services.dataset_asset_service import DatasetAssetService
from app.services.delivery_service import DeliveryService
from app.services.imagery_service import ImageryService
from app.services.offline_archive_writer import OfflineArchiveSourceFile


class OfflineArchiveInventoryService:
    """重新校验并汇总离线封存所需的全部物理实体。"""

    def __init__(
        self,
        dao: OfflineArchiveDAO,
        delivery_service: DeliveryService,
        imagery_service: ImageryService,
        dataset_asset_service: DatasetAssetService,
    ) -> None:
        """初始化来源盘点依赖。

        Args:
            dao: 离线封存来源查询 DAO。
            delivery_service: 当前成果包实体复核服务。
            imagery_service: 源影像和处理产物实体复核服务。
            dataset_asset_service: 多源数据实体复核服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao
        self.delivery_service = delivery_service
        self.imagery_service = imagery_service
        self.dataset_asset_service = dataset_asset_service

    @staticmethod
    def _safe_segment(value: str) -> str:
        """把业务编码规范化为不含路径分隔符的成员目录名。

        Args:
            value: 来源业务编码。

        Returns:
            str: 仅含字母、数字、点、下划线和连字符的片段。
        """
        normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
        return normalized.strip("._") or "unnamed"

    @staticmethod
    def _raster_media_type(path: Path) -> str:
        """根据受控栅格扩展名返回明确媒体类型。

        Args:
            path: 栅格实体路径。

        Returns:
            str: 标准或保守媒体类型。
        """
        return {
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".img": "application/octet-stream",
            ".hdf": "application/x-hdf",
            ".h5": "application/x-hdf5",
        }.get(path.suffix.lower(), "application/octet-stream")

    @staticmethod
    def _imagery_classification(asset: object) -> str:
        """从影像实体标签读取密级，缺失时保守按内部资料处理。

        Args:
            asset: 遥感影像资产模型。

        Returns:
            str: 规范化密级编码。
        """
        metadata = getattr(asset, "raster_metadata", None) or {}
        tags = metadata.get("tags") or {}
        value = str(tags.get("SECURITY_CLASSIFICATION") or "internal")
        return value.strip().lower() or "internal"

    @staticmethod
    def _with_sequence(
        source: OfflineArchiveSourceFile,
        sequence: int,
    ) -> OfflineArchiveSourceFile:
        """为已校验来源分配稳定全局序号。

        Args:
            source: 尚未使用最终序号的来源实体。
            sequence: 从 1 开始的全局序号。

        Returns:
            OfflineArchiveSourceFile: 带最终序号的不可变副本。
        """
        return OfflineArchiveSourceFile(
            sequence=sequence,
            source_kind=source.source_kind,
            source_entity_id=source.source_entity_id,
            source_entity_code=source.source_entity_code,
            archive_path=source.archive_path,
            original_filename=source.original_filename,
            physical_path=source.physical_path,
            file_uri=source.file_uri,
            file_size_bytes=source.file_size_bytes,
            checksum_sha256=source.checksum_sha256,
            media_type=source.media_type,
            source_version=source.source_version,
            security_classification=source.security_classification,
            source_updated_at=source.source_updated_at,
        )

    @classmethod
    def assign_sequences(
        cls,
        sources: list[OfflineArchiveSourceFile],
    ) -> list[OfflineArchiveSourceFile]:
        """按当前稳定顺序为来源分配从 1 开始的全局序号。

        Args:
            sources: 已按业务规则排序的来源实体。

        Returns:
            list[OfflineArchiveSourceFile]: 带最终序号的来源列表。
        """
        return [
            cls._with_sequence(source, index)
            for index, source in enumerate(sources, start=1)
        ]

    async def load_non_delivery_sources(
        self,
        db: AsyncSession,
        task: object,
    ) -> list[OfflineArchiveSourceFile]:
        """重新校验业务源影像、完成产物和已验证多源数据实体。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            list[OfflineArchiveSourceFile]: 不含成果交付包的受控实体。
        """
        imagery_assets = await self.dao.list_operational_imagery_assets(
            db,
            task.project_id,
        )
        if not imagery_assets:
            raise ValidationException("项目没有可封存的业务影像源实体")
        imagery_by_id = {asset.id: asset for asset in imagery_assets}
        steps = await self.dao.list_completed_imagery_steps(
            db,
            list(imagery_by_id),
        )
        dataset_assets = await self.dao.list_verified_dataset_assets(
            db,
            task.project_id,
            task.id,
        )
        sources: list[OfflineArchiveSourceFile] = []
        for asset in imagery_assets:
            path = await asyncio.to_thread(
                self.imagery_service.resolve_verified_asset_source_path,
                asset,
            )
            if not asset.checksum_sha256:
                raise ValidationException(
                    f"业务影像 {asset.asset_code} 缺少服务端 SHA-256 证据"
                )
            sources.append(
                OfflineArchiveSourceFile(
                    sequence=0,
                    source_kind="imagery_source",
                    source_entity_id=asset.id,
                    source_entity_code=asset.asset_code,
                    archive_path=(
                        "imagery/source/"
                        f"{self._safe_segment(asset.asset_code)}/{path.name}"
                    ),
                    original_filename=asset.original_filename or path.name,
                    physical_path=path,
                    file_uri=str(asset.file_uri),
                    file_size_bytes=path.stat().st_size,
                    checksum_sha256=str(asset.checksum_sha256),
                    media_type=self._raster_media_type(path),
                    source_version=(
                        str(asset.processing_level)
                        if asset.processing_level is not None
                        else None
                    ),
                    security_classification=self._imagery_classification(asset),
                    source_updated_at=asset.created_at,
                )
            )
        for step in steps:
            asset = imagery_by_id.get(step.asset_id)
            if asset is None:
                raise ValidationException("影像处理产物缺少业务源资产")
            registered_evidence = (step.parameters or {}).get(
                "artifact_evidence"
            ) or {}
            if registered_evidence.get("execution_mode") == "source_level_acceptance":
                # L2A 源级承认复用源栅格作为处理证据，不是新的物理产物。
                continue
            path, evidence = await asyncio.to_thread(
                self.imagery_service.resolve_verified_step_artifact_path,
                step,
            )
            step_entity_code = f"{asset.asset_code}:{step.step_code}"
            sources.append(
                OfflineArchiveSourceFile(
                    sequence=0,
                    source_kind="imagery_product",
                    source_entity_id=step.id,
                    source_entity_code=step_entity_code,
                    archive_path=(
                        "imagery/processed/"
                        f"{self._safe_segment(asset.asset_code)}/"
                        f"{step.sequence:02d}_{self._safe_segment(step.step_code)}"
                        f"{path.suffix.lower()}"
                    ),
                    original_filename=path.name,
                    physical_path=path,
                    file_uri=str(step.output_uri),
                    file_size_bytes=path.stat().st_size,
                    checksum_sha256=str(evidence["checksum_sha256"]),
                    media_type=self._raster_media_type(path),
                    source_version=str(
                        evidence.get("processor_version") or "unversioned"
                    ),
                    security_classification=self._imagery_classification(asset),
                    source_updated_at=step.updated_at,
                )
            )
        verified_files = await self.dataset_asset_service.load_verified_files(
            dataset_assets
        )
        dataset_by_code = {asset.asset_code: asset for asset in dataset_assets}
        for verified in verified_files:
            asset = dataset_by_code[verified.asset_code]
            sources.append(
                OfflineArchiveSourceFile(
                    sequence=0,
                    source_kind="dataset_asset",
                    source_entity_id=asset.id,
                    source_entity_code=asset.asset_code,
                    archive_path=(
                        "datasets/"
                        f"{self._safe_segment(asset.asset_type)}/"
                        f"{self._safe_segment(asset.asset_code)}/"
                        f"{self._safe_segment(verified.original_filename)}"
                    ),
                    original_filename=verified.original_filename,
                    physical_path=verified.path,
                    file_uri=verified.file_uri,
                    file_size_bytes=verified.file_size_bytes,
                    checksum_sha256=verified.checksum_sha256,
                    media_type=verified.media_type,
                    source_version=asset.source_version,
                    security_classification=asset.security_classification,
                    source_updated_at=asset.updated_at,
                )
            )
        return sources

    async def load_current_delivery_source(
        self,
        db: AsyncSession,
        task: object,
    ) -> tuple[object, OfflineArchiveSourceFile]:
        """解析任务当前成果包并构造离线封存来源。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            tuple[object, OfflineArchiveSourceFile]: 成果包模型和实体来源。
        """
        package = await self.delivery_service.get_current_package(db, task)
        if package is None:
            raise ValidationException(
                "任务尚无当前有效成果包，请完成三级审核并生成成果包后再封存"
            )
        path = await asyncio.to_thread(
            self.delivery_service.resolve_verified_package_path,
            package,
        )
        if (
            package.completed_at is None
            or package.file_size_bytes is None
            or not package.checksum_sha256
        ):
            raise ValidationException("当前成果包缺少完整实体证据")
        source = OfflineArchiveSourceFile(
            sequence=0,
            source_kind="delivery_package",
            source_entity_id=package.id,
            source_entity_code=package.package_code,
            archive_path=(
                "delivery/final/"
                f"{self._safe_segment(package.package_code)}.zip"
            ),
            original_filename=path.name,
            physical_path=path,
            file_uri=f"storage://deliveries/{path.name}",
            file_size_bytes=package.file_size_bytes,
            checksum_sha256=package.checksum_sha256,
            media_type="application/zip",
            source_version=f"v{package.version}",
            security_classification="internal",
            source_updated_at=package.completed_at,
        )
        return package, source

    async def load_current_sources(
        self,
        db: AsyncSession,
        task: object,
    ) -> tuple[object, list[OfflineArchiveSourceFile]]:
        """加载含当前成果包在内的完整离线封存来源集合。

        Args:
            db: 异步数据库会话。
            task: 当前作业任务。

        Returns:
            tuple[object, list[OfflineArchiveSourceFile]]: 成果包和稳定排序来源。
        """
        non_delivery_sources = await self.load_non_delivery_sources(db, task)
        package, delivery_source = await self.load_current_delivery_source(db, task)
        ordered = [delivery_source, *non_delivery_sources]
        return package, self.assign_sequences(ordered)

    @staticmethod
    def source_summaries(
        sources: list[OfflineArchiveSourceFile],
    ) -> list[OfflineArchiveSourceSummary]:
        """汇总前端容量预估使用的来源类别。

        Args:
            sources: 已校验来源实体。

        Returns:
            list[OfflineArchiveSourceSummary]: 稳定排序的类别摘要。
        """
        counts: Counter[str] = Counter()
        sizes: defaultdict[str, int] = defaultdict(int)
        for source in sources:
            counts[source.source_kind] += 1
            sizes[source.source_kind] += source.file_size_bytes
        return [
            OfflineArchiveSourceSummary(
                source_kind=kind,
                source_count=counts[kind],
                file_size_bytes=sizes[kind],
            )
            for kind in sorted(counts)
        ]

    @staticmethod
    def delivery_snapshot(package: object) -> dict:
        """构造顶层规范清单的当前成果包快照。

        Args:
            package: 当前有效成果交付包。

        Returns:
            dict: 不包含本机绝对路径的交付证据。
        """
        return {
            "delivery_package_id": package.id,
            "package_code": package.package_code,
            "version": package.version,
            "completed_at": package.completed_at.isoformat(),
            "file_size_bytes": package.file_size_bytes,
            "checksum_sha256": package.checksum_sha256,
        }
