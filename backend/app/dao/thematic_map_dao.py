"""专题图模板、实体产品和审计事件数据访问层。"""

from sqlalchemy import and_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thematic_map import (
    ThematicMapEvent,
    ThematicMapProduct,
    ThematicMapTemplate,
)
from app.models.workbench import ImageryAsset, ImageryProcessingStep


class ThematicMapDAO:
    """封装专题制图持久化查询与写入。"""

    async def list_templates(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[ThematicMapTemplate]:
        """查询项目全部版式模板。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[ThematicMapTemplate]: 按创建时间排序的模板。
        """
        result = await db.execute(
            select(ThematicMapTemplate)
            .where(ThematicMapTemplate.project_id == project_id)
            .order_by(ThematicMapTemplate.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_template_by_code(
        self,
        db: AsyncSession,
        project_id: int,
        template_code: str,
    ) -> ThematicMapTemplate | None:
        """按项目和模板编号查询版式。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。
            template_code: 模板编号。

        Returns:
            ThematicMapTemplate | None: 模板或空值。
        """
        result = await db.execute(
            select(ThematicMapTemplate).where(
                ThematicMapTemplate.project_id == project_id,
                ThematicMapTemplate.template_code == template_code,
            )
        )
        return result.scalar_one_or_none()

    async def add_template(
        self,
        db: AsyncSession,
        template: ThematicMapTemplate,
    ) -> ThematicMapTemplate:
        """新增版式模板。

        Args:
            db: 异步数据库会话。
            template: 待保存模板。

        Returns:
            ThematicMapTemplate: 已刷新模板。
        """
        db.add(template)
        await db.flush()
        await db.refresh(template)
        return template

    async def list_source_rows(
        self,
        db: AsyncSession,
        project_id: int,
    ) -> list[RowMapping]:
        """查询项目影像与其波段产品步骤。

        Args:
            db: 异步数据库会话。
            project_id: 项目主键。

        Returns:
            list[RowMapping]: 影像资产和可选波段产品步骤。
        """
        result = await db.execute(
            select(ImageryAsset, ImageryProcessingStep)
            .outerjoin(
                ImageryProcessingStep,
                and_(
                    ImageryProcessingStep.asset_id == ImageryAsset.id,
                    ImageryProcessingStep.step_code == "band_products",
                ),
            )
            .where(ImageryAsset.project_id == project_id)
            .order_by(ImageryAsset.acquired_at.desc())
        )
        return list(result.mappings().all())

    async def find_existing_product(
        self,
        db: AsyncSession,
        task_id: int,
        map_number: str,
        source_product_code: str,
        output_format: str,
    ) -> ThematicMapProduct | None:
        """查询是否存在相同任务、图号、产品和格式成果。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            map_number: 图号。
            source_product_code: 真彩色、假彩色或 NDVI。
            output_format: PNG 或 PDF。

        Returns:
            ThematicMapProduct | None: 已有成果或空值。
        """
        result = await db.execute(
            select(ThematicMapProduct).where(
                ThematicMapProduct.task_id == task_id,
                ThematicMapProduct.map_number == map_number,
                ThematicMapProduct.source_product_code == source_product_code,
                ThematicMapProduct.output_format == output_format,
            )
        )
        return result.scalar_one_or_none()

    async def add_products(
        self,
        db: AsyncSession,
        products: list[ThematicMapProduct],
    ) -> None:
        """批量保存专题图成果。

        Args:
            db: 异步数据库会话。
            products: 实体成果模型。

        Returns:
            None: 写入会话后返回。
        """
        db.add_all(products)
        await db.flush()
        for product in products:
            await db.refresh(product)

    async def list_product_rows(
        self,
        db: AsyncSession,
        task_id: int,
        limit: int = 100,
    ) -> list[RowMapping]:
        """查询任务最近专题图并关联模板和资产。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。
            limit: 最大返回数量。

        Returns:
            list[RowMapping]: 成果、模板和影像关联行。
        """
        result = await db.execute(
            select(
                ThematicMapProduct,
                ThematicMapTemplate,
                ImageryAsset,
            )
            .join(
                ThematicMapTemplate,
                ThematicMapTemplate.id == ThematicMapProduct.template_id,
            )
            .join(ImageryAsset, ImageryAsset.id == ThematicMapProduct.asset_id)
            .where(ThematicMapProduct.task_id == task_id)
            .order_by(ThematicMapProduct.generated_at.desc())
            .limit(limit)
        )
        return list(result.mappings().all())

    async def get_product_row(
        self,
        db: AsyncSession,
        product_code: str,
    ) -> RowMapping | None:
        """按成果编号查询专题图、模板和资产。

        Args:
            db: 异步数据库会话。
            product_code: 成果编号。

        Returns:
            RowMapping | None: 关联行或空值。
        """
        result = await db.execute(
            select(
                ThematicMapProduct,
                ThematicMapTemplate,
                ImageryAsset,
            )
            .join(
                ThematicMapTemplate,
                ThematicMapTemplate.id == ThematicMapProduct.template_id,
            )
            .join(ImageryAsset, ImageryAsset.id == ThematicMapProduct.asset_id)
            .where(ThematicMapProduct.product_code == product_code)
        )
        return result.mappings().one_or_none()

    async def add_event(
        self,
        db: AsyncSession,
        event: ThematicMapEvent,
    ) -> None:
        """新增不可变专题图事件。

        Args:
            db: 异步数据库会话。
            event: 事件模型。

        Returns:
            None: 刷新后返回。
        """
        db.add(event)
        await db.flush()
