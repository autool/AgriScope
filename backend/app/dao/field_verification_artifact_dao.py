"""外业核查实体证据数据访问对象。"""

from collections.abc import Sequence

from sqlalchemy import Row, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workbench import (
    FieldVerification,
    FieldVerificationArtifact,
    FieldVerificationArtifactEvent,
)


class FieldVerificationArtifactDAO:
    """封装外业核查实体证据与不可变事件查询。"""

    async def list_by_verification_ids(
        self,
        db: AsyncSession,
        verification_ids: list[int],
    ) -> Sequence[FieldVerificationArtifact]:
        """批量查询外业记录关联的实体证据。

        Args:
            db: 异步数据库会话。
            verification_ids: 外业记录主键列表。

        Returns:
            Sequence[FieldVerificationArtifact]: 按上传时间排列的证据。
        """
        if not verification_ids:
            return []
        result = await db.execute(
            select(FieldVerificationArtifact)
            .where(
                FieldVerificationArtifact.field_verification_id.in_(
                    verification_ids
                )
            )
            .order_by(
                FieldVerificationArtifact.created_at,
                FieldVerificationArtifact.id,
            )
        )
        return result.scalars().all()

    async def find_duplicate_for_update(
        self,
        db: AsyncSession,
        field_verification_id: int,
        checksum_sha256: str,
    ) -> FieldVerificationArtifact | None:
        """锁定并查询同一外业记录内的重复实体。

        Args:
            db: 异步数据库会话。
            field_verification_id: 外业记录主键。
            checksum_sha256: 服务端计算的文件校验值。

        Returns:
            FieldVerificationArtifact | None: 已存在证据或 None。
        """
        result = await db.execute(
            select(FieldVerificationArtifact)
            .where(
                FieldVerificationArtifact.field_verification_id
                == field_verification_id,
                FieldVerificationArtifact.checksum_sha256 == checksum_sha256,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def add_artifact(
        self,
        db: AsyncSession,
        artifact: FieldVerificationArtifact,
    ) -> FieldVerificationArtifact:
        """新增外业实体证据。

        Args:
            db: 异步数据库会话。
            artifact: 待持久化证据。

        Returns:
            FieldVerificationArtifact: 已获得主键的证据。
        """
        db.add(artifact)
        await db.flush()
        return artifact

    async def add_event(
        self,
        db: AsyncSession,
        event: FieldVerificationArtifactEvent,
    ) -> FieldVerificationArtifactEvent:
        """追加不可变外业证据事件。

        Args:
            db: 异步数据库会话。
            event: 上传或下载事件。

        Returns:
            FieldVerificationArtifactEvent: 已获得主键的事件。
        """
        db.add(event)
        await db.flush()
        return event

    async def get_artifact_record(
        self,
        db: AsyncSession,
        verification_code: str,
        artifact_code: str,
    ) -> Row[tuple[FieldVerificationArtifact, FieldVerification]] | None:
        """按外业编号和证据编号查询下载上下文。

        Args:
            db: 异步数据库会话。
            verification_code: 外业记录业务编号。
            artifact_code: 实体证据业务编号。

        Returns:
            Row | None: 证据和所属外业记录，不存在时返回 None。
        """
        result = await db.execute(
            select(FieldVerificationArtifact, FieldVerification)
            .join(
                FieldVerification,
                FieldVerification.id
                == FieldVerificationArtifact.field_verification_id,
            )
            .where(
                FieldVerification.verification_code == verification_code,
                FieldVerificationArtifact.artifact_code == artifact_code,
            )
        )
        return result.first()

    async def count_by_record_type(
        self,
        db: AsyncSession,
        field_verification_id: int,
        artifact_type: str,
    ) -> int:
        """统计外业记录指定类型的实体证据数量。

        Args:
            db: 异步数据库会话。
            field_verification_id: 外业记录主键。
            artifact_type: 证据类型。

        Returns:
            int: 实体证据数量。
        """
        result = await db.execute(
            select(func.count(FieldVerificationArtifact.id)).where(
                FieldVerificationArtifact.field_verification_id
                == field_verification_id,
                FieldVerificationArtifact.artifact_type == artifact_type,
            )
        )
        return int(result.scalar_one())

    async def count_task_records_missing_photo(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> int:
        """统计缺少实体现场照片的任务外业记录。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            int: 缺少照片实体的记录数。
        """
        photo_exists = exists(
            select(FieldVerificationArtifact.id).where(
                FieldVerificationArtifact.field_verification_id
                == FieldVerification.id,
                FieldVerificationArtifact.artifact_type == "photo",
            )
        )
        result = await db.execute(
            select(func.count(FieldVerification.id)).where(
                FieldVerification.task_id == task_id,
                ~photo_exists,
            )
        )
        return int(result.scalar_one())

    async def list_task_artifacts(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[Row[tuple[FieldVerificationArtifact, str]]]:
        """查询任务全部外业实体证据及所属记录编号。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[Row]: 证据模型和外业记录编号。
        """
        result = await db.execute(
            select(
                FieldVerificationArtifact,
                FieldVerification.verification_code.label("verification_code"),
            )
            .join(
                FieldVerification,
                FieldVerification.id
                == FieldVerificationArtifact.field_verification_id,
            )
            .where(FieldVerification.task_id == task_id)
            .order_by(
                FieldVerification.verification_code,
                FieldVerificationArtifact.created_at,
            )
        )
        return result.all()

    async def list_task_events(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> Sequence[Row[tuple[FieldVerificationArtifactEvent, str, str | None]]]:
        """查询任务外业实体证据上传与下载事件。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            Sequence[Row]: 事件、外业编号和可选证据编号。
        """
        result = await db.execute(
            select(
                FieldVerificationArtifactEvent,
                FieldVerification.verification_code.label("verification_code"),
                FieldVerificationArtifact.artifact_code.label("artifact_code"),
            )
            .join(
                FieldVerification,
                FieldVerification.id
                == FieldVerificationArtifactEvent.field_verification_id,
            )
            .outerjoin(
                FieldVerificationArtifact,
                FieldVerificationArtifact.id
                == FieldVerificationArtifactEvent.artifact_id,
            )
            .where(FieldVerification.task_id == task_id)
            .order_by(FieldVerificationArtifactEvent.created_at)
        )
        return result.all()
