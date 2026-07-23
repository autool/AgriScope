"""多源数据资产实体扩展名、签名和安全归档检查。"""

import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile

import rasterio
from rasterio.errors import RasterioIOError

from app.core.exceptions import ValidationException

DATASET_SUFFIXES: dict[str, set[str]] = {
    "imagery": {".tif", ".tiff", ".img", ".hdf", ".zip"},
    "vector": {".geojson", ".json", ".gpkg", ".kml", ".zip"},
    "table": {".csv", ".xlsx", ".zip"},
    "dem": {".tif", ".tiff", ".img", ".hdf", ".zip"},
    "control": {".csv", ".xlsx", ".geojson", ".json", ".pdf", ".zip"},
    "weather": {".csv", ".json", ".xlsx", ".nc", ".grb", ".grib", ".zip"},
    "management": {".csv", ".json", ".xlsx", ".docx", ".pdf", ".zip"},
    "uav": {
        ".tif",
        ".tiff",
        ".img",
        ".jpg",
        ".jpeg",
        ".png",
        ".mp4",
        ".csv",
        ".json",
        ".zip",
    },
    "iot": {".csv", ".json", ".xlsx", ".zip"},
}

MEDIA_TYPES: dict[str, str] = {
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".img": "application/x-erdas-img",
    ".hdf": "application/x-hdf",
    ".geojson": "application/geo+json",
    ".json": "application/json",
    ".gpkg": "application/geopackage+sqlite3",
    ".kml": "application/vnd.google-earth.kml+xml",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".nc": "application/x-netcdf",
    ".grb": "application/x-grib",
    ".grib": "application/x-grib",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".mp4": "video/mp4",
    ".zip": "application/zip",
}

MAX_DIRECT_JSON_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000


@dataclass(frozen=True)
class DatasetFileInspection:
    """服务端确认的多源实体格式和结构摘要。"""

    media_type: str
    suffix: str
    metadata: dict[str, object]


def allowed_dataset_suffixes(asset_type: str) -> set[str]:
    """返回指定数据资产类型允许的实体扩展名。

    Args:
        asset_type: imagery、vector、table 等数据资产类型。

    Returns:
        set[str]: 小写扩展名集合。
    """
    return DATASET_SUFFIXES.get(asset_type, set())


def _inspect_archive(path: Path, suffix: str, max_expanded_bytes: int) -> dict:
    """检查 ZIP/Office 归档路径、加密、成员数和解压体积。

    Args:
        path: 待检查归档文件。
        suffix: `.zip`、`.xlsx` 或 `.docx`。
        max_expanded_bytes: 允许的成员总解压体积。

    Returns:
        dict: 归档成员数量和总解压体积。
    """
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            if not members or len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValidationException("数据资产归档成员数量无效或超过上限")
            expanded_size = 0
            names: set[str] = set()
            for item in members:
                normalized = item.filename.replace("\\", "/")
                member_path = PurePosixPath(normalized)
                if (
                    not normalized
                    or normalized.startswith("/")
                    or ".." in member_path.parts
                ):
                    raise ValidationException("数据资产归档包含不安全内部路径")
                if item.flag_bits & 0x1:
                    raise ValidationException("数据资产归档不得加密")
                expanded_size += item.file_size
                if expanded_size > max_expanded_bytes:
                    raise ValidationException("数据资产归档解压后体积超过平台上限")
                names.add(normalized)
            if suffix == ".xlsx" and not {
                "[Content_Types].xml",
                "xl/workbook.xml",
            }.issubset(names):
                raise ValidationException("上传文件不是有效的 XLSX 工作簿")
            if suffix == ".docx" and not {
                "[Content_Types].xml",
                "word/document.xml",
            }.issubset(names):
                raise ValidationException("上传文件不是有效的 DOCX 文档")
            corrupt_member = archive.testzip()
            if corrupt_member is not None:
                raise ValidationException(
                    f"数据资产归档成员 {corrupt_member} 已损坏"
                )
            return {
                "archive_member_count": len(members),
                "archive_expanded_size_bytes": expanded_size,
            }
    except BadZipFile as exc:
        raise ValidationException("上传文件不是有效的 ZIP/Office 归档") from exc


def _has_raster_signature(path: Path, suffix: str) -> bool:
    """按原始扩展名校验临时栅格文件签名。

    Args:
        path: 可能以 `.part` 结尾的临时实体路径。
        suffix: 从原始文件名解析出的栅格扩展名。

    Returns:
        bool: 文件头与原始扩展名匹配时返回 True。
    """
    with path.open("rb") as file_handle:
        header = file_handle.read(16)
    if suffix in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if suffix == ".img":
        return header.startswith(b"EHFA_HEADER_TAG")
    if suffix == ".hdf":
        return header.startswith((b"\x89HDF\r\n\x1a\n", b"\x0e\x03\x13\x01"))
    return False


