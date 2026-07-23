"""任务作用域多格式矢量成果导出测试。"""

import asyncio
import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zipfile import ZipFile

import fiona
import pytest

from app.core.exceptions import PermissionDeniedException, ValidationException
from app.dao.vector_export_dao import VectorExportDAO
from app.models.vector_export import VectorExportPackage
from app.schemas.vector_export import VectorExportGenerateRequest
from app.services.vector_export_renderer import VectorExportRenderer
from app.services.vector_export_service import VectorExportService


def build_rows() -> list[SimpleNamespace]:
    """构造两个带完整来源属性的 WGS84 Polygon。

    Returns:
        list[SimpleNamespace]: DAO 导出行。
    """
    updated_at = datetime(2026, 7, 20, tzinfo=UTC)
    common = {
        "owner_village": "幸福村 A&B",
        "area_ha": 1.25,
        "land_class": "耕地",
        "crop_type": "玉米",
        "planting_mode": "单季种植",
        "irrigation_condition": "灌溉",
        "custom_attributes": {},
        "interpretation_status": "interpreted",
        "version": 2,
        "province_name": "黑龙江省",
        "city_name": "哈尔滨市",
        "district_name": "松北区",
        "district_code": "230109",
        "source_name": "OpenStreetMap",
        "source_uri": "https://www.openstreetmap.org/way/1",
        "source_version": "3",
        "source_updated_at": updated_at,
    }
    return [
        SimpleNamespace(
            **common,
            plot_code="PLOT-001",
            source_feature_id="way/1",
            geometry=(
                '{"type":"Polygon","coordinates":'
                '[[[126.50,45.70],[126.51,45.70],[126.51,45.71],'
                '[126.50,45.70]]]}'
            ),
        ),
        SimpleNamespace(
            **common,
            plot_code="PLOT-002",
            source_feature_id="way/2",
            geometry=(
                '{"type":"Polygon","coordinates":'
                '[[[126.52,45.72],[126.53,45.72],[126.53,45.73],'
                '[126.52,45.72]]]}'
            ),
        ),
    ]


def build_task() -> SimpleNamespace:
    """构造导出关联任务。

    Returns:
        SimpleNamespace: 带稳定更新时间的任务。
    """
    return SimpleNamespace(
        id=7,
        project_id=3,
        task_code="RS-TEST",
        task_name="黑龙江省农业遥感监测测试任务",
        total_plots=2,
        updated_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
    )


def build_operator() -> SimpleNamespace:
    """构造持久化项目负责人。

    Returns:
        SimpleNamespace: 稳定用户和角色快照。
    """
    return SimpleNamespace(
        display_name="赵志远",
        user_code="manager-zhao-zhiyuan",
        role_code="project_manager",
    )


def test_vector_export_dao_uses_task_scope_and_filters() -> None:
    """验证导出数量查询连接 task_plots 并绑定县区和地类。"""
    dao = VectorExportDAO()
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(scalar_one=lambda: 2)

    result = asyncio.run(
        dao.count_features(db, 7, ["230109"], ["耕地"])
    )

    statement = db.execute.await_args.args[0]
    compiled = statement.compile()
    assert result == 2
    assert "task_plots" in str(compiled)
    assert 7 in compiled.params.values()
    assert ["230109"] in compiled.params.values()
    assert ["耕地"] in compiled.params.values()


