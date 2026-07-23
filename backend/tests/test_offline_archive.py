"""源栅格离线介质 ZIP64 分卷、清单和失效门禁测试。"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.offline_archive import OfflineArchiveGenerateRequest
from app.services.offline_archive_response_builder import (
    OfflineArchiveResponseBuilder,
)
from app.services.offline_archive_service import OfflineArchiveService
from app.services.offline_archive_writer import (
    OfflineArchiveSourceFile,
    OfflineArchiveWriter,
)


def build_source(
    root: Path,
    sequence: int,
    size: int,
    source_kind: str = "imagery_source",
) -> OfflineArchiveSourceFile:
    """构造具有真实文件大小和 SHA-256 的受控来源。

    Args:
        root: 测试文件根目录。
        sequence: 来源序号。
        size: 文件字节数。
        source_kind: 来源类别。

    Returns:
        OfflineArchiveSourceFile: 可供分卷写入的来源实体。
    """
    path = root / f"source-{sequence}.tif"
    content = bytes([sequence % 251 + 1]) * size
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    return OfflineArchiveSourceFile(
        sequence=sequence,
        source_kind=source_kind,
        source_entity_id=sequence,
        source_entity_code=f"SOURCE-{sequence:03d}",
        archive_path=f"imagery/source/SOURCE-{sequence:03d}/{path.name}",
        original_filename=path.name,
        physical_path=path,
        file_uri=f"storage://imagery/assets/SOURCE-{sequence:03d}/{path.name}",
        file_size_bytes=size,
        checksum_sha256=checksum,
        media_type="image/tiff",
        source_version="L2A",
        security_classification="public",
        source_updated_at=datetime(2026, 7, 23, sequence, tzinfo=UTC),
    )


def test_writer_creates_independent_checked_volumes(tmp_path: Path) -> None:
    """验证每个完整源文件只进入一个可独立提取且可复核的分卷。"""
    source_root = tmp_path / "sources"
    source_root.mkdir()
    sources = [
        build_source(source_root, 1, 20_000),
        build_source(source_root, 2, 20_000, "imagery_product"),
    ]
    writer = OfflineArchiveWriter(tmp_path / "archives")
    snapshot = writer.snapshot_sha256(sources)
    result = writer.write_archive(
        "RS-TEST-OFFLINE-v1",
        "测试源栅格离线封存",
        datetime(2026, 7, 23, 12, tzinfo=UTC),
        96 * 1024,
        snapshot,
        {
            "delivery_package_id": 7,
            "package_code": "DELIVERY-v1",
            "version": 1,
            "completed_at": "2026-07-23T11:00:00+00:00",
            "file_size_bytes": 1024,
            "checksum_sha256": "d" * 64,
        },
        sources,
    )

    assert len(result.volumes) == 2
    assert result.canonical_manifest["source_count"] == 2
    assert result.canonical_manifest["volume_count"] == 2
    assert result.canonical_manifest["source_snapshot_sha256"] == snapshot
    assert json.loads(result.manifest_path.read_text(encoding="utf-8")) == (
        result.canonical_manifest
    )
    for volume, source in zip(result.volumes, sources, strict=True):
        assert volume.file_size_bytes <= 96 * 1024
        assert writer.verify_volume(
            volume.file_uri,
            volume.file_size_bytes,
            volume.checksum_sha256,
            volume.volume_manifest,
        ) == volume.path
        with ZipFile(volume.path) as archive:
            assert set(archive.namelist()) == {
                source.archive_path,
                "volume_manifest.json",
            }
            assert archive.read(source.archive_path) == (
                source.physical_path.read_bytes()
            )
    assert writer.verify_manifest(
        result.manifest_uri,
        result.manifest_size_bytes,
        result.manifest_checksum_sha256,
        result.canonical_manifest,
    ) == result.manifest_path


def test_writer_rejects_single_source_larger_than_volume(tmp_path: Path) -> None:
    """验证单文件超过卷容量时明确拒绝，不进行静默截断。"""
    source = build_source(tmp_path, 1, 40_000)
    with pytest.raises(ValidationException, match="不会截断或拆分单个源文件"):
        OfflineArchiveWriter.plan_volumes([source], 90 * 1024)


def test_volume_tampering_is_rejected(tmp_path: Path) -> None:
    """验证分卷物理字节变化会在下载复核前被拒绝。"""
    source = build_source(tmp_path, 1, 4096)
    writer = OfflineArchiveWriter(tmp_path / "archives")
    result = writer.write_archive(
        "RS-TEST-OFFLINE-v2",
        "分卷篡改测试",
        datetime(2026, 7, 23, 12, tzinfo=UTC),
        96 * 1024,
        writer.snapshot_sha256([source]),
        {"package_code": "DELIVERY-v2"},
        [source],
    )
    volume = result.volumes[0]
    with volume.path.open("ab") as file:
        file.write(b"tampered")

    with pytest.raises(ValidationException, match="分卷大小校验失败"):
        writer.verify_volume(
            volume.file_uri,
            volume.file_size_bytes,
            volume.checksum_sha256,
            volume.volume_manifest,
        )


def test_archive_staleness_tracks_delivery_and_source_snapshot() -> None:
    """验证成果包或任一受控来源变化都会使旧离线封存失效。"""
    completed_at = datetime(2026, 7, 23, 10, tzinfo=UTC)
    package = SimpleNamespace(
        id=9,
        package_code="DELIVERY-v3",
        file_size_bytes=4096,
        checksum_sha256="a" * 64,
        completed_at=completed_at,
    )
    archive = SimpleNamespace(
        status="completed",
        delivery_package_id=9,
        delivery_package_code="DELIVERY-v3",
        delivery_package_size_bytes=4096,
        delivery_package_checksum_sha256="a" * 64,
        delivery_package_completed_at_snapshot=completed_at,
        source_snapshot_sha256="b" * 64,
        volume_count=2,
    )
    volumes = [SimpleNamespace(), SimpleNamespace()]

    assert OfflineArchiveResponseBuilder.stale_reason(
        archive,
        package,
        "b" * 64,
        volumes,
    ) is None
    assert OfflineArchiveResponseBuilder.stale_reason(
        archive,
        package,
        "c" * 64,
        volumes,
    ) == "源栅格、处理产物或多源数据实体快照已变化"
    package.checksum_sha256 = "d" * 64
    assert OfflineArchiveResponseBuilder.stale_reason(
        archive,
        package,
        "b" * 64,
        volumes,
    ) == "当前成果包版本或实体证据已变化"


def test_generate_request_enforces_media_capacity_and_audit_comment() -> None:
    """验证单卷容量和生成依据必须满足后端门禁。"""
    request = OfflineArchiveGenerateRequest(
        operator_code="manager-001",
        volume_capacity_bytes=64 * 1024 * 1024,
        comment="按项目交付要求生成源栅格离线介质封存",
    )
    assert request.volume_capacity_bytes == 64 * 1024 * 1024
    with pytest.raises(ValidationError, match="不得低于 64 MiB"):
        OfflineArchiveGenerateRequest(
            operator_code="manager-001",
            volume_capacity_bytes=63 * 1024 * 1024,
            comment="按项目交付要求生成源栅格离线介质封存",
        )
    with pytest.raises(ValidationError, match="至少填写 10 个字符"):
        OfflineArchiveGenerateRequest(
            operator_code="manager-001",
            comment="依据不足",
        )


@pytest.mark.asyncio
async def test_service_generates_persisted_volume_and_audit(tmp_path: Path) -> None:
    """验证服务把实体分卷、来源快照、版本替代和审计放入同一事务。"""
    source_root = tmp_path / "sources"
    source_root.mkdir()
    sources = [
        build_source(source_root, 1, 4096, "delivery_package"),
        build_source(source_root, 2, 8192, "imagery_source"),
    ]
    package = SimpleNamespace(
        id=31,
        package_code="DELIVERY-CURRENT",
        version=3,
        completed_at=datetime(2026, 7, 23, 10, tzinfo=UTC),
        file_size_bytes=sources[0].file_size_bytes,
        checksum_sha256=sources[0].checksum_sha256,
    )
    task = SimpleNamespace(id=11, project_id=22, task_name="测试任务")
    operator = SimpleNamespace(
        display_name="项目负责人",
        user_code="manager-001",
        role_code="project_manager",
    )
    stored_volumes: list[object] = []

    dao = MagicMock()
    dao.get_next_version = AsyncMock(return_value=1)
    dao.list_current_archives_for_update = AsyncMock(return_value=[])

    async def add_archive(_: object, archive: object) -> object:
        archive.id = 101
        return archive

    async def add_volumes(_: object, volumes: list[object]) -> None:
        stored_volumes.extend(volumes)

    dao.add_archive = AsyncMock(side_effect=add_archive)
    dao.add_volumes = AsyncMock(side_effect=add_volumes)
    dao.add_sources = AsyncMock(return_value=None)
    dao.add_event = AsyncMock(return_value=None)
    dao.list_volumes = AsyncMock(side_effect=lambda *_: stored_volumes)
    workbench_dao = MagicMock()
    workbench_dao.get_task_by_code_for_update = AsyncMock(return_value=task)
    workbench_dao.add_review_record = AsyncMock(return_value=None)
    user_service = MagicMock()
    user_service.require_capability = AsyncMock(return_value=operator)
    writer = OfflineArchiveWriter(tmp_path / "archives")
    service = OfflineArchiveService(
        dao=dao,
        workbench_dao=workbench_dao,
        delivery_service=MagicMock(),
        imagery_service=MagicMock(),
        dataset_asset_service=MagicMock(),
        user_service=user_service,
        writer=writer,
    )
    service.inventory_service.load_current_sources = AsyncMock(
        return_value=(package, sources)
    )
    db = AsyncMock()

    response = await service.generate_archive(
        db,
        "RS-TEST-001",
        OfflineArchiveGenerateRequest(
            operator_code="manager-001",
            archive_name="测试离线封存",
            volume_capacity_bytes=64 * 1024 * 1024,
            comment="按当前成果包生成全部源栅格离线封存",
        ),
    )

    assert response.version == 1
    assert response.is_current is True
    assert response.volume_count == 1
    assert response.source_count == 2
    assert len(stored_volumes) == 1
    assert (tmp_path / "archives" / response.archive_code).is_dir()
    dao.add_sources.assert_awaited_once()
    dao.add_event.assert_awaited_once()
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()
