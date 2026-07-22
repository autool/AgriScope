"""三级审核与图斑版本回退业务服务。"""

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.review_dao import ReviewDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.workbench import PlotVersion, QualityIssue, ReviewRecord
from app.schemas.review import (
    PlotRollbackRequest,
    PlotVersionListResponse,
    PlotVersionResponse,
    ReviewActionRequest,
    ReviewActionResponse,
)
from app.schemas.workbench import PlotAttributesResponse, TaskSummary
from app.services.project_user_service import ProjectUserService

logger = logging.getLogger(__name__)

REVIEW_CAPABILITIES = {
    "self_check": "review_self_check",
    "quality_review": "review_quality",
    "client_review": "review_client",
}


class ReviewService:
    """执行三级审核状态流转、问题生成和版本回退。"""

    def __init__(
        self,
        dao: ReviewDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化审核业务服务。

        Args:
            dao: 审核版本 DAO。
            workbench_dao: 工作台公共 DAO。
            project_user_service: 项目用户与角色校验服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ReviewDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()

    async def execute_task_action(
        self,
        db: AsyncSession,
        task_code: str,
        request: ReviewActionRequest,
    ) -> ReviewActionResponse:
        """执行任务通过、退回或驳回动作。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            request: 审核动作、人员和意见。

        Returns:
            ReviewActionResponse: 状态流转结果。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        previous_status = task.status
        pass_transitions = {
            "self_check": "quality_review",
            "quality_review": "client_review",
            "client_review": "completed",
        }
        if request.action == "pass":
            if previous_status not in pass_transitions:
                raise ValidationException("当前节点不允许执行通过操作")
            next_status = pass_transitions[previous_status]
        elif request.action == "return":
            if previous_status not in pass_transitions:
                raise ValidationException("当前节点不允许退回整改")
            if not request.comment:
                raise ValidationException("退回整改必须填写审核意见")
            next_status = "interpreting"
        else:
            if previous_status not in pass_transitions:
                raise ValidationException("当前节点不允许驳回")
            if not request.comment:
                raise ValidationException("驳回必须填写审核意见")
            next_status = "rejected"

        capability = REVIEW_CAPABILITIES.get(previous_status)
        if capability is None:
            raise ValidationException("当前节点未配置审核角色")
        reviewer = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.reviewer_code,
            capability,
        )

        if request.action == "pass" and previous_status in {
            "quality_review",
            "client_review",
        }:
            open_issue_count = await self.workbench_dao.count_open_issues(
                db,
                task.id,
            )
            if open_issue_count > 0:
                raise ValidationException(
                    f"仍有 {open_issue_count} 条问题未关闭，不能通过当前审核"
                )
        if request.action == "pass" and previous_status == "client_review":
            pending_field_count = (
                await self.workbench_dao.count_pending_field_verifications(
                    db,
                    task.id,
                )
            )
            if pending_field_count > 0:
                raise ValidationException(
                    f"仍有 {pending_field_count} 条外业疑点未处置，不能完成甲方复核"
                )

        task.status = next_status
        task.updated_at = datetime.now(UTC)
        record = await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level=previous_status,
                action=request.action,
                reviewer=reviewer.display_name,
                reviewer_code=reviewer.user_code,
                reviewer_role=reviewer.role_code,
                comment=request.comment,
            ),
        )
        if request.action in {"return", "reject"}:
            await self.workbench_dao.add_quality_issues(
                db,
                [
                    QualityIssue(
                        task_id=task.id,
                        plot_code=None,
                        rule_code=f"REVIEW_{record.id}",
                        issue_type=request.issue_type or "review_comment",
                        severity="high" if request.action == "reject" else "medium",
                        description=request.comment or "审核问题",
                        status="open",
                        source="manual",
                    )
                ],
            )
        await db.commit()
        await db.refresh(task)
        logger.info(
            "审核状态流转: task=%s, %s -> %s",
            task_code,
            previous_status,
            task.status,
        )
        return ReviewActionResponse(
            task=TaskSummary.model_validate(task),
            previous_status=previous_status,
            current_status=task.status,
            action=request.action,
            record_id=record.id,
            reviewer_code=reviewer.user_code,
            reviewer_name=reviewer.display_name,
            reviewer_role=reviewer.role_code,
        )

    async def list_plot_versions(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
    ) -> PlotVersionListResponse:
        """查询图斑当前版本和历史版本列表。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。

        Returns:
            PlotVersionListResponse: 图斑版本列表。
        """
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if not await self.workbench_dao.is_plot_assigned_to_task(
            db,
            task.id,
            plot_code,
        ):
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        plot = await self.workbench_dao.get_plot_by_code(db, plot_code)
        if plot is None:
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        versions = await self.dao.get_versions(db, plot_code)
        return PlotVersionListResponse(
            plot_code=plot_code,
            current_version=plot.version,
            versions=[PlotVersionResponse.model_validate(item) for item in versions],
        )

    async def rollback_plot(
        self,
        db: AsyncSession,
        task_code: str,
        plot_code: str,
        request: PlotRollbackRequest,
    ) -> PlotAttributesResponse:
        """将图斑内容恢复到历史版本并生成新的当前版本。

        Args:
            db: 异步数据库会话。
            task_code: 作业任务编号。
            plot_code: 图斑编号。
            request: 目标版本、操作人和说明。

        Returns:
            PlotAttributesResponse: 回退后图斑属性。
        """
        task = await self.workbench_dao.get_task_by_code_for_update(db, task_code)
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if not await self.workbench_dao.is_plot_assigned_to_task(
            db,
            task.id,
            plot_code,
        ):
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        plot = await self.workbench_dao.get_plot_by_code(db, plot_code)
        if plot is None:
            raise NotFoundException(f"当前任务未找到图斑 {plot_code}")
        target = await self.dao.get_version(db, plot_code, request.target_version)
        if target is None:
            raise NotFoundException(f"未找到图斑版本 v{request.target_version}")
        if request.target_version == plot.version:
            raise ValidationException("目标版本已是当前版本")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            request.operator_code,
            "rollback_plot",
        )

        new_version = plot.version + 1
        plot.land_class = target.land_class
        plot.crop_type = target.crop_type
        plot.planting_mode = target.planting_mode
        plot.irrigation_condition = target.irrigation_condition
        plot.interpretation_status = "interpreting"
        plot.geom = target.geom
        plot.version = new_version
        plot.updated_at = datetime.now(UTC)
        await self.dao.add_version(
            db,
            PlotVersion(
                plot_code=plot_code,
                version=new_version,
                land_class=plot.land_class,
                crop_type=plot.crop_type,
                planting_mode=plot.planting_mode,
                irrigation_condition=plot.irrigation_condition,
                interpretation_status=plot.interpretation_status,
                geom=plot.geom,
                change_summary=(
                    request.comment or f"回退至历史版本 v{request.target_version}"
                ),
                created_by=operator.display_name,
                created_by_code=operator.user_code,
                created_by_role=operator.role_code,
            ),
        )
        task.status = "interpreting"
        await self.workbench_dao.add_review_record(
            db,
            ReviewRecord(
                task_id=task.id,
                review_level="version_management",
                action="rollback",
                reviewer=operator.display_name,
                reviewer_code=operator.user_code,
                reviewer_role=operator.role_code,
                comment=f"图斑 {plot_code} 回退至 v{request.target_version}",
            ),
        )
        await db.commit()
        await db.refresh(plot)
        return PlotAttributesResponse(
            plot_code=plot.plot_code,
            owner_village=plot.owner_village,
            area_ha=float(plot.area_ha) if plot.area_ha is not None else None,
            land_class=plot.land_class,
            crop_type=plot.crop_type,
            planting_mode=plot.planting_mode,
            irrigation_condition=plot.irrigation_condition,
            interpretation_status=plot.interpretation_status,
            version=plot.version,
            updated_at=plot.updated_at,
        )
