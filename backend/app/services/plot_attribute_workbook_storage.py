"""地块属性 Excel 原始导入文件受控存储。"""

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from app.core.exceptions import ValidationException
from app.models.plot_attribute_workbook import PlotAttributeImportBatch
from app.services.plot_attribute_workbook_parser import (
    MAX_XLSX_BYTES,
    PlotAttributeWorkbookParser,
)


@dataclass(frozen=True)
class StoredPlotAttributeWorkbook:
    """已原子发布的地块属性导入工作簿证据。"""

    path: Path
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    created_new: bool


@dataclass(frozen=True)
class VerifiedPlotAttributeImportWorkbook:
    """通过路径、大小、SHA256 和工作簿结构复核的导入源文件。"""

    path: Path
    batch_code: str
    original_filename: str
    file_uri: str
    file_size_bytes: int
    checksum_sha256: str
    row_count: int
    changed_count: int
    unchanged_count: int
    imported_by: str
    imported_by_code: str
    imported_by_role: str
    import_comment: str
    imported_at: datetime


class PlotAttributeWorkbookStorage:
    """保存并复核地块属性导入源工作簿。"""

    def __init__(self, storage_root: Path | None = None) -> None:
        """初始化受控存储目录。

        Args:
            storage_root: 测试或部署注入的存储根目录。

        Returns:
            None: 无返回值。
        """
        self.storage_root = storage_root or (
            Path(__file__).resolve().parents[2]
            / "storage"
            / "plot-attribute-imports"
        )

    def store(self, filename: str, content: bytes) -> StoredPlotAttributeWorkbook:
        """按服务端 SHA256 原子保存原始 XLSX。

        Args:
            filename: 原始文件名，仅用于扩展名校验。
            content: 已通过解析器校验的工作簿字节。

        Returns:
            StoredPlotAttributeWorkbook: 受控路径、大小和校验值。
        """
        if not filename.strip().lower().endswith(".xlsx"):
            raise ValidationException("仅支持保存 .xlsx 地块属性工作簿")
        if not content or len(content) > MAX_XLSX_BYTES:
            raise ValidationException("地块属性工作簿大小不合法")
        checksum = hashlib.sha256(content).hexdigest()
        self.storage_root.mkdir(parents=True, exist_ok=True)
        final_path = self.storage_root / f"{checksum}.xlsx"
        if final_path.exists():
            existing = final_path.read_bytes()
            existing_checksum = hashlib.sha256(existing).hexdigest()
            if len(existing) != len(content) or existing_checksum != checksum:
                raise ValidationException("受控目录中同名工作簿证据校验失败")
            return StoredPlotAttributeWorkbook(
                path=final_path,
                file_uri=f"storage://plot-attribute-imports/{final_path.name}",
                file_size_bytes=len(existing),
                checksum_sha256=checksum,
                created_new=False,
            )

        temporary_path = self.storage_root / f".{uuid4().hex}.tmp"
        try:
            with temporary_path.open("xb") as file_handle:
                file_handle.write(content)
                file_handle.flush()
                os.fsync(file_handle.fileno())
            if temporary_path.stat().st_size != len(content):
                raise ValidationException("地块属性工作簿临时文件大小不一致")
            if hashlib.sha256(temporary_path.read_bytes()).hexdigest() != checksum:
                raise ValidationException("地块属性工作簿临时文件校验失败")
            os.replace(temporary_path, final_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return StoredPlotAttributeWorkbook(
            path=final_path,
            file_uri=f"storage://plot-attribute-imports/{final_path.name}",
            file_size_bytes=len(content),
            checksum_sha256=checksum,
            created_new=True,
        )

    def verify_import_workbook(
        self,
        batch: PlotAttributeImportBatch,
        parser: PlotAttributeWorkbookParser,
    ) -> VerifiedPlotAttributeImportWorkbook:
        """在成果归档前重新复核数据库批次对应的原始 XLSX。

        Args:
            batch: 数据库地块属性导入批次。
            parser: 工作簿安全解析器。

        Returns:
            VerifiedPlotAttributeImportWorkbook: 可写入成果包的实体证据。
        """
        prefix = "storage://plot-attribute-imports/"
        if not batch.file_uri.startswith(prefix):
            raise ValidationException("地块属性工作簿不在受控存储中")
        relative_text = batch.file_uri.removeprefix(prefix)
        relative_path = PurePosixPath(relative_text)
        if (
            relative_path.is_absolute()
            or ".." in relative_path.parts
            or len(relative_path.parts) != 1
            or not relative_text
        ):
            raise ValidationException("地块属性工作簿受控路径不合法")
        expected_name = f"{batch.checksum_sha256}.xlsx"
        if relative_path.name != expected_name:
            raise ValidationException("地块属性工作簿路径与数据库校验值不一致")
        path = self.storage_root / relative_path.name
        if not path.is_file():
            raise ValidationException("地块属性工作簿实体不存在")
        content = path.read_bytes()
        if len(content) != batch.file_size_bytes:
            raise ValidationException("地块属性工作簿文件大小校验失败")
        checksum = hashlib.sha256(content).hexdigest()
        if checksum != batch.checksum_sha256:
            raise ValidationException("地块属性工作簿 SHA256 校验失败")
        rows = parser.parse(batch.original_filename, content)
        if len(rows) != batch.row_count:
            raise ValidationException("地块属性工作簿行数与导入批次不一致")
        if batch.changed_count + batch.unchanged_count != batch.row_count:
            raise ValidationException("地块属性工作簿批次变更数量不一致")
        return VerifiedPlotAttributeImportWorkbook(
            path=path,
            batch_code=batch.batch_code,
            original_filename=batch.original_filename,
            file_uri=batch.file_uri,
            file_size_bytes=batch.file_size_bytes,
            checksum_sha256=batch.checksum_sha256,
            row_count=batch.row_count,
            changed_count=batch.changed_count,
            unchanged_count=batch.unchanged_count,
            imported_by=batch.imported_by,
            imported_by_code=batch.imported_by_code,
            imported_by_role=batch.imported_by_role,
            import_comment=batch.import_comment,
            imported_at=batch.imported_at,
        )