def _inspect_raster(path: Path, suffix: str) -> dict[str, object]:
    """检查影像或 DEM 栅格签名和基础结构。

    Args:
        path: 待检查栅格临时文件。
        suffix: 原始文件名扩展名。

    Returns:
        dict: 驱动、尺寸、波段和坐标系摘要。
    """
    if not _has_raster_signature(path, suffix):
        raise ValidationException("栅格扩展名与实体签名不一致")
    try:
        with rasterio.open(path) as root_dataset:
            dataset = root_dataset
            nested = None
            if root_dataset.count <= 0 and root_dataset.subdatasets:
                nested = rasterio.open(root_dataset.subdatasets[0])
                dataset = nested
            try:
                if dataset.width <= 0 or dataset.height <= 0 or dataset.count <= 0:
                    raise ValidationException("栅格尺寸或波段数量无效")
                return {
                    "driver": dataset.driver,
                    "width": dataset.width,
                    "height": dataset.height,
                    "band_count": dataset.count,
                    "crs": dataset.crs.to_string() if dataset.crs else None,
                    "has_rpc": dataset.rpcs is not None,
                }
            finally:
                if nested is not None:
                    nested.close()
    except RasterioIOError as exc:
        raise ValidationException("栅格实体无法读取或文件已损坏") from exc


def inspect_dataset_file(
    path: Path,
    asset_type: str,
    original_filename: str,
    reported_media_type: str | None,
    max_archive_expanded_bytes: int,
) -> DatasetFileInspection:
    """按资产类型检查扩展名、文件签名和安全结构。

    Args:
        path: 已完整写入的临时文件。
        asset_type: 多源数据资产类型。
        original_filename: 原始文件名。
        reported_media_type: 浏览器报告 MIME。
        max_archive_expanded_bytes: ZIP/Office 成员解压体积上限。

    Returns:
        DatasetFileInspection: 服务端确认的媒体类型和结构摘要。
    """
    suffix = Path(original_filename).suffix.lower()
    allowed = allowed_dataset_suffixes(asset_type)
    if suffix not in allowed:
        raise ValidationException(
            f"{asset_type} 数据资产仅允许：{'、'.join(sorted(allowed))}"
        )
    with path.open("rb") as file_handle:
        prefix = file_handle.read(64)
    metadata: dict[str, object] = {}
    if suffix in {".tif", ".tiff", ".img", ".hdf"}:
        metadata.update(_inspect_raster(path, suffix))
    elif suffix in {".zip", ".xlsx", ".docx"}:
        if not prefix.startswith(b"PK"):
            raise ValidationException("归档扩展名与实体签名不一致")
        metadata.update(
            _inspect_archive(path, suffix, max_archive_expanded_bytes)
        )
    elif suffix in {".geojson", ".json"}:
        if path.stat().st_size > MAX_DIRECT_JSON_BYTES:
            raise ValidationException("直接 JSON 超过 100MB，请使用安全 ZIP 包")
        try:
            with path.open("r", encoding="utf-8-sig") as file_handle:
                payload = json.load(file_handle)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("JSON/GeoJSON 实体格式无效") from exc
        metadata["json_top_level_type"] = type(payload).__name__
        if suffix == ".geojson" and not (
            isinstance(payload, dict)
            and payload.get("type") in {"Feature", "FeatureCollection"}
        ):
            raise ValidationException("GeoJSON 顶层必须是 Feature 或 FeatureCollection")
    elif suffix == ".gpkg":
        if not prefix.startswith(b"SQLite format 3\x00"):
            raise ValidationException("GeoPackage 扩展名与 SQLite 实体签名不一致")
    elif suffix == ".kml":
        normalized = prefix.lstrip().lower()
        if not (normalized.startswith(b"<?xml") or b"<kml" in normalized):
            raise ValidationException("KML 扩展名与 XML 实体签名不一致")
    elif suffix == ".csv":
        try:
            prefix.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationException("CSV 必须使用 UTF-8 编码") from exc
    elif suffix == ".pdf":
        if not prefix.startswith(b"%PDF-"):
            raise ValidationException("PDF 扩展名与实体签名不一致")
    elif suffix == ".nc":
        if not prefix.startswith((b"CDF", b"\x89HDF\r\n\x1a\n")):
            raise ValidationException("NetCDF 扩展名与实体签名不一致")
    elif suffix in {".grb", ".grib"}:
        if not prefix.startswith(b"GRIB"):
            raise ValidationException("GRIB 扩展名与实体签名不一致")
    elif suffix in {".jpg", ".jpeg"}:
        if not prefix.startswith(b"\xff\xd8\xff"):
            raise ValidationException("JPEG 扩展名与实体签名不一致")
    elif suffix == ".png":
        if not prefix.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValidationException("PNG 扩展名与实体签名不一致")
    elif suffix == ".mp4":
        if len(prefix) < 12 or prefix[4:8] != b"ftyp":
            raise ValidationException("MP4 扩展名与实体签名不一致")
    media_type = MEDIA_TYPES[suffix]
    reported = (reported_media_type or "").split(";", 1)[0].strip().lower()
    if reported and reported not in {
        "application/octet-stream",
        "binary/octet-stream",
        media_type.lower(),
    }:
        raise ValidationException("浏览器报告 MIME 与实体格式不一致")
    return DatasetFileInspection(
        media_type=media_type,
        suffix=suffix,
        metadata=metadata,
    )
