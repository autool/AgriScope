"""内置双时相多算法候选发现、实体 GeoJSON 与审计持久化服务。"""

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.change_detection_dao import ChangeDetectionDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.change_detection import ChangeDetectionEvent
from app.schemas.change_detection import (
    ChangeCandidateDiscoveryRequest,
    ChangeCandidateDiscoveryResponse,
)
from app.services.change_candidate_discovery_engine import (
    ChangeCandidateDiscoveryEngine,
)
from app.services.change_comparison_service import ChangeComparisonService
from app.services.project_user_service import ProjectUserService


class ChangeCandidateDiscoveryService:
    """编排公共网格差分、面积门禁、实体成果和不可变审计。"""

    def __init__(
        self,
        dao: ChangeDetectionDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        user_service: ProjectUserService | None = None,
        comparison_service: ChangeComparisonService | None = None,
        engine: ChangeCandidateDiscoveryEngine | None = None,
    ) -> None:
        """初始化自动候选发现服务。

        Args:
            dao: 变化检测 DAO。
            workbench_dao: 项目任务公共 DAO。
            user_service: 项目用户能力服务。
            comparison_service: 双时相公共网格预览服务。
            engine: 多算法变化评分与矢量化引擎。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ChangeDetectionDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.user_service = user_service or ProjectUserService()
        self.comparison_service = comparison_service or ChangeComparisonService()
        self.engine = engine or ChangeCandidateDiscoveryEngine()
        self.storage_root = (
            Path(__file__).resolve().parents[2]
            / "storage"
            / "change_detection"
            / "discovery"
        )

    @staticmethod
    def _write_atomic(path: Path, content: bytes) -> None:
        """先写临时文件再原子替换自动候选成果。

        Args:
            path: 最终成果路径。
            content: GeoJSON 文件字节。

        Returns:
            None: 无返回值。
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.part")
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    async def discover_candidates(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        run_code: str,
        request: ChangeCandidateDiscoveryRequest,
    ) -> ChangeCandidateDiscoveryResponse:
        """运行指定内置算法并原子持久化未分类变化候选。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            run_code: 检测任务编号。
            request: 算法、阈值、连通域和操作审计参数。

        Returns:
            ChangeCandidateDiscoveryResponse: 实体成果、过滤统计和用户审计。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        if task.status != "interpreting":
            raise ValidationException("仅解译中任务允许自动发现变化候选")
        operator = await self.user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "run_change_detection",
        )
        run = await self.dao.get_run_by_code_for_update(db, task.id, run_code)
        if run is None:
            raise NotFoundException(f"未找到变化检测任务 {run_code}")
        if run.status != "active":
            raise ValidationException("每个检测任务只能生成或导入一个冻结候选批次")
        current_plot_count = await self.dao.count_task_plots(db, task.id)
        if (
            current_plot_count != run.task_plot_count
            or task.updated_at != run.task_updated_at_snapshot
        ):
            raise ValidationException(
                "任务图斑范围或数据版本已变化，请重新创建变化检测任务"
            )

        comparison = await self.comparison_service.get_metadata(
            db,
            project_code,
            task_code,
            run_code,
        )
        baseline_png, _ = await self.comparison_service.get_image(
            db,
            project_code,
            task_code,
            run_code,
            "baseline",
        )
        target_png, _ = await self.comparison_service.get_image(
            db,
            project_code,
            task_code,
            run_code,
            "target",
        )
        try:
            algorithm = self.engine.algorithm_descriptor(request.algorithm_code)
            difference_threshold = (
                request.difference_threshold
                if request.difference_threshold is not None
                else algorithm.default_threshold
            )
            discovered = self.engine.discover(
                baseline_png,
                target_png,
                comparison.bounds_wgs84,
                request.algorithm_code,
                difference_threshold,
                request.min_component_pixels,
                request.max_candidates,
            )
        except ValueError as exc:
            raise ValidationException(f"自动候选发现失败：{exc}") from exc
        if not discovered.candidates:
            raise ValidationException("当前阈值未发现显著变化候选")

        min_area_sqm = float(
            run.rule_profile_snapshot["other_agricultural_min_area_sqm"]
        )
        retained: list[dict[str, object]] = []
        filtered_below_area_count = 0
        for item in discovered.candidates:
            geometry_json = json.dumps(
                item.geometry,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            metrics = await self.dao.analyze_import_geometry(
                db,
                project.id,
                geometry_json,
            )
            if metrics is None:
                raise ValidationException("项目未配置省级行政区边界")
            if not bool(metrics["geometry_valid"]):
                raise ValidationException("自动候选包含无效 Polygon")
            if not bool(metrics["within_project"]):
                raise ValidationException("自动候选超出项目行政区范围")
            area_ha = float(metrics["area_ha"] or 0)
            if area_ha * 10000 < min_area_sqm:
                filtered_below_area_count += 1
                continue
            retained.append(
                {
                    "geometry": item.geometry,
                    "geometry_json": geometry_json,
                    "confidence": item.confidence,
                    "pixel_count": item.pixel_count,
                    "area_ha": round(area_ha, 4),
                }
            )
        if not retained:
            raise ValidationException(
                f"检测到 {len(discovered.candidates)} 个连通域，但均低于冻结规则 "
                f"{min_area_sqm:g} 平方米"
            )

        parameters = {
            "algorithm_code": discovered.algorithm_code,
            "difference_threshold": difference_threshold,
            "min_component_pixels": request.min_component_pixels,
            "max_candidates": request.max_candidates,
            "minimum_area_sqm": min_area_sqm,
            "score_formula": discovered.score_formula,
        }
        detection_fingerprint = sha256(
            json.dumps(
                {
                    "run_code": run.run_code,
                    "algorithm_code": discovered.algorithm_code,
                    "algorithm_version": discovered.algorithm_version,
                    "parameters": parameters,
                    "baseline_preview_sha256": (
                        comparison.baseline_preview_sha256
                    ),
                    "target_preview_sha256": comparison.target_preview_sha256,
                    "candidates": [
                        {
                            "geometry": item["geometry"],
                            "confidence": item["confidence"],
                            "pixel_count": item["pixel_count"],
                            "area_ha": item["area_ha"],
                        }
                        for item in retained
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        generated_at = datetime.now(UTC)
        batch_code = (
            f"CDAUTO-{generated_at:%Y%m%dT%H%M%S}-"
            f"{detection_fingerprint[:8]}-{secrets.token_hex(4)}"
        )
        candidate_codes = [
            f"AUTO-{run.run_code[:35]}-{detection_fingerprint[:8]}-{index:04d}"
            for index in range(1, len(retained) + 1)
        ]
        source_feature_ids = [
            f"{discovered.algorithm_code}-component-{index:04d}"
            for index in range(1, len(retained) + 1)
        ]
        artifact_relative_path = (
            Path(str(run.id)) / batch_code / "candidates.geojson"
        )
        artifact_uri = (
            "storage://change_detection/discovery/"
            f"{artifact_relative_path.as_posix()}"
        )
        artifact_payload = {
            "type": "FeatureCollection",
            "metadata": {
                "run_code": run.run_code,
                "algorithm_code": discovered.algorithm_code,
                "algorithm_name": discovered.algorithm_name,
                "algorithm_version": discovered.algorithm_version,
                "score_formula": discovered.score_formula,
                "parameters": parameters,
                "baseline_preview_sha256": comparison.baseline_preview_sha256,
                "target_preview_sha256": comparison.target_preview_sha256,
                "bounds_wgs84": comparison.bounds_wgs84,
                "detected_count": len(discovered.candidates),
                "filtered_below_area_count": filtered_below_area_count,
                "generated_at": generated_at.isoformat(),
            },
            "features": [
                {
                    "type": "Feature",
                    "geometry": item["geometry"],
                    "properties": {
                        "candidate_code": candidate_code,
                        "source_feature_id": source_feature_id,
                        "change_class": "unclassified",
                        "confidence": item["confidence"],
                        "pixel_count": item["pixel_count"],
                        "area_ha": item["area_ha"],
                    },
                }
                for item, candidate_code, source_feature_id in zip(
                    retained,
                    candidate_codes,
                    source_feature_ids,
                    strict=True,
                )
            ],
        }
        artifact_bytes = json.dumps(
            artifact_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        artifact_sha256 = sha256(artifact_bytes).hexdigest()
        artifact_path = self.storage_root / artifact_relative_path
        await asyncio.to_thread(self._write_atomic, artifact_path, artifact_bytes)

        try:
            for item, candidate_code, source_feature_id in zip(
                retained,
                candidate_codes,
                source_feature_ids,
                strict=True,
            ):
                candidate = await self.dao.insert_candidate(
                    db,
                    {
                        "run_id": run.id,
                        "candidate_code": candidate_code,
                        "source_name": f"AgriScope {discovered.algorithm_name}",
                        "source_uri": artifact_uri,
                        "source_version": discovered.algorithm_version,
                        "source_feature_id": source_feature_id,
                        "source_checksum_sha256": artifact_sha256,
                        "import_batch_code": batch_code,
                        "change_class": "unclassified",
                        "confidence": item["confidence"],
                        "area_ha": item["area_ha"],
                        "evidence_uri": f"{artifact_uri}#{candidate_code}",
                        "imported_by": operator.display_name,
                        "imported_by_code": operator.user_code,
                        "imported_by_role": operator.role_code,
                        "geometry": item["geometry_json"],
                    },
                )
                await self.dao.add_event(
                    db,
                    ChangeDetectionEvent(
                        run_id=run.id,
                        candidate_id=candidate.id,
                        event_type="candidate_auto_discovered",
                        previous_values={},
                        new_values={
                            "status": "pending",
                            "change_class": "unclassified",
                            "confidence": float(candidate.confidence),
                            "area_ha": float(candidate.area_ha),
                            "pixel_count": item["pixel_count"],
                            "artifact_sha256": artifact_sha256,
                            "import_batch_code": batch_code,
                        },
                        comment=request.comment,
                        operator=operator.display_name,
                        operator_code=operator.user_code,
                        operator_role=operator.role_code,
                    ),
                )
            run.status = "reviewing"
            run.updated_at = generated_at
            task.updated_at = generated_at
            await self.dao.add_event(
                db,
                ChangeDetectionEvent(
                    run_id=run.id,
                    candidate_id=None,
                    event_type="candidate_discovery_completed",
                    previous_values={"status": "active"},
                    new_values={
                        "status": "reviewing",
                        "batch_code": batch_code,
                        "algorithm_code": discovered.algorithm_code,
                        "algorithm_name": discovered.algorithm_name,
                        "algorithm_version": discovered.algorithm_version,
                        "score_formula": discovered.score_formula,
                        "parameters": parameters,
                        "detected_count": len(discovered.candidates),
                        "imported_count": len(retained),
                        "filtered_below_area_count": filtered_below_area_count,
                        "artifact_uri": artifact_uri,
                        "artifact_sha256": artifact_sha256,
                    },
                    comment=request.comment,
                    operator=operator.display_name,
                    operator_code=operator.user_code,
                    operator_role=operator.role_code,
                ),
            )
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            artifact_path.unlink(missing_ok=True)
            raise ValidationException("自动候选编号或来源要素与现有数据冲突") from exc
        except (OSError, RuntimeError, SQLAlchemyError):
            await db.rollback()
            artifact_path.unlink(missing_ok=True)
            raise
        return ChangeCandidateDiscoveryResponse(
            run_code=run_code,
            batch_code=batch_code,
            algorithm_code=discovered.algorithm_code,
            algorithm_name=discovered.algorithm_name,
            algorithm_version=discovered.algorithm_version,
            score_formula=discovered.score_formula,
            parameters=parameters,
            detected_count=len(discovered.candidates),
            imported_count=len(retained),
            filtered_below_area_count=filtered_below_area_count,
            changed_pixel_count=discovered.changed_pixel_count,
            valid_pixel_count=discovered.valid_pixel_count,
            candidate_codes=candidate_codes,
            artifact_uri=artifact_uri,
            artifact_sha256=artifact_sha256,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generated_at=generated_at,
        )
