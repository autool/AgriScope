"""离线介质 ZIP64 分卷规划、原子写入与实体复核。"""

import hashlib
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import ZIP_STORED, BadZipFile, ZipFile

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256


@dataclass(frozen=True)
class OfflineArchiveSourceFile:
    """已重新校验、可写入离线封存的单个实体文件。"""

    sequence: int
    source_kind: str
    source_entity_id: int | None
    source_entity_code: str
    archive_path: str
    original_filename: str
    physical_path: Path
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    media_type: str
    source_version: str | None
    security_classification: str
    source_updated_at: datetime | None

    def manifest_item(self) -> dict:
        """构造规范化来源清单项。

        Returns:
            dict: 不包含本机绝对路径的来源证据。
        """
        return {
            "sequence": self.sequence,
            "source_kind": self.source_kind,
            "source_entity_id": self.source_entity_id,
            "source_entity_code": self.source_entity_code,
            "archive_path": self.archive_path,
            "original_filename": self.original_filename,
            "file_uri": self.file_uri,
            "file_size_bytes": self.file_size_bytes,
            "checksum_sha256": self.checksum_sha256,
            "media_type": self.media_type,
            "source_version": self.source_version,
            "security_classification": self.security_classification,
            "source_updated_at": (
                self.source_updated_at.isoformat()
                if self.source_updated_at is not None
                else None
            ),
        }


@dataclass(frozen=True)
class OfflineArchiveVolumeArtifact:
    """已写入并校验的单个 ZIP64 卷。"""

    sequence: int
    filename: str
    path: Path
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    source_size_bytes: int
    volume_manifest: dict
    sources: tuple[OfflineArchiveSourceFile, ...]


@dataclass(frozen=True)
class OfflineArchiveWriteResult:
    """离线封存原子写入结果。"""

    root_path: Path
    manifest_path: Path
    manifest_uri: str
    manifest_size_bytes: int
    manifest_checksum_sha256: str
    canonical_manifest: dict
    volumes: tuple[OfflineArchiveVolumeArtifact, ...]