def test_vector_export_renderer_creates_four_real_formats(tmp_path: Path) -> None:
    """验证四种格式均可重新打开且要素数量、CRS 和属性有效。"""
    renderer = VectorExportRenderer()
    task = build_task()
    export_code = "VEXP-RS-TEST-V001"
    content, manifest = renderer.build_archive(
        build_rows(),
        ["geojson", "shapefile", "kml", "filegdb"],
        ["230109"],
        ["耕地"],
        task,
        2,
        export_code,
        "松北区耕地矢量成果",
        1,
        datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
        build_operator(),
        "按松北区和耕地筛选生成四格式成果",
    )
    archive_path = tmp_path / "vector.zip"
    archive_path.write_bytes(content)
    output_root = tmp_path / "members"
    output_root.mkdir()
    with ZipFile(archive_path) as archive:
        archive.extractall(output_root)
        assert json.loads(archive.read("manifest.json")) == manifest
        names = set(archive.namelist())
    assert "geojson/farmland_plots.geojson" in names
    assert "shapefile/farmland_plots.shp" in names
    assert "kml/farmland_plots.kml" in names
    assert any(name.startswith("filegdb/farmland_plots.gdb/") for name in names)
    renderer.validate_directory(
        output_root,
        ["geojson", "shapefile", "kml", "filegdb"],
        2,
    )
    with fiona.open(output_root / "shapefile" / "farmland_plots.shp") as source:
        feature = next(iter(source))
        assert feature.properties["PLOT_CODE"] == "PLOT-001"
        assert feature.properties["LAND_CLS"] == "耕地"
    assert len(manifest["files"]) == len(names) - 1
    assert manifest["feature_count"] == 2


def test_vector_export_preserves_custom_schema_aliases_and_historical_ledger(
    tmp_path: Path,
) -> None:
    """验证四格式字段映射与完整 JSON 账本不会丢失停用历史值。"""
    row = build_rows()[0]
    row.custom_attributes = {
        "soil_type": "黑土",
        "survey_score": 98.5,
        "legacy_code": "OLD-001",
    }
    snapshot = [
        {
            "field_code": "soil_type",
            "label": "土壤类型",
            "field_type": "single_select",
            "required": True,
            "options": ["黑土", "白浆土"],
            "display_order": 10,
            "version": 1,
        },
        {
            "field_code": "survey_score",
            "label": "调查评分",
            "field_type": "number",
            "required": False,
            "options": [],
            "display_order": 20,
            "version": 2,
        },
    ]
    content, manifest = VectorExportRenderer.build_archive(
        [row],
        ["geojson", "shapefile", "kml", "filegdb"],
        [],
        [],
        build_task(),
        2,
        "VEXP-CUSTOM-001",
        "自定义属性矢量成果",
        1,
        datetime(2026, 7, 23, 9, 30, tzinfo=UTC),
        build_operator(),
        "验证活动字段别名与历史值账本",
        snapshot,
    )
    archive_path = tmp_path / "custom-vector.zip"
    archive_path.write_bytes(content)

    with ZipFile(archive_path) as archive:
        geojson = json.loads(archive.read("geojson/farmland_plots.geojson"))
        ledger = json.loads(archive.read("attributes/custom_attributes.json"))
        archive.extractall(tmp_path / "custom-vector")

    properties = geojson["features"][0]["properties"]
    assert properties["custom:soil_type"] == "黑土"
    assert properties["custom:survey_score"] == 98.5
    assert ledger["items"][0]["custom_attributes"]["legacy_code"] == "OLD-001"
    assert manifest["custom_attribute_schema"]["field_aliases"] == {
        "soil_type": {
            "shapefile": "CUST001",
            "filegdb": "custom_soil_type",
        },
        "survey_score": {
            "shapefile": "CUST002",
            "filegdb": "custom_survey_score",
        },
    }
    with fiona.open(
        tmp_path / "custom-vector" / "shapefile" / "farmland_plots.shp"
    ) as source:
        feature = next(iter(source))
        assert feature.properties["CUST001"] == "黑土"
        assert feature.properties["CUST002"] == pytest.approx(98.5)


