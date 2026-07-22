"""影像文件受控路径、格式签名和校验和工具。"""

import hashlib
from pathlib import Path

SUPPORTED_RASTER_SUFFIXES = {".tif", ".tiff", ".img", ".hdf"}


def resolve_imagery_path(storage_dir: Path, relative_path: str) -> Path:
    """将相对路径安全解析到指定影像存储根目录。

    Args:
        storage_dir: 受控影像存储根目录。
        relative_path: 用户或数据库提供的相对路径。

    Returns:
        Path: 未越出存储根目录的绝对路径。
    """
    requested = Path(relative_path)
    if requested.is_absolute():
        raise ValueError("影像文件必须使用存储目录内的相对路径")
    storage_root = storage_dir.resolve()
    target_path = (storage_root / requested).resolve()
    if not target_path.is_relative_to(storage_root):
        raise ValueError("影像文件路径不得越出存储目录")
    if target_path.suffix.lower() not in SUPPORTED_RASTER_SUFFIXES:
        raise ValueError("影像文件仅支持 GeoTIFF、IMG 或 HDF 格式")
    return target_path


def calculate_sha256(path: Path) -> str:
    """流式计算文件 SHA256。

    Args:
        path: 待校验文件。

    Returns:
        str: 小写十六进制 SHA256。
    """
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_supported_raster_signature(path: Path) -> bool:
    """校验 GeoTIFF、IMG 或 HDF 文件头签名。

    Args:
        path: 待校验影像文件。

    Returns:
        bool: 扩展名与已知格式签名匹配时返回 True。
    """
    with path.open("rb") as file_handle:
        header = file_handle.read(16)
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        return header.startswith((b"II*\x00", b"MM\x00*"))
    if suffix == ".img":
        return header.startswith(b"EHFA_HEADER_TAG")
    if suffix == ".hdf":
        return header.startswith((b"\x89HDF\r\n\x1a\n", b"\x0e\x03\x13\x01"))
    return False
