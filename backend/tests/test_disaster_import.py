"""灾害模型 GeoJSON 导入业务测试。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.core.exceptions import ValidationException
from app.schemas.disaster import DisasterGeoJsonImportRequest
from app.services.disaster_service import DisasterService


def build_import_request(
    *,
    conflict_policy: str = "reject",
) -> DisasterGeoJsonImportRequest:
    """构造单斑块标准 GeoJSON 导入请求。

    Args:
        conflict_policy: 编号冲突策略。

    Returns:
        DisasterGeoJsonImportRequest: 可供服务测试的导入请求。
    """
    return DisasterGeoJsonImportRequest.model_validate(
        {
            "type": "FeatureCollection",
            "source_name": "省级洪涝识别模型",
            "source_uri": "model://flood-v2/runs/20260722",
            "source_version": "flood-v2.3",
            "operator_code": "interp-li-jing",
            "conflict_policy": conflict_policy,
            "comment": "依据 2026-07-20 Sentinel-2 影像模型输出导入",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [126.50, 45.70],
                                [126.51, 45.70],
                                [126.51, 45.71],
                                [126.50, 45.70],
                            ]
                        ],
                    },
                    "properties": {
                        "patch_code": "DS-FLOOD-20260722-001",
                        "source_feature_id": "flood-polygon-001",
                        "disaster_type": "洪涝",
                        "severity": "重度",
                        "crop_type": "水稻",
                        "detected_at": "2026-07-20",
                        "ndvi_change": -0.31,
                    },
                }
            ],
        }
    )


def build_service() -> tuple[DisasterService, AsyncMock, AsyncMock, AsyncMock]:
    """构造通过身份校验的灾害导入服务测试替身。

    Returns:
        tuple: 服务、灾害 DAO、工作台 DAO 和用户服务。
    """
    dao = AsyncMock()
    dao.get_conflicting_patches_for_update.return_value = []
    dao.analyze_import_geometry.return_value = {
        "geometry_valid": True,
        "within_project": True,
        "area_ha": 8.25,
    }
    dao.insert_imported_patch.return_value = SimpleNamespace(id=1)
    workbench_dao = AsyncMock()
    workbench_dao.get_task_by_code_for_update.return_value = SimpleNamespace(
        id=7,
        project_id=3,
        status="interpreting",
        updated_at=None,
    )
    user_service = AsyncMock()
    user_service.require_capability.return_value = SimpleNamespace(
        user_code="interp-li-jing",
        display_name="李静",
        role_code="interpreter",
    )
    service = DisasterService(
        dao=dao,
        workbench_dao=workbench_dao,
        project_user_service=user_service,
    )
    return service, dao, workbench_dao, user_service


def test_disaster_import_rejects_duplicate_codes_in_one_file() -> None:
    """验证同一 FeatureCollection 内的斑块编号不得重复。"""
    payload = build_import_request().model_dump(mode="json")
    payload["features"].append(payload["features"][0])

    with pytest.raises(ValidationError, match="斑块编号不得重复"):
        DisasterGeoJsonImportRequest.model_validate(payload)


def test_disaster_import_persists_area_source_and_audit() -> None:
    """验证真实导入会重算面积并保存来源、用户和任务审计。"""
    service, dao, workbench_dao, user_service = build_service()
    db = AsyncMock()

    response = asyncio.run(
        service.import_geojson(db, "RS-2026-045", build_import_request())
    )

    assert response.imported_count == 1
    assert response.created_count == 1
    assert response.replaced_count == 0
    assert response.imported_by_code == "interp-li-jing"
    assert len(response.source_checksum_sha256) == 64
    user_service.require_capability.assert_awaited_once_with(
        db,
        3,
        "interp-li-jing",
        "import_disaster",
    )
    values = dao.insert_imported_patch.await_args.args[1]
    assert values["affected_area_ha"] == 8.25
    assert values["source_feature_id"] == "flood-polygon-001"
    assert values["imported_by_role"] == "interpreter"
    workbench_dao.add_review_record.assert_awaited_once()
    db.commit.assert_awaited_once()


def test_disaster_import_rejects_existing_code_without_partial_write() -> None:
    """验证 reject 策略发现已有编号时整批停止。"""
    service, dao, _, _ = build_service()
    dao.get_conflicting_patches_for_update.return_value = [
        SimpleNamespace(
            id=9,
            patch_code="DS-FLOOD-20260722-001",
            source="省级洪涝识别模型",
            source_feature_id="flood-polygon-001",
        )
    ]
    db = AsyncMock()

    with pytest.raises(ValidationException, match="斑块编号已存在"):
        asyncio.run(
            service.import_geojson(db, "RS-2026-045", build_import_request())
        )

    dao.insert_imported_patch.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_disaster_import_replace_resets_existing_patch_through_dao() -> None:
    """验证 replace 策略走锁定替换路径而不是创建重复斑块。"""
    service, dao, _, _ = build_service()
    existing = SimpleNamespace(
        id=9,
        patch_code="DS-FLOOD-20260722-001",
        source="省级洪涝识别模型",
        source_feature_id="flood-polygon-001",
    )
    dao.get_conflicting_patches_for_update.return_value = [existing]
    dao.replace_imported_patch.return_value = existing
    db = AsyncMock()

    response = asyncio.run(
        service.import_geojson(
            db,
            "RS-2026-045",
            build_import_request(conflict_policy="replace"),
        )
    )

    assert response.created_count == 0
    assert response.replaced_count == 1
    dao.replace_imported_patch.assert_awaited_once()
    dao.insert_imported_patch.assert_not_awaited()


def test_disaster_import_rejects_geometry_outside_project() -> None:
    """验证越出项目省域的灾害斑块不会落库。"""
    service, dao, _, _ = build_service()
    dao.analyze_import_geometry.return_value = {
        "geometry_valid": True,
        "within_project": False,
        "area_ha": 8.25,
    }
    db = AsyncMock()

    with pytest.raises(ValidationException, match="超出项目行政区范围"):
        asyncio.run(
            service.import_geojson(db, "RS-2026-045", build_import_request())
        )

    dao.insert_imported_patch.assert_not_awaited()