def test_vector_export_service_generates_and_cross_validates_manifest(
    tmp_path: Path,
) -> None:
    """验证服务端原子生成、版本审计和 manifest 交叉校验。"""
    task = build_task()
    operator = build_operator()
    dao = AsyncMock()
    dao.count_features.side_effect = [2, 2]
    dao.get_export_rows.return_value = build_rows()
    dao.get_next_version.return_value = 1
    dao.supersede_completed_packages.return_value = 0

    async def add_package(_db: object, package: object) -> object:
        package.id = 11
        return package

    dao.add_package.side_effect = add_package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = task
    user_service = AsyncMock()
    user_service.require_capability.return_value = operator
    field_service = MagicMock()
    field_service.get_active_fields_by_project_id = AsyncMock(return_value=[])
    field_service.build_schema_snapshot.return_value = []
    field_service.schema_digest.return_value = (
        "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
    )
    service = VectorExportService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
        plot_attribute_field_service=field_service,
        storage_root=tmp_path,
    )
    db = AsyncMock()

    response = asyncio.run(
        service.generate_package(
            db,
            task.task_code,
            VectorExportGenerateRequest(
                operator_code=operator.user_code,
                export_title="测试任务全格式矢量成果",
                formats=["geojson", "shapefile", "kml", "filegdb"],
                district_codes=["230109"],
                land_classes=["耕地"],
                comment="验证真实四格式、筛选和完整性证据",
            ),
        )
    )

    package = dao.add_package.await_args.args[1]
    path = service.verify_package_file(package)
    assert response.version == 1
    assert response.feature_count == 2
    assert response.is_current is True
    assert path.is_file()
    user_service.require_capability.assert_awaited_once_with(
        db,
        task.project_id,
        operator.user_code,
        "generate_vector_export",
    )
    db.commit.assert_awaited_once()

    members = service.read_verified_members(package)
    tampered_manifest = deepcopy(package.export_manifest)
    tampered_manifest["files"][0]["checksum_sha256"] = "0" * 64
    with ZipFile(path, "w") as archive:
        for name, member_content in members.items():
            if name != "manifest.json":
                archive.writestr(name, member_content)
        archive.writestr(
            "manifest.json",
            json.dumps(tampered_manifest, ensure_ascii=False),
        )
    package.file_size_bytes = path.stat().st_size
    package.checksum_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    package.export_manifest = tampered_manifest
    with pytest.raises(ValidationException, match="文件证据不一致"):
        service.verify_package_file(package)


def build_package(task: SimpleNamespace) -> VectorExportPackage:
    """构造列表和权限测试使用的完整导出包模型。

    Args:
        task: 报告关联任务。

    Returns:
        VectorExportPackage: 不依赖实体文件的版本摘要。
    """
    return VectorExportPackage(
        id=11,
        task_id=task.id,
        export_code="VEXP-RS-TEST-V001",
        export_title="测试任务矢量成果",
        version=1,
        status="completed",
        formats=["geojson"],
        district_codes=[],
        land_classes=[],
        feature_count=2,
        task_plot_count=2,
        task_updated_at_snapshot=task.updated_at,
        file_uri="storage://vector-exports/RS-TEST/export.zip",
        file_size_bytes=10,
        checksum_sha256="a" * 64,
        export_manifest={"files": []},
        generation_comment="测试导出",
        generated_by="赵志远",
        generated_by_code="manager-zhao-zhiyuan",
        generated_by_role="project_manager",
        generated_at=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
    )


def test_vector_export_list_is_read_only_and_detects_task_change() -> None:
    """验证历史列表不扫描 ZIP，并动态标记任务变化后的版本。"""
    task = build_task()
    package = build_package(task)
    task.updated_at += timedelta(seconds=1)
    dao = AsyncMock()
    dao.count_features.return_value = 2
    dao.list_packages.return_value = [package]
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code.return_value = task
    service = VectorExportService(dao=dao, workbench_dao=workbench_dao)
    service.verify_package_file = MagicMock(
        side_effect=AssertionError("列表不应读取历史 ZIP")
    )
    db = AsyncMock()

    response = asyncio.run(service.list_packages(db, task.task_code))

    assert response.items[0].status == "superseded"
    assert response.items[0].is_current is False
    service.verify_package_file.assert_not_called()
    db.commit.assert_not_awaited()


def test_vector_export_download_checks_capability_before_file() -> None:
    """验证无权限用户不能触发矢量成果实体读取。"""
    task = build_task()
    package = build_package(task)
    dao = AsyncMock()
    dao.get_package_by_code.return_value = package
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_id.return_value = task
    user_service = AsyncMock()
    user_service.require_capability.side_effect = PermissionDeniedException(
        "内业解译员无权下载矢量成果"
    )
    service = VectorExportService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    service.verify_package_file = MagicMock()

    with pytest.raises(PermissionDeniedException):
        asyncio.run(
            service.authorize_download(
                AsyncMock(),
                package.export_code,
                "interp-li-jing",
            )
        )

    service.verify_package_file.assert_not_called()
