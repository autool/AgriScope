"""任务地块属性 Excel 安全解析与导出生成。"""

from collections.abc import Sequence
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.models.plot import FarmlandPlot
from app.schemas.plot_attribute_workbook import PlotAttributeWorkbookRow

XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
WORKSHEET_NAME = "地块属性"
MAX_XLSX_BYTES = 10 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_XLSX_ARCHIVE_ENTRIES = 2000
MAX_WORKBOOK_ROWS = 500
WORKBOOK_HEADERS = (
    "plot_code",
    "expected_version",
    "owner_village",
    "land_class",
    "crop_type",
    "planting_mode",
    "irrigation_condition",
)


class PlotAttributeWorkbookParser:
    """解析任务地块属性 XLSX，并生成可回写的标准工作簿。"""

    @staticmethod
    def _validate_archive(content: bytes) -> None:
        """校验 XLSX ZIP 路径、加密标记和解压规模。

        Args:
            content: 原始 XLSX 字节。

        Returns:
            None: 结构安全时无返回值。
        """
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_XLSX_ARCHIVE_ENTRIES:
                    raise ValidationException("Excel 文件内部条目数量异常")
                required = {"[Content_Types].xml", "xl/workbook.xml"}
                if not required.issubset(archive.namelist()):
                    raise ValidationException("Excel 文件缺少标准 XLSX 结构")
                expanded_size = 0
                for entry in entries:
                    path = PurePosixPath(entry.filename)
                    if (
                        path.is_absolute()
                        or ".." in path.parts
                        or "\\" in entry.filename
                        or not entry.filename
                    ):
                        raise ValidationException("Excel 文件包含不安全的内部路径")
                    if entry.flag_bits & 0x1:
                        raise ValidationException("不支持加密的 Excel 文件")
                    expanded_size += entry.file_size
                    if expanded_size > MAX_XLSX_UNCOMPRESSED_BYTES:
                        raise ValidationException("Excel 文件解压后不得超过 50MB")
                if archive.testzip() is not None:
                    raise ValidationException("Excel 压缩内容已损坏")
        except BadZipFile as exc:
            raise ValidationException("Excel 文件不是有效的 XLSX 压缩包") from exc

    @staticmethod
    def _cell_text(value: object) -> str:
        """将单元格值转换为稳定文本。

        Args:
            value: openpyxl 单元格值。

        Returns:
            str: 去除首尾空白的文本。
        """
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    @staticmethod
    def _validation_message(error: ValidationError) -> str:
        """提取首条可安全展示的 Pydantic 错误。

        Args:
            error: 单行属性校验异常。

        Returns:
            str: 字段定位和中文错误信息。
        """
        first_error = error.errors(include_url=False)[0]
        location = ".".join(str(item) for item in first_error.get("loc", ()))
        message = str(first_error.get("msg") or "记录格式不合法")
        message = message.removeprefix("Value error, ")
        return f"{location}: {message}" if location else message

    def parse(self, filename: str, content: bytes) -> list[PlotAttributeWorkbookRow]:
        """解析严格表头的地块属性工作簿。

        Args:
            filename: 原始上传文件名。
            content: 原始 XLSX 字节。

        Returns:
            list[PlotAttributeWorkbookRow]: 完成格式与业务校验的逐行属性。
        """
        normalized_filename = filename.strip()
        if not normalized_filename.lower().endswith(".xlsx"):
            raise ValidationException("仅支持 .xlsx 地块属性工作簿")
        if not content:
            raise ValidationException("Excel 文件内容为空")
        if len(content) > MAX_XLSX_BYTES:
            raise ValidationException("Excel 文件不得超过 10MB")
        self._validate_archive(content)
        try:
            workbook = load_workbook(
                BytesIO(content),
                read_only=True,
                data_only=False,
                keep_links=False,
            )
        except (InvalidFileException, OSError, ValueError) as exc:
            raise ValidationException("无法读取 Excel 工作簿") from exc
        try:
            if WORKSHEET_NAME not in workbook.sheetnames:
                raise ValidationException(f"Excel 必须包含“{WORKSHEET_NAME}”工作表")
            for sheet in workbook.worksheets:
                for sheet_row in sheet.iter_rows():
                    if any(cell.data_type == "f" for cell in sheet_row):
                        raise ValidationException(
                            f"Excel 工作表“{sheet.title}”包含公式，"
                            "必须粘贴为值后再导入"
                        )
            worksheet = workbook[WORKSHEET_NAME]
            rows = worksheet.iter_rows()
            header_cells = next(rows, None)
            if header_cells is None:
                raise ValidationException("Excel 必须包含标准表头和至少一条记录")
            headers = tuple(self._cell_text(cell.value) for cell in header_cells)
            if headers != WORKBOOK_HEADERS:
                raise ValidationException(
                    "Excel 表头必须严格为：" + "、".join(WORKBOOK_HEADERS)
                )

            records: list[PlotAttributeWorkbookRow] = []
            seen_codes: set[str] = set()
            for row_number, row in enumerate(rows, start=2):
                values = [self._cell_text(cell.value) for cell in row]
                if not any(values):
                    continue
                if len(records) >= MAX_WORKBOOK_ROWS:
                    raise ValidationException("单次最多导入 500 条地块属性")
                values.extend([""] * (len(WORKBOOK_HEADERS) - len(values)))
                row_values = dict(zip(WORKBOOK_HEADERS, values, strict=False))
                try:
                    record = PlotAttributeWorkbookRow.model_validate(
                        {
                            "plot_code": row_values["plot_code"],
                            "expected_version": row_values["expected_version"],
                            "owner_village": row_values["owner_village"],
                            "land_class": row_values["land_class"],
                            "crop_type": row_values["crop_type"] or None,
                            "planting_mode": row_values["planting_mode"] or None,
                            "irrigation_condition": (
                                row_values["irrigation_condition"] or None
                            ),
                        }
                    )
                except ValidationError as exc:
                    raise ValidationException(
                        f"Excel 第 {row_number} 行 {self._validation_message(exc)}"
                    ) from exc
                if record.plot_code in seen_codes:
                    raise ValidationException(
                        f"Excel 第 {row_number} 行图斑编号 {record.plot_code} 重复"
                    )
                seen_codes.add(record.plot_code)
                records.append(record)
            if not records:
                raise ValidationException("Excel 必须包含至少一条地块属性记录")
            return records
        finally:
            workbook.close()

    @staticmethod
    def build_export(plots: Sequence[FarmlandPlot]) -> bytes:
        """从数据库当前值生成可编辑并可原子回写的 XLSX。

        Args:
            plots: 已按任务范围校验的有效图斑。

        Returns:
            bytes: 标准地块属性 Excel 实体。
        """
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = WORKSHEET_NAME
        worksheet.append(list(WORKBOOK_HEADERS))
        for plot in plots:
            worksheet.append(
                [
                    plot.plot_code,
                    plot.version,
                    plot.owner_village or "",
                    plot.land_class or "",
                    plot.crop_type or "",
                    plot.planting_mode or "",
                    plot.irrigation_condition or "",
                ]
            )

        header_fill = PatternFill("solid", fgColor="245A3F")
        for cell in worksheet[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)
            cell.alignment = Alignment(horizontal="center")
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = f"A1:G{len(plots) + 1}"
        widths = [24, 18, 24, 18, 18, 20, 20]
        for column, width in zip("ABCDEFG", widths, strict=True):
            worksheet.column_dimensions[column].width = width
        for row in worksheet.iter_rows(min_row=2, max_col=7):
            for cell in row:
                cell.number_format = "@"

        land_class_validation = DataValidation(
            type="list",
            formula1='"耕地,园地,林地,草地,水域,建设用地"',
            allow_blank=False,
        )
        worksheet.add_data_validation(land_class_validation)
        land_class_validation.add(f"D2:D{MAX_WORKBOOK_ROWS + 1}")

        instructions = workbook.create_sheet("填写说明")
        instructions.append(["字段", "填写要求"])
        instructions.append(["plot_code", "只读业务主键，不得修改或重复"])
        instructions.append(
            ["expected_version", "只读并发版本；导入时必须与数据库当前版本一致"]
        )
        instructions.append(["owner_village", "必填，最长 100 个字符"])
        instructions.append(
            ["land_class", "耕地、园地、林地、草地、水域或建设用地"]
        )
        instructions.append(["crop_type", "耕地必填，非耕地必须为空"])
        instructions.append(["planting_mode", "可选，最长 50 个字符"])
        instructions.append(["irrigation_condition", "可选，最长 20 个字符"])
        instructions.append(
            [
                "原子导入",
                "任一图斑越权、重复、版本过期或属性不合法时整批不写入",
            ]
        )
        instructions.column_dimensions["A"].width = 24
        instructions.column_dimensions["B"].width = 76
        for cell in instructions[1]:
            cell.fill = header_fill
            cell.font = Font(color="FFFFFF", bold=True)

        output = BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()
