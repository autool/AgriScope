"""灾害斑块识别与受灾范围评估业务服务。"""

import json
import secrets
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.disaster_dao import DisasterDAO
from app.dao.disaster_report_dao import DisasterReportDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import DisasterPatch, ReviewRecord
from app.schemas.disaster import (
    DisasterGeoJsonImportRequest,
    DisasterGeoJsonImportResponse,
    DisasterGroupItem,
    DisasterPatchResponse,
    DisasterPatchUpdateRequest,
    DisasterSummaryResponse,
)
from app.services.project_user_service import ProjectUserService


class DisasterService:
    """汇总灾害斑块、生成专题图层并执行人工修正。"""

    def __init__(
        self,
        dao: DisasterDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        report_dao: DisasterReportDAO | None = None,
    ) -> None:
        """初始化灾害业务服务。

        Args:
            dao: 灾害斑块 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目用户与角色校验服务。
            report_dao: 灾害专题报告 DAO。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or DisasterDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.report_dao = report_dao or DisasterReportDAO()

    @staticmethod
    def _to_patch_response(
        patch: DisasterPatch,
        geometry: dict,
    ) -> DisasterPatchResponse:
        """组装灾害斑块响应。

        Args:
            patch: 灾害斑块 ORM 对象。
            geometry: GeoJSON 几何。

        Returns:
            DisasterPatchResponse: 灾害斑块属性和审核快照。
        """
        return DisasterPatchResponse(
            patch_code=patch.patch_code,
            disaster_type=patch.disaster_type,
            severity=patch.severity,
            affected_area_ha=float(patch.affected_area_ha),
            crop_type=patch.crop_type,
            detected_at=patch.detected_at,
            ndvi_change=(
                float(patch.ndvi_change) if patch.ndvi_change is not None else None
            ),
            status=patch.status,
            source=patch.source,
            source_uri=getattr(patch, "source_uri", None),
            source_version=getattr(patch, "source_version", None),
            source_feature_id=getattr(patch, "source_feature_id", None),
            source_checksum_sha256=getattr(
                patch,
                "source_checksum_sha256",
                None,
            ),
            import_batch_code=getattr(patch, "import_batch_code", None),
            imported_by=getattr(patch, "imported_by", None),
            imported_by_code=getattr(patch, "imported_by_code", None),
            imported_by_role=getattr(patch, "imported_by_role", None),
            reviewed_by=patch.reviewed_by,
            reviewed_by_code=patch.reviewed_by_code,
            reviewed_by_role=patch.reviewed_by_role,
            review_comment=patch.review_comment,
            reviewed_at=patch.reviewed_at,
            geometry=geometry,
        )

    @staticmethod
    def _build_groups(
        items: list[DisasterPatchResponse],
        attribute: str,
        total_area: float,
    ) -> list[DisasterGroupItem]:
        """按指定属性汇总灾害数量和面积。

        Args:
            items: 灾害斑块列表。
            attribute: 聚合属性名。
            total_area: 受灾总面积。

        Returns:
            list[DisasterGroupItem]: 按面积倒序的聚合指标。
        """
        groups: dict[str, dict[str, float | int]] = defaultdict(
            lambda: {"patch_count": 0, "area_ha": 0.0}
        )
        for item in items:
            label = str(getattr(item, attribute))
            groups[label]["patch_count"] += 1
            groups[label]["area_ha"] += item.affected_area_ha
        return [
            DisasterGroupItem(
                label=label,
                patch_count=int(values["patch_count"]),
                area_ha=round(float(values["area_ha"]), 2),
                percentage=(
                    round(float(values["area_ha"]) / total_area * 100, 2)
                    if total_area
                    else 0
                ),
            )
            for label, values in sorted(
                groups.items(),
                key=lambda pair: float(pair[1]["area_ha"]),
                reverse=True,
            )
        ]

    async def get_summary(
        self,
        db: AsyncSession,
        task_code: str,
    ) -> DisasterSummaryResponse:
        """获取任务灾害斑块、受灾面积和专题图层。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。

        Returns:
            DisasterSummaryResponse: 灾害评估汇总。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        rows = await self.dao.get_patches(db, task.id)
        items = [
            self._to_patch_response(patch, json.loads(geometry))
            for patch, geometry in rows
        ]
        included_items = [item for item in items if item.status != "excluded"]
        total_area = round(sum(item.affected_area_ha for item in included_items), 2)
        features = [
            {
                "type": "Feature",
                "geometry": item.geometry,
                "properties": item.model_dump(exclude={"geometry"}, mode="json"),
            }
            for item in items
        ]
        return DisasterSummaryResponse(
            task_code=task_code,
            generated_at=datetime.now(UTC),
            total_patches=len(included_items),
            affected_area_ha=total_area,
            pending_count=sum(item.status == "pending" for item in items),
            confirmed_count=sum(item.status == "confirmed" for item in items),
            by_severity=self._build_groups(included_items, "severity", total_area),
            by_type=self._build_groups(included_items, "disaster_type", total_area),
            items=items,
            feature_collection={"type": "FeatureCollection", "features": features},
        )

    async def import_geojson(
        self,
        db: AsyncSession,
        task_code: str,
        request: DisasterGeoJsonImportRequest,
    ) -> DisasterGeoJsonImportResponse:
        """导入灾害模型 GeoJSON 并保存来源与用户审计。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 已校验的标准 FeatureCollection 和来源信息。

        Returns:
            DisasterGeoJsonImportResponse: 批次编号和新增/替换统计。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.status != "interpreting":
            raise ValidationException("仅解译中任务允许导入灾害模型结果")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "import_disaster",
        )
        source_payload = {
            "type": request.type,
            "features": [
                feature.model_dump(mode="json") for feature in request.features
            ],
        }
        source_checksum = sha256(
            json.dumps(
                source_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        imported_at = datetime.now(UTC)
        batch_code = (
            f"DSIMP-{imported_at:%Y%m%dT%H%M%S}-"
            f"{source_checksum[:8]}-{secrets.token_hex(4)}"
        )
        patch_codes = [
            feature.properties.patch_code for feature in request.features
        ]
        source_feature_ids = [
            feature.properties.source_feature_id for feature in request.features
        ]
        conflicts = await self.dao.get_conflicting_patches_for_update(
            db,
            task.id,
            patch_codes,
            request.source_name,
            source_feature_ids,
        )
        existing_by_code = {patch.patch_code: patch for patch in conflicts}
        imported_source_keys = {
            (request.source_name, source_feature_id): patch_code
            for source_feature_id, patch_code in zip(
                source_feature_ids,
                patch_codes,
                strict=True,
            )
        }
        for patch in conflicts:
            source_key = (patch.source, patch.source_feature_id)
            requested_code = imported_source_keys.get(source_key)
            if requested_code and requested_code != patch.patch_code:
                raise ValidationException(
                    f"来源要素 {patch.source_feature_id} 已绑定斑块 "
                    f"{patch.patch_code}，不得改用编号 {requested_code}"
                )
        duplicate_codes = sorted(set(existing_by_code).intersection(patch_codes))
        if duplicate_codes and request.conflict_policy == "reject":
            preview = "、".join(duplicate_codes[:5])
            suffix = "等" if len(duplicate_codes) > 5 else ""
            raise ValidationException(f"灾害斑块编号已存在：{preview}{suffix}")

        prepared_values: list[dict[str, object]] = []
        for feature in request.features:
            geometry_json = json.dumps(
                feature.geometry.model_dump(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
            metrics = await self.dao.analyze_import_geometry(
                db,
                task.project_id,
                geometry_json,
            )
            patch_code = feature.properties.patch_code
            if metrics is None:
                raise ValidationException("项目未配置省级行政区边界")
            if not bool(metrics["geometry_valid"]):
                raise ValidationException(f"灾害斑块 {patch_code} 几何无效")
            if not bool(metrics["within_project"]):
                raise ValidationException(
                    f"灾害斑块 {patch_code} 超出项目行政区范围"
                )
            area_ha = float(metrics["area_ha"] or 0)
            if area_ha <= 0:
                raise ValidationException(f"灾害斑块 {patch_code} 面积必须大于 0")
            properties = feature.properties
            prepared_values.append(
                {
                    "task_id": task.id,
                    "patch_code": patch_code,
                    "disaster_type": properties.disaster_type,
                    "severity": properties.severity,
                    "affected_area_ha": round(area_ha, 4),
                    "crop_type": properties.crop_type,
                    "detected_at": properties.detected_at,
                    "ndvi_change": properties.ndvi_change,
                    "source": request.source_name,
                    "source_uri": request.source_uri,
                    "source_version": request.source_version,
                    "source_feature_id": properties.source_feature_id,
                    "source_checksum_sha256": source_checksum,
                    "import_batch_code": batch_code,
                    "imported_by": operator.display_name,
                    "imported_by_code": operator.user_code,
                    "imported_by_role": operator.role_code,
                    "geometry": geometry_json,
                }
            )

        created_count = 0
        replaced_count = 0
        try:
            await self.report_dao.supersede_completed_reports(db, task.id)
            for values in prepared_values:
                existing = existing_by_code.get(str(values["patch_code"]))
                if existing is None:
                    await self.dao.insert_imported_patch(db, values)
                    created_count += 1
                else:
                    await self.dao.replace_imported_patch(db, existing.id, values)
                    replaced_count += 1
            task.updated_at = imported_at
            await self.workbench_dao.add_review_record(
                db,
                ReviewRecord(
                    task_id=task.id,
                    review_level="disaster_monitoring",
                    action="disaster_geojson_imported",
                    reviewer=operator.display_name,
                    reviewer_code=operator.user_code,
                    reviewer_role=operator.role_code,
                    comment=(
                        f"批次 {batch_code} 导入 {len(prepared_values)} 个灾害斑块；"
                        f"新增 {created_count}，替换 {replaced_count}；"
                        f"来源 {request.source_name} {request.source_version}；"
                        f"SHA256 {source_checksum}；{request.comment}"
                    ),
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ValidationException(
                "灾害斑块编号或来源要素与现有数据冲突"
            ) from exc
        return DisasterGeoJsonImportResponse(
            task_code=task_code,
            batch_code=batch_code,
            imported_count=len(prepared_values),
            created_count=created_count,
            replaced_count=replaced_count,
            patch_codes=patch_codes,
            source_checksum_sha256=source_checksum,
            imported_by=operator.display_name,
            imported_by_code=operator.user_code,
            imported_by_role=operator.role_code,
            imported_at=imported_at,
        )

    async def update_patch(
        self,
        db: AsyncSession,
        task_code: str,
        patch_code: str,
        request: DisasterPatchUpdateRequest,
    ) -> DisasterPatchResponse:
        """人工修正灾害等级并写入审核记录。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            patch_code: 灾害斑块编号。
            request: 修正等级、状态、人员和说明。

        Returns:
            DisasterPatchResponse: 修正后的灾害斑块。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        patch = await self.dao.get_patch_by_code_for_update(db, patch_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if patch is None or patch.task_id != task.id:
            raise NotFoundException(f"未找到灾害斑块 {patch_code}")
        reviewer = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.reviewer_code,
            "review_disaster",
        )
        patch.severity = request.severity
        patch.status = request.status
        reviewed_at = datetime.now(UTC)
        patch.reviewed_by = reviewer.display_name
        patch.reviewed_by_code = reviewer.user_code
        patch.reviewed_by_role = reviewer.role_code
        patch.review_comment = request.comment or "人工复核灾害斑块"
        patch.reviewed_at = reviewed_at
        patch.updated_at = reviewed_at
        task.updated_at = reviewed_at
        await self.report_dao.supersede_completed_reports(db, task.id)
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="disaster_monitoring",
                action="disaster_patch_updated",
                reviewer=reviewer.display_name,
                reviewer_code=reviewer.user_code,
                reviewer_role=reviewer.role_code,
                comment=(
                    f"{patch_code}: {request.severity}/{request.status}"
                    f" - {request.comment or '人工复核灾害斑块'}"
                ),
            ),
        )
        await db.commit()
        await db.refresh(patch)
        geometry = json.loads(await self.dao.get_patch_geometry(db, patch_code))
        return self._to_patch_response(patch, geometry)
