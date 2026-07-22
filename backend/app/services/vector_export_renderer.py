"""GeoJSON、Shapefile、KML 和 OpenFileGDB 实体生成器。"""

import json
import tempfile
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, ZipFile

import fiona

from app.core.exceptions import ValidationException

KML_NAMESPACE = "http://www.opengis.net/kml/2.2"
ElementTree.register_namespace("", KML_NAMESPACE)


class VectorExportRenderer:
    """把任务图斑真实写入四种标准矢量格式。"""

    @staticmethod
    def _serialize_value(value: object) -> object:
        """把数据库值转换为 JSON/Fiona 可写类型。

        Args:
            value: 数据库字段值。

        Returns:
            object: 可序列化标量或空值。
        """
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    @classmethod
    def _properties(cls, row: object) -> dict[str, object]:
        """构建完整业务属性和来源血缘。

        Args:
            row: DAO 导出行。

        Returns:
            dict[str, object]: 标准字段属性。
        """
        field_names = (
            "plot_code",
            "owner_village",
            "area_ha",
            "land_class",
            "crop_type",
            "planting_mode",
            "irrigation_condition",
            "interpretation_status",
            "version",
            "province_name",
            "city_name",
            "district_name",
            "district_code",
            "source_name",
            "source_feature_id",
            "source_uri",
            "source_version",
            "source_updated_at",
        )
        return {
            name: cls._serialize_value(getattr(row, name, None))
            for name in field_names
        }

    @classmethod
    def _features(cls, rows: list[object]) -> list[dict[str, object]]:
        """构建标准 GeoJSON Feature 列表。

        Args:
            rows: 任务作用域导出行。

        Returns:
            list[dict[str, object]]: 完整属性与 Polygon 几何。
        """
        features: list[dict[str, object]] = []
        for row in rows:
            geometry = json.loads(row.geometry)
            if geometry.get("type") != "Polygon":
                raise ValidationException("矢量导出只接受任务内 Polygon 图斑")
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": cls._properties(row),
                }
            )
        return features

    @staticmethod
    def _fiona_schema(*, shapefile: bool) -> dict[str, object]:
        """返回 Shapefile 短字段或 FileGDB 完整字段模式。

        Args:
            shapefile: 是否受十字符字段名限制。

        Returns:
            dict[str, object]: Fiona schema。
        """
        if shapefile:
            properties = {
                "PLOT_CODE": "str:50",
                "VILLAGE": "str:100",
                "AREA_HA": "float:14.4",
                "LAND_CLS": "str:50",
                "CROP_TYPE": "str:50",
                "PLANT_MD": "str:50",
                "IRRIGATE": "str:20",
                "STATUS": "str:30",
                "VERSION": "int",
                "PROVINCE": "str:100",
                "CITY": "str:100",
                "DISTRICT": "str:100",
                "DIST_CODE": "str:50",
                "SRC_NAME": "str:120",
                "SRC_ID": "str:80",
                "SRC_URI": "str:254",
                "SRC_VER": "str:80",
                "SRC_TIME": "str:40",
            }
        else:
            properties = {
                "plot_code": "str:50",
                "owner_village": "str:100",
                "area_ha": "float",
                "land_class": "str:50",
                "crop_type": "str:50",
                "planting_mode": "str:50",
                "irrigation_condition": "str:20",
                "interpretation_status": "str:30",
                "version": "int",
                "province_name": "str:100",
                "city_name": "str:100",
                "district_name": "str:100",
                "district_code": "str:50",
                "source_name": "str:120",
                "source_feature_id": "str:80",
                "source_uri": "str:500",
                "source_version": "str:80",
                "source_updated_at": "str:40",
            }
        return {"geometry": "Polygon", "properties": properties}

    @staticmethod
    def _shapefile_properties(properties: dict[str, object]) -> dict[str, object]:
        """映射为 Shapefile 十字符字段名。

        Args:
            properties: 完整业务属性。

        Returns:
            dict[str, object]: DBF 可写短字段属性。
        """
        mapping = {
            "PLOT_CODE": "plot_code",
            "VILLAGE": "owner_village",
            "AREA_HA": "area_ha",
            "LAND_CLS": "land_class",
            "CROP_TYPE": "crop_type",
            "PLANT_MD": "planting_mode",
            "IRRIGATE": "irrigation_condition",
            "STATUS": "interpretation_status",
            "VERSION": "version",
            "PROVINCE": "province_name",
            "CITY": "city_name",
            "DISTRICT": "district_name",
            "DIST_CODE": "district_code",
            "SRC_NAME": "source_name",
            "SRC_ID": "source_feature_id",
            "SRC_URI": "source_uri",
            "SRC_VER": "source_version",
            "SRC_TIME": "source_updated_at",
        }
        return {
            target: properties.get(source)
            for target, source in mapping.items()
        }

    @classmethod
    def _write_geojson(
        cls,
        path: Path,
        features: list[dict[str, object]],
    ) -> None:
        """写入 UTF-8 GeoJSON FeatureCollection。

        Args:
            path: 输出文件路径。
            features: 标准要素列表。

        Returns:
            None: 文件写入完成。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {"type": "FeatureCollection", "features": features},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    @classmethod
    def _write_shapefile(
        cls,
        path: Path,
        features: list[dict[str, object]],
    ) -> None:
        """使用 Fiona/GDAL 写入真实 ESRI Shapefile 文件组。

        Args:
            path: `.shp` 主文件路径。
            features: 标准要素列表。

        Returns:
            None: 文件组写入完成。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with fiona.open(
            path,
            "w",
            driver="ESRI Shapefile",
            crs="EPSG:4326",
            schema=cls._fiona_schema(shapefile=True),
            encoding="UTF-8",
        ) as collection:
            collection.writerecords(
                {
                    "geometry": feature["geometry"],
                    "properties": cls._shapefile_properties(
                        feature["properties"]  # type: ignore[arg-type]
                    ),
                }
                for feature in features
            )

    @classmethod
    def _write_filegdb(
        cls,
        path: Path,
        features: list[dict[str, object]],
    ) -> None:
        """使用开源 OpenFileGDB 驱动创建真实 FileGDB 目录。

        Args:
            path: `.gdb` 目录路径。
            features: 标准要素列表。

        Returns:
            None: FileGDB 图层写入完成。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with fiona.open(
            path,
            "w",
            driver="OpenFileGDB",
            layer="farmland_plots",
            crs="EPSG:4326",
            schema=cls._fiona_schema(shapefile=False),
            encoding="UTF-8",
        ) as collection:
            collection.writerecords(
                {
                    "geometry": feature["geometry"],
                    "properties": feature["properties"],
                }
                for feature in features
            )

    @staticmethod
    def _append_kml_polygon(parent: Any, geometry: dict[str, object]) -> None:
        """把 WGS84 Polygon 外环和内环写入 KML。

        Args:
            parent: Placemark XML 节点。
            geometry: GeoJSON Polygon。

        Returns:
            None: XML 原位增加 Polygon。
        """
        polygon = ElementTree.SubElement(parent, f"{{{KML_NAMESPACE}}}Polygon")
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            raise ValidationException("KML 导出遇到空 Polygon 坐标")
        for index, ring in enumerate(coordinates):
            boundary_name = "outerBoundaryIs" if index == 0 else "innerBoundaryIs"
            boundary = ElementTree.SubElement(
                polygon,
                f"{{{KML_NAMESPACE}}}{boundary_name}",
            )
            linear_ring = ElementTree.SubElement(
                boundary,
                f"{{{KML_NAMESPACE}}}LinearRing",
            )
            coordinate_node = ElementTree.SubElement(
                linear_ring,
                f"{{{KML_NAMESPACE}}}coordinates",
            )
            coordinate_node.text = " ".join(
                f"{float(point[0]):.10f},{float(point[1]):.10f},0"
                for point in ring
            )

    @classmethod
    def _write_kml(
        cls,
        path: Path,
        export_title: str,
        features: list[dict[str, object]],
    ) -> None:
        """写入带完整 ExtendedData 的 OGC KML 2.2。

        Args:
            path: KML 输出路径。
            export_title: 文档标题。
            features: 标准要素列表。

        Returns:
            None: KML 文件写入完成。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        root = ElementTree.Element(f"{{{KML_NAMESPACE}}}kml")
        document = ElementTree.SubElement(root, f"{{{KML_NAMESPACE}}}Document")
        ElementTree.SubElement(
            document,
            f"{{{KML_NAMESPACE}}}name",
        ).text = export_title
        for feature in features:
            properties = feature["properties"]
            if not isinstance(properties, dict):
                raise ValidationException("KML 导出属性结构不合法")
            placemark = ElementTree.SubElement(
                document,
                f"{{{KML_NAMESPACE}}}Placemark",
            )
            ElementTree.SubElement(
                placemark,
                f"{{{KML_NAMESPACE}}}name",
            ).text = str(properties.get("plot_code") or "未编号图斑")
            extended = ElementTree.SubElement(
                placemark,
                f"{{{KML_NAMESPACE}}}ExtendedData",
            )
            for key, value in properties.items():
                data = ElementTree.SubElement(
                    extended,
                    f"{{{KML_NAMESPACE}}}Data",
                    {"name": key},
                )
                ElementTree.SubElement(
                    data,
                    f"{{{KML_NAMESPACE}}}value",
                ).text = "" if value is None else str(value)
            geometry = feature["geometry"]
            if not isinstance(geometry, dict):
                raise ValidationException("KML 导出几何结构不合法")
            cls._append_kml_polygon(placemark, geometry)
        ElementTree.ElementTree(root).write(
            path,
            encoding="utf-8",
            xml_declaration=True,
        )

    @staticmethod
    def _validate_fiona_dataset(
        path: Path,
        expected_count: int,
        *,
        layer: str | None = None,
    ) -> None:
        """重新打开 GDAL 数据集并核对图层、数量、几何和 CRS。

        Args:
            path: Shapefile 或 FileGDB 路径。
            expected_count: 预期要素数量。
            layer: FileGDB 图层名。

        Returns:
            None: 数据集符合门禁时无返回值。
        """
        layers = fiona.listlayers(path)
        if not layers or (layer is not None and layer not in layers):
            raise ValidationException("矢量导出数据集缺少目标图层")
        selected_layer = layer or layers[0]
        with fiona.open(path, layer=selected_layer) as source:
            if len(source) != expected_count:
                raise ValidationException("矢量导出数据集要素数量不一致")
            if source.crs.to_epsg() != 4326:
                raise ValidationException("矢量导出数据集不是 EPSG:4326")
            geometry_type = str(source.schema.get("geometry") or "")
            if geometry_type not in {"Polygon", "MultiPolygon"}:
                raise ValidationException("矢量导出数据集几何类型不合法")

    @classmethod
    def validate_directory(
        cls,
        root: Path,
        formats: list[str],
        expected_count: int,
    ) -> None:
        """复核解压目录内每种声明格式的真实可读性。

        Args:
            root: 导出成员根目录。
            formats: 声明格式列表。
            expected_count: 预期要素数量。

        Returns:
            None: 全部格式可读且数量一致时无返回值。
        """
        if "geojson" in formats:
            geojson_path = root / "geojson" / "farmland_plots.geojson"
            try:
                payload = json.loads(geojson_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValidationException("GeoJSON 实体不可读取") from exc
            features = payload.get("features") if isinstance(payload, dict) else None
            if (
                payload.get("type") != "FeatureCollection"
                or not isinstance(features, list)
                or len(features) != expected_count
                or any(
                    not isinstance(item, dict)
                    or not isinstance(item.get("geometry"), dict)
                    or item["geometry"].get("type") != "Polygon"
                    for item in features
                )
            ):
                raise ValidationException("GeoJSON 实体结构或数量不一致")
        if "shapefile" in formats:
            cls._validate_fiona_dataset(
                root / "shapefile" / "farmland_plots.shp",
                expected_count,
            )
        if "kml" in formats:
            try:
                kml_root = ElementTree.parse(
                    root / "kml" / "farmland_plots.kml"
                ).getroot()
            except (OSError, ElementTree.ParseError) as exc:
                raise ValidationException("KML 实体不可读取") from exc
            placemarks = kml_root.findall(
                f".//{{{KML_NAMESPACE}}}Placemark"
            )
            if len(placemarks) != expected_count:
                raise ValidationException("KML 实体要素数量不一致")
        if "filegdb" in formats:
            cls._validate_fiona_dataset(
                root / "filegdb" / "farmland_plots.gdb",
                expected_count,
                layer="farmland_plots",
            )

    @staticmethod
    def _member_format(relative_path: str) -> str:
        """按归档目录确定清单格式名称。

        Args:
            relative_path: ZIP 内相对路径。

        Returns:
            str: 用户可识别格式名称。
        """
        if relative_path.startswith("geojson/"):
            return "GeoJSON"
        if relative_path.startswith("shapefile/"):
            return "Shapefile"
        if relative_path.startswith("kml/"):
            return "KML"
        return "FileGDB"

    @classmethod
    def build_archive(
        cls,
        rows: list[object],
        formats: list[str],
        district_codes: list[str],
        land_classes: list[str],
        task: object,
        task_plot_count: int,
        export_code: str,
        export_title: str,
        version: int,
        generated_at: datetime,
        operator: object,
        comment: str,
    ) -> tuple[bytes, dict]:
        """生成并验证多格式矢量成果 ZIP。

        Args:
            rows: 任务作用域导出行。
            formats: 选择的真实格式。
            district_codes: 县区筛选快照。
            land_classes: 地类筛选快照。
            task: 当前作业任务。
            task_plot_count: 当前任务精确有效图斑数。
            export_code: 导出业务编号。
            export_title: 导出标题。
            version: 导出版本。
            generated_at: 生成时间。
            operator: 持久化项目用户。
            comment: 生成依据。

        Returns:
            tuple[bytes, dict]: ZIP 字节和逐文件 manifest。
        """
        features = cls._features(rows)
        with tempfile.TemporaryDirectory(prefix="agriscope-vector-") as directory:
            root = Path(directory)
            if "geojson" in formats:
                cls._write_geojson(
                    root / "geojson" / "farmland_plots.geojson",
                    features,
                )
            if "shapefile" in formats:
                cls._write_shapefile(
                    root / "shapefile" / "farmland_plots.shp",
                    features,
                )
            if "kml" in formats:
                cls._write_kml(
                    root / "kml" / "farmland_plots.kml",
                    export_title,
                    features,
                )
            if "filegdb" in formats:
                cls._write_filegdb(
                    root / "filegdb" / "farmland_plots.gdb",
                    features,
                )
            cls.validate_directory(root, formats, len(features))
            files = []
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                relative_path = path.relative_to(root).as_posix()
                content = path.read_bytes()
                files.append(
                    {
                        "path": relative_path,
                        "format": cls._member_format(relative_path),
                        "file_size_bytes": len(content),
                        "checksum_sha256": sha256(content).hexdigest(),
                    }
                )
            manifest = {
                "schema_version": "vector-export-v1",
                "export_code": export_code,
                "export_title": export_title,
                "version": version,
                "task": {
                    "task_code": task.task_code,
                    "task_name": task.task_name,
                    "task_plot_count": task_plot_count,
                    "task_updated_at_snapshot": task.updated_at.isoformat(),
                },
                "filters": {
                    "district_codes": district_codes,
                    "land_classes": land_classes,
                },
                "formats": formats,
                "feature_count": len(features),
                "generator": {
                    "display_name": operator.display_name,
                    "user_code": operator.user_code,
                    "role_code": operator.role_code,
                    "generated_at": generated_at.isoformat(),
                    "comment": comment,
                },
                "files": files,
            }
            output = BytesIO()
            with ZipFile(output, "w", ZIP_DEFLATED) as archive:
                for item in files:
                    archive.write(root / item["path"], item["path"])
                archive.writestr(
                    "manifest.json",
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        indent=2,
                    ).encode("utf-8"),
                )
            return output.getvalue(), manifest