class OfflineArchiveWriter:
    """生成可独立解压且可逐卷复核的 ZIP64 离线封存。"""

    STORAGE_PREFIX = "storage://offline-archives/"
    VOLUME_MANIFEST_NAME = "volume_manifest.json"
    VOLUME_FIXED_RESERVE = 64 * 1024
    MEMBER_RESERVE = 2048

    def __init__(self, storage_root: Path | None = None) -> None:
        """初始化离线封存受控存储根目录。

        Args:
            storage_root: 测试或部署注入的离线封存目录。

        Returns:
            None: 无返回值。
        """
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2] / "storage" / "offline-archives"
        )

    @staticmethod
    def canonical_json(payload: dict | list) -> bytes:
        """将清单序列化为稳定 UTF-8 JSON。

        Args:
            payload: 待序列化的字典或列表。

        Returns:
            bytes: 规范化 JSON 字节。
        """
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    @classmethod
    def snapshot_sha256(
        cls,
        sources: list[OfflineArchiveSourceFile],
    ) -> str:
        """计算来源快照的规范化 SHA-256。

        Args:
            sources: 已按稳定顺序排列的来源实体。

        Returns:
            str: 来源快照 SHA-256。
        """
        payload = [source.manifest_item() for source in sources]
        return hashlib.sha256(cls.canonical_json(payload)).hexdigest()

    @classmethod
    def _estimated_source_bytes(cls, source: OfflineArchiveSourceFile) -> int:
        """保守估算一个不压缩 ZIP 成员占用空间。

        Args:
            source: 待写入来源实体。

        Returns:
            int: 含文件体和目录/清单预留的估算字节数。
        """
        return (
            source.file_size_bytes
            + cls.MEMBER_RESERVE
            + len(source.archive_path.encode("utf-8")) * 2
        )

    @classmethod
    def plan_volumes(
        cls,
        sources: list[OfflineArchiveSourceFile],
        volume_capacity_bytes: int,
    ) -> list[list[OfflineArchiveSourceFile]]:
        """按容量把每个完整实体分配到一个独立卷。

        Args:
            sources: 待封存实体列表。
            volume_capacity_bytes: 单卷最大物理字节数。

        Returns:
            list[list[OfflineArchiveSourceFile]]: 分卷后的来源实体。
        """
        if not sources:
            raise ValidationException("没有可写入离线介质的实体文件")
        if volume_capacity_bytes <= cls.VOLUME_FIXED_RESERVE:
            raise ValidationException("离线介质单卷容量过小")
        planned: list[list[OfflineArchiveSourceFile]] = []
        current: list[OfflineArchiveSourceFile] = []
        current_bytes = cls.VOLUME_FIXED_RESERVE
        for source in sources:
            estimated = cls._estimated_source_bytes(source)
            if estimated + cls.VOLUME_FIXED_RESERVE > volume_capacity_bytes:
                raise ValidationException(
                    f"实体 {source.source_entity_code} 大小为 "
                    f"{source.file_size_bytes} 字节，超过单卷容量；"
                    "平台不会截断或拆分单个源文件，请提高容量后重试"
                )
            if current and current_bytes + estimated > volume_capacity_bytes:
                planned.append(current)
                current = []
                current_bytes = cls.VOLUME_FIXED_RESERVE
            current.append(source)
            current_bytes += estimated
        if current:
            planned.append(current)
        return planned

    @staticmethod
    def _ensure_safe_archive_path(path: str) -> None:
        """拒绝绝对路径、空路径和目录穿越成员名。

        Args:
            path: ZIP 内成员路径。

        Returns:
            None: 路径安全时无返回值。
        """
        candidate = PurePosixPath(path)
        if (
            not path
            or candidate.is_absolute()
            or ".." in candidate.parts
            or candidate.name in {"", "."}
        ):
            raise ValidationException(f"离线封存成员路径不安全：{path}")

    @staticmethod
    def _source_categories(
        sources: list[OfflineArchiveSourceFile],
    ) -> dict[str, dict[str, int]]:
        """按来源类别汇总数量和字节数。

        Args:
            sources: 全部来源实体。

        Returns:
            dict[str, dict[str, int]]: 类别统计。
        """
        counts: Counter[str] = Counter()
        sizes: defaultdict[str, int] = defaultdict(int)
        for source in sources:
            counts[source.source_kind] += 1
            sizes[source.source_kind] += source.file_size_bytes
        return {
            kind: {"count": counts[kind], "file_size_bytes": sizes[kind]}
            for kind in sorted(counts)
        }

    def write_archive(
        self,
        archive_code: str,
        archive_name: str,
        generated_at: datetime,
        volume_capacity_bytes: int,
        source_snapshot_sha256: str,
        delivery_package: dict,
        sources: list[OfflineArchiveSourceFile],
    ) -> OfflineArchiveWriteResult:
        """在临时目录完成全部卷和顶层清单后原子发布。

        Args:
            archive_code: 离线封存业务编号。
            archive_name: 离线封存名称。
            generated_at: 统一生成时间。
            volume_capacity_bytes: 单卷最大物理容量。
            source_snapshot_sha256: 来源规范快照 SHA-256。
            delivery_package: 当前成果交付包快照。
            sources: 已重新校验的全部实体文件。

        Returns:
            OfflineArchiveWriteResult: 已发布分卷和规范清单证据。
        """
        if len({source.archive_path for source in sources}) != len(sources):
            raise ValidationException("离线封存成员路径存在重复")
        for source in sources:
            self._ensure_safe_archive_path(source.archive_path)
        planned = self.plan_volumes(sources, volume_capacity_bytes)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        temporary_parent = self.storage_root / ".tmp"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        temporary_root = temporary_parent / f"{archive_code}-{uuid4().hex}"
        final_root = self.storage_root / archive_code
        if final_root.exists():
            raise ValidationException(f"离线封存目录 {archive_code} 已存在")
        temporary_root.mkdir(parents=False, exist_ok=False)
        volume_artifacts: list[OfflineArchiveVolumeArtifact] = []
        try:
            volume_count = len(planned)
            for volume_sequence, volume_sources in enumerate(planned, start=1):
                filename = f"{archive_code}-VOL-{volume_sequence:03d}.zip"
                temporary_path = temporary_root / filename
                source_items = [
                    source.manifest_item() for source in volume_sources
                ]
                volume_manifest = {
                    "schema_version": "offline-raster-volume-v1",
                    "archive_code": archive_code,
                    "archive_name": archive_name,
                    "generated_at": generated_at.isoformat(),
                    "volume_sequence": volume_sequence,
                    "volume_count": volume_count,
                    "volume_capacity_bytes": volume_capacity_bytes,
                    "source_count": len(volume_sources),
                    "source_size_bytes": sum(
                        source.file_size_bytes for source in volume_sources
                    ),
                    "source_snapshot_sha256": source_snapshot_sha256,
                    "sources": source_items,
                }
                with ZipFile(
                    temporary_path,
                    mode="w",
                    compression=ZIP_STORED,
                    allowZip64=True,
                    strict_timestamps=False,
                ) as archive:
                    for source in volume_sources:
                        if not source.physical_path.is_file():
                            raise ValidationException(
                                f"离线封存来源 {source.source_entity_code} 实体不存在"
                            )
                        if (
                            source.physical_path.stat().st_size
                            != source.file_size_bytes
                        ):
                            raise ValidationException(
                                f"离线封存来源 {source.source_entity_code} "
                                "在写入前大小发生变化"
                            )
                        if (
                            calculate_sha256(source.physical_path)
                            != source.checksum_sha256
                        ):
                            raise ValidationException(
                                f"离线封存来源 {source.source_entity_code} "
                                "在写入前 SHA-256 发生变化"
                            )
                        archive.write(source.physical_path, source.archive_path)
                    archive.writestr(
                        self.VOLUME_MANIFEST_NAME,
                        self.canonical_json(volume_manifest),
                    )
                file_size_bytes = temporary_path.stat().st_size
                if file_size_bytes > volume_capacity_bytes:
                    raise ValidationException(
                        f"第 {volume_sequence} 卷实际大小超过配置容量，"
                        "请提高容量后重试"
                    )
                volume_checksum = calculate_sha256(temporary_path)
                self._verify_volume_path(
                    temporary_path,
                    file_size_bytes,
                    volume_checksum,
                    volume_manifest,
                )
                volume_artifacts.append(
                    OfflineArchiveVolumeArtifact(
                        sequence=volume_sequence,
                        filename=filename,
                        path=temporary_path,
                        file_uri=(
                            f"{self.STORAGE_PREFIX}{archive_code}/{filename}"
                        ),
                        file_size_bytes=file_size_bytes,
                        checksum_sha256=volume_checksum,
                        source_size_bytes=volume_manifest["source_size_bytes"],
                        volume_manifest=volume_manifest,
                        sources=tuple(volume_sources),
                    )
                )
            canonical_manifest = {
                "schema_version": "offline-raster-archive-v1",
                "archive_code": archive_code,
                "archive_name": archive_name,
                "generated_at": generated_at.isoformat(),
                "volume_capacity_bytes": volume_capacity_bytes,
                "volume_count": len(volume_artifacts),
                "source_count": len(sources),
                "total_source_bytes": sum(
                    source.file_size_bytes for source in sources
                ),
                "total_archive_bytes": sum(
                    volume.file_size_bytes for volume in volume_artifacts
                ),
                "source_snapshot_sha256": source_snapshot_sha256,
                "delivery_package": delivery_package,
                "source_categories": self._source_categories(sources),
                "volumes": [
                    {
                        "sequence": volume.sequence,
                        "filename": volume.filename,
                        "file_size_bytes": volume.file_size_bytes,
                        "checksum_sha256": volume.checksum_sha256,
                        "source_count": len(volume.sources),
                        "source_size_bytes": volume.source_size_bytes,
                        "sources": [
                            source.manifest_item() for source in volume.sources
                        ],
                    }
                    for volume in volume_artifacts
                ],
            }
            manifest_filename = f"{archive_code}-manifest.json"
            manifest_path = temporary_root / manifest_filename
            manifest_path.write_bytes(self.canonical_json(canonical_manifest))
            manifest_size_bytes = manifest_path.stat().st_size
            manifest_checksum_sha256 = calculate_sha256(manifest_path)
            temporary_root.replace(final_root)
        except (OSError, BadZipFile) as exc:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise ValidationException("离线介质分卷写入失败") from exc
        except ValidationException:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        final_volumes = tuple(
            OfflineArchiveVolumeArtifact(
                sequence=volume.sequence,
                filename=volume.filename,
                path=final_root / volume.filename,
                file_uri=volume.file_uri,
                file_size_bytes=volume.file_size_bytes,
                checksum_sha256=volume.checksum_sha256,
                source_size_bytes=volume.source_size_bytes,
                volume_manifest=volume.volume_manifest,
                sources=volume.sources,
            )
            for volume in volume_artifacts
        )
        final_manifest_path = final_root / manifest_filename
        return OfflineArchiveWriteResult(
            root_path=final_root,
            manifest_path=final_manifest_path,
            manifest_uri=(
                f"{self.STORAGE_PREFIX}{archive_code}/{manifest_filename}"
            ),
            manifest_size_bytes=manifest_size_bytes,
            manifest_checksum_sha256=manifest_checksum_sha256,
            canonical_manifest=canonical_manifest,
            volumes=final_volumes,
        )

    def resolve_controlled_path(self, file_uri: str) -> Path:
        """解析并限制离线封存受控 URI。

        Args:
            file_uri: `storage://offline-archives/` 受控地址。

        Returns:
            Path: 位于离线封存根目录下的实体路径。
        """
        if not file_uri.startswith(self.STORAGE_PREFIX):
            raise ValidationException("离线封存文件不在受控存储中")
        root = self.storage_root.resolve()
        path = (root / file_uri.removeprefix(self.STORAGE_PREFIX)).resolve()
        if not path.is_relative_to(root):
            raise ValidationException("离线封存文件路径越界")
        if not path.is_file():
            raise NotFoundException("离线封存实体文件不存在")
        return path

    def verify_manifest(
        self,
        file_uri: str,
        expected_size: int,
        expected_checksum: str,
        expected_payload: dict,
    ) -> Path:
        """重新校验顶层规范清单实体和数据库快照。

        Args:
            file_uri: 受控清单 URI。
            expected_size: 数据库存储的文件大小。
            expected_checksum: 数据库存储的 SHA-256。
            expected_payload: 数据库存储的规范清单 JSON。

        Returns:
            Path: 已通过全部复核的清单路径。
        """
        path = self.resolve_controlled_path(file_uri)
        if path.stat().st_size != expected_size:
            raise ValidationException("离线封存顶层清单大小校验失败")
        if calculate_sha256(path) != expected_checksum:
            raise ValidationException("离线封存顶层清单 SHA-256 校验失败")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("离线封存顶层清单结构无效") from exc
        if payload != expected_payload:
            raise ValidationException("离线封存顶层清单与数据库快照不一致")
        return path

    def verify_volume(
        self,
        file_uri: str,
        expected_size: int,
        expected_checksum: str,
        expected_manifest: dict,
    ) -> Path:
        """逐成员重新校验一个可独立提取的 ZIP64 卷。

        Args:
            file_uri: 分卷受控 URI。
            expected_size: 数据库存储的分卷大小。
            expected_checksum: 数据库存储的分卷 SHA-256。
            expected_manifest: 数据库存储的卷内清单。

        Returns:
            Path: 已通过签名、成员和校验值复核的分卷路径。
        """
        path = self.resolve_controlled_path(file_uri)
        self._verify_volume_path(
            path,
            expected_size,
            expected_checksum,
            expected_manifest,
        )
        return path

    def _verify_volume_path(
        self,
        path: Path,
        expected_size: int,
        expected_checksum: str,
        expected_manifest: dict,
    ) -> None:
        """复核指定路径的 ZIP64 分卷及全部成员。

        Args:
            path: 已限制范围或尚未发布的分卷路径。
            expected_size: 期望物理大小。
            expected_checksum: 期望分卷 SHA-256。
            expected_manifest: 期望卷内规范清单。

        Returns:
            None: 全部证据一致时无返回值。
        """
        if path.stat().st_size != expected_size:
            raise ValidationException("离线封存分卷大小校验失败")
        if calculate_sha256(path) != expected_checksum:
            raise ValidationException("离线封存分卷 SHA-256 校验失败")
        expected_sources = expected_manifest.get("sources") or []
        expected_names = {
            str(item["archive_path"]) for item in expected_sources
        } | {self.VOLUME_MANIFEST_NAME}
        try:
            with ZipFile(path) as archive:
                actual_names = set(archive.namelist())
                if actual_names != expected_names:
                    raise ValidationException("离线封存分卷成员集合不一致")
                for name in actual_names:
                    self._ensure_safe_archive_path(name)
                volume_manifest = json.loads(
                    archive.read(self.VOLUME_MANIFEST_NAME).decode("utf-8")
                )
                if volume_manifest != expected_manifest:
                    raise ValidationException("卷内清单与数据库快照不一致")
                for item in expected_sources:
                    member_name = str(item["archive_path"])
                    digest = hashlib.sha256()
                    member_size = 0
                    with archive.open(member_name) as member:
                        while chunk := member.read(1024 * 1024):
                            digest.update(chunk)
                            member_size += len(chunk)
                    if member_size != int(item["file_size_bytes"]):
                        raise ValidationException(
                            f"离线封存成员 {member_name} 大小校验失败"
                        )
                    if digest.hexdigest() != item["checksum_sha256"]:
                        raise ValidationException(
                            f"离线封存成员 {member_name} SHA-256 校验失败"
                        )
        except (BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("离线封存分卷结构无效") from exc

    def remove_archive(self, archive_code: str) -> None:
        """清理数据库事务失败后已发布的整个封存目录。

        Args:
            archive_code: 待清理离线封存编号。

        Returns:
            None: 清理结束后无返回值。
        """
        path = (self.storage_root / archive_code).resolve()
        root = self.storage_root.resolve()
        if path.is_relative_to(root):
            shutil.rmtree(path, ignore_errors=True)
