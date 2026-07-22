"""历史年度面积统计 CSV 解析与模板生成。"""

import csv
from io import StringIO

from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.statistics import AreaStatisticsSnapshotImportItem

MAX_HISTORY_CSV_BYTES = 1024 * 1024
MAX_HISTORY_ROWS = 30
REQUIRED_HEADERS = (
    "monitor_year",
    "total_area_ha",
    "farmland_area_ha",
    "crop_area_ha",
)


class StatisticsSnapshotCsvParser:
    """解析真实历史年度面积统计 CSV。"""

    @staticmethod
    def _validation_message(error: ValidationError) -> str:
        """提取 Pydantic 首条安全校验信息。

        Args:
            error: 单条历史快照校验异常。

        Returns:
            str: 可展示的错误信息。
        """
        first_error = error.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        message = str(first_error.get("msg") or "历史快照格式不合法")
        message = message.removeprefix("Value error, ")
        return f"{location}: {message}" if location else message

    def parse(
        self,
        filename: str,
        content: bytes,
    ) -> list[AreaStatisticsSnapshotImportItem]:
        """解析历史年度统计 CSV 实体文件。

        Args:
            filename: 原始文件名。
            content: 原始 CSV 字节。

        Returns:
            list[AreaStatisticsSnapshotImportItem]: 已校验年度快照。
        """
        if not filename.strip().lower().endswith(".csv"):
            raise ValidationException("历史年度统计仅支持 .csv 文件")
        if not content:
            raise ValidationException("历史年度统计 CSV 内容为空")
        if len(content) > MAX_HISTORY_CSV_BYTES:
            raise ValidationException("历史年度统计 CSV 不得超过 1MB")
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationException("历史年度统计 CSV 必须使用 UTF-8 编码") from exc
        if "\x00" in text:
            raise ValidationException("历史年度统计 CSV 包含非法空字符")
        try:
            reader = csv.DictReader(StringIO(text, newline=""))
            headers = [str(header or "").strip() for header in reader.fieldnames or []]
            if len(headers) != len(set(headers)):
                raise ValidationException("历史年度统计 CSV 表头不得重复")
            missing_header = next(
                (header for header in REQUIRED_HEADERS if header not in headers),
                None,
            )
            if missing_header:
                raise ValidationException(
                    f"历史年度统计 CSV 缺少必填列 {missing_header}"
                )
            records: list[AreaStatisticsSnapshotImportItem] = []
            for row_number, row in enumerate(reader, start=2):
                normalized = {
                    str(key or "").strip(): str(value or "").strip()
                    for key, value in row.items()
                }
                if not any(normalized.values()):
                    continue
                if len(records) >= MAX_HISTORY_ROWS:
                    raise ValidationException("单次最多导入 30 个历史年度")
                try:
                    records.append(
                        AreaStatisticsSnapshotImportItem.model_validate(
                            {
                                header: normalized.get(header, "")
                                for header in REQUIRED_HEADERS
                            }
                        )
                    )
                except ValidationError as exc:
                    raise ValidationException(
                        f"历史统计 CSV 第 {row_number} 行 "
                        f"{self._validation_message(exc)}"
                    ) from exc
        except csv.Error as exc:
            raise ValidationException("历史年度统计 CSV 结构不合法") from exc
        if not records:
            raise ValidationException("历史年度统计 CSV 至少需要一条记录")
        years = [record.monitor_year for record in records]
        if len(years) != len(set(years)):
            raise ValidationException("同一导入批次监测年度不得重复")
        return records

    @staticmethod
    def build_template() -> bytes:
        """生成历史年度统计 CSV 标准模板。

        Returns:
            bytes: UTF-8 BOM CSV 模板。
        """
        output = StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(REQUIRED_HEADERS)
        writer.writerow([2025, "125000.0000", "98000.0000", "76000.0000"])
        return output.getvalue().encode("utf-8-sig")
