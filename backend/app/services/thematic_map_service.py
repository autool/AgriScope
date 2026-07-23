"""专题图模板、实体生成、来源校验、下载和审计业务服务。"""

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.imagery_dao import ImageryDAO
from app.dao.thematic_map_dao import ThematicMapDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.thematic_map import (
    ThematicMapEvent,
    ThematicMapProduct,
    ThematicMapTemplate,
)
from app.models.workbench import ImageryAsset, ImageryProcessingStep
from app.schemas.thematic_map import (
    ThematicMapBatchGenerateRequest,
    ThematicMapBatchGenerateResponse,
    ThematicMapOverviewResponse,
    ThematicMapProductResponse,
    ThematicMapSourceResponse,
    ThematicMapTemplateCreateRequest,
    ThematicMapTemplateResponse,
)
from app.services.imagery_service import ImageryService
from app.services.project_user_service import ProjectUserService
from app.services.thematic_map_atlas_service import ThematicMapAtlasService
from app.services.thematic_map_renderer import ThematicMapRenderer


@dataclass(frozen=True)
class ThematicMapDownload:
    """已校验专题图下载内容。"""

    content: bytes
    media_type: str
    filename: str


class ThematicMapService:
    """编排模板管理、实体制图、批量事务和下载审计。"""

    def __init__(
        self,
        dao: ThematicMapDAO | None = None,
        imagery_dao: ImageryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        imagery_service: ImageryService | None = None,
        renderer: ThematicMapRenderer | None = None,
        atlas_service: ThematicMapAtlasService | None = None,
    ) -> None:
        """初始化专题制图业务服务。

        Args:
            dao: 专题图 DAO。
            imagery_dao: 影像资产和步骤 DAO。
            workbench_dao: 项目任务 DAO。
            project_user_service: 项目成员权限服务。
            imagery_service: 影像实体产物校验服务。
            renderer: 专题图实体渲染器。
            atlas_service: 独立专题图集业务服务。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ThematicMapDAO()
        self.imagery_dao = imagery_dao or ImageryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.imagery_service = imagery_service or ImageryService()
        self.renderer = renderer or ThematicMapRenderer()
        self.atlas_service = atlas_service or ThematicMapAtlasService(
            dao=self.dao,
            workbench_dao=self.workbench_dao,
            project_user_service=self.project_user_service,
        )
        self.storage_root = (
            Path(__file__).resolve().parents[2] / "storage" / "thematic_maps"
        )

    def _resolve_storage_path(self, relative_path: str) -> Path:
        """解析并限制专题图受控存储路径。

        Args:
            relative_path: 相对于专题图存储根目录的路径。

        Returns:
            Path: 未越界的绝对路径。
        """
        root = self.storage_root.resolve()
        resolved = (root / relative_path).resolve()
        if not resolved.is_relative_to(root):
            raise ValidationException("专题图存储路径越界")
        return resolved

    @staticmethod
    def _template_response(
        template: ThematicMapTemplate,
    ) -> ThematicMapTemplateResponse:
        """转换模板响应。

        Args:
            template: 模板模型。

        Returns:
            ThematicMapTemplateResponse: 模板响应。
        """
        return ThematicMapTemplateResponse.model_validate(template)

    @staticmethod
    def _media_type(output_format: str) -> str:
        """获取专题图文件媒体类型。

        Args:
            output_format: png 或 pdf。

        Returns:
            str: HTTP 媒体类型。
        """
        return "image/png" if output_format == "png" else "application/pdf"

    def verify_product_file(self, product: ThematicMapProduct) -> Path:
        """重新校验专题图路径、大小、签名和 SHA256。

        Args:
            product: 专题图产品模型。

        Returns:
            Path: 已通过校验的物理文件。
        """
        prefix = "storage://thematic_maps/"
        if not product.file_uri.startswith(prefix):
            raise ValidationException("专题图未登记受控文件地址")
        path = self._resolve_storage_path(product.file_uri.removeprefix(prefix))
        if not path.is_file():
            raise ValidationException("专题图实体文件不存在")
        if path.stat().st_size != product.file_size_bytes:
            raise ValidationException("专题图实体大小与登记值不一致")
        signature = path.read_bytes()[:8]
        if product.output_format == "png" and signature != b"\x89PNG\r\n\x1a\n":
            raise ValidationException("专题图 PNG 文件签名不合法")
        if product.output_format == "pdf" and not signature.startswith(b"%PDF-"):
            raise ValidationException("专题图 PDF 文件签名不合法")
        if calculate_sha256(path) != product.checksum_sha256:
            raise ValidationException("专题图实体 SHA256 与登记值不一致")
        return path

    def _product_response(
        self,
        product: ThematicMapProduct,
        template: ThematicMapTemplate,
        asset: ImageryAsset,
    ) -> ThematicMapProductResponse:
        """组装专题图成果及下载信息。

        Args:
            product: 成果模型。
            template: 使用的模板。
            asset: 来源影像资产。

        Returns:
            ThematicMapProductResponse: 可供前端展示的成果。
        """
        try:
            self.verify_product_file(product)
            effective_status = "completed"
        except ValidationException:
            effective_status = "invalid"
        download_url = f"/api/v1/thematic-maps/products/{product.product_code}/download"
        return ThematicMapProductResponse(
            product_code=product.product_code,
            template_code=template.template_code,
            asset_code=asset.asset_code,
            map_name=product.map_name,
            map_number=product.map_number,
            map_date=product.map_date,
            source_product_code=product.source_product_code,
            output_format=product.output_format,
            status=effective_status,
            file_size_bytes=product.file_size_bytes,
            checksum_sha256=product.checksum_sha256,
            page_width_px=product.page_width_px,
            page_height_px=product.page_height_px,
            dpi=product.dpi,
            source_uri=product.source_uri,
            source_checksum_sha256=product.source_checksum_sha256,
            source_bounds_wgs84=product.source_bounds_wgs84,
            render_manifest=product.render_manifest,
            generated_by=product.generated_by,
            generated_by_code=product.generated_by_code,
            generated_by_role=product.generated_by_role,
            generated_at=product.generated_at,
            download_url=download_url,
            preview_url=download_url if product.output_format == "png" else None,
        )

    async def _project_task(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> tuple[object, object]:
        """加载并校验项目任务归属。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。

        Returns:
            tuple[object, object]: 项目和任务。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None:
            raise NotFoundException(f"未找到任务 {task_code}")
        if task.project_id != project.id:
            raise ValidationException("专题制图任务不属于当前项目")
        return project, task

    async def create_template(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ThematicMapTemplateCreateRequest,
    ) -> ThematicMapTemplateResponse:
        """创建真实持久化版式模板并保存审计。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 审计所属任务编号。
            request: 完整模板版式参数和操作人。

        Returns:
            ThematicMapTemplateResponse: 新模板。
        """
        project, task = await self._project_task(db, project_code, task_code)
        operator = await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_thematic_maps",
        )
        if await self.dao.get_template_by_code(
            db,
            project.id,
            request.template_code,
        ):
            raise ValidationException(f"专题图模板 {request.template_code} 已存在")
        template = await self.dao.add_template(
            db,
            ThematicMapTemplate(
                project_id=project.id,
                template_code=request.template_code,
                template_name=request.template_name,
                title_pattern=request.title_pattern,
                producer=request.producer,
                page_width_px=request.page_width_px,
                page_height_px=request.page_height_px,
                dpi=request.dpi,
                margin_px=request.margin_px,
                legend_position=request.legend_position,
                include_neatline=request.include_neatline,
                include_north_arrow=request.include_north_arrow,
                include_scale_bar=request.include_scale_bar,
                created_by=operator.display_name,
                created_by_code=operator.user_code,
                created_by_role=operator.role_code,
            ),
        )
        await self.dao.add_event(
            db,
            ThematicMapEvent(
                task_id=task.id,
                entity_type="template",
                entity_code=template.template_code,
                action="template_created",
                event_values=request.model_dump(mode="json"),
                comment=request.comment,
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        return self._template_response(template)

    def _source_response(
        self,
        asset: ImageryAsset,
        step: ImageryProcessingStep | None,
    ) -> ThematicMapSourceResponse:
        """复核影像产品并生成来源响应。

        Args:
            asset: 影像资产。
            step: 波段产品步骤。

        Returns:
            ThematicMapSourceResponse: 可用产品或明确不可用原因。
        """
        if asset.data_status != "operational":
            return ThematicMapSourceResponse(
                asset_code=asset.asset_code,
                asset_name=asset.asset_name,
                acquired_at=asset.acquired_at,
                data_status=asset.data_status,
                source_uri=None,
                source_checksum_sha256=None,
                available_products=[],
                eligible=False,
                unavailable_reason="演示影像不得生成正式专题图",
            )
        if step is None:
            return ThematicMapSourceResponse(
                asset_code=asset.asset_code,
                asset_name=asset.asset_name,
                acquired_at=asset.acquired_at,
                data_status=asset.data_status,
                source_uri=None,
                source_checksum_sha256=None,
                available_products=[],
                eligible=False,
                unavailable_reason="尚未生成波段与指数实体产物",
            )
        try:
            _, evidence = self.imagery_service.resolve_verified_step_artifact_path(step)
        except ValidationException as exc:
            return ThematicMapSourceResponse(
                asset_code=asset.asset_code,
                asset_name=asset.asset_name,
                acquired_at=asset.acquired_at,
                data_status=asset.data_status,
                source_uri=step.output_uri,
                source_checksum_sha256=None,
                available_products=[],
                eligible=False,
                unavailable_reason=exc.message,
            )
        return ThematicMapSourceResponse(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            acquired_at=asset.acquired_at,
            data_status=asset.data_status,
            source_uri=step.output_uri,
            source_checksum_sha256=evidence.get("checksum_sha256"),
            available_products=["true_color", "false_color", "ndvi"],
            eligible=True,
            unavailable_reason=None,
        )

    async def get_overview(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
    ) -> ThematicMapOverviewResponse:
        """查询模板、真实来源和最近实体专题图。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。

        Returns:
            ThematicMapOverviewResponse: 专题制图完整总览。
        """
        project, task = await self._project_task(db, project_code, task_code)
        templates = await self.dao.list_templates(db, project.id)
        source_rows = await self.dao.list_source_rows(db, project.id)
        sources = [
            self._source_response(
                row[ImageryAsset],
                row[ImageryProcessingStep],
            )
            for row in source_rows
        ]
        product_rows = await self.dao.list_product_rows(db, task.id)
        products = [
            self._product_response(
                row[ThematicMapProduct],
                row[ThematicMapTemplate],
                row[ImageryAsset],
            )
            for row in product_rows
        ]
        atlas_eligible_product_count, atlases = await self.atlas_service.build_overview(
            db,
            task.id,
        )
        return ThematicMapOverviewResponse(
            project_code=project_code,
            task_code=task_code,
            template_count=len(templates),
            eligible_source_count=sum(source.eligible for source in sources),
            product_count=len(products),
            atlas_eligible_product_count=atlas_eligible_product_count,
            atlas_count=len(atlases),
            templates=[self._template_response(item) for item in templates],
            sources=sources,
            products=products,
            atlases=atlases,
        )

    async def generate_batch(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ThematicMapBatchGenerateRequest,
    ) -> ThematicMapBatchGenerateResponse:
        """从一个已校验波段产品实体原子批量生成专题图。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            request: 模板、影像、1–12 张图定义和操作人。

        Returns:
            ThematicMapBatchGenerateResponse: 全部生成成果。
        """
        project, task = await self._project_task(db, project_code, task_code)
        operator = await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "generate_thematic_maps",
        )
        template = await self.dao.get_template_by_code(
            db,
            project.id,
            request.template_code,
        )
        if template is None:
            raise NotFoundException(f"未找到专题图模板 {request.template_code}")
        asset = await self.imagery_dao.get_asset_by_code(db, request.asset_code)
        if asset is None or asset.project_id != project.id:
            raise NotFoundException(f"未找到当前项目影像 {request.asset_code}")
        if asset.data_status != "operational":
            raise ValidationException("演示影像不得生成正式专题图")
        step = await self.imagery_dao.get_step(db, asset.id, "band_products")
        if step is None:
            raise ValidationException("影像尚未生成波段与指数实体产物")
        source_path, source_evidence = (
            self.imagery_service.resolve_verified_step_artifact_path(step)
        )
        source_uri = str(step.output_uri or "")
        source_checksum = str(source_evidence.get("checksum_sha256") or "")
        asset_tags = (asset.raster_metadata or {}).get("tags") or {}
        security_classification = str(
            asset_tags.get("SECURITY_CLASSIFICATION") or "internal"
        ).lower()
        classification_label = (
            "公开数据 · 非法定调查成果"
            if security_classification == "public"
            else "项目业务数据"
        )
        source_asset_lineage = {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "data_status": asset.data_status,
            "acquired_at": asset.acquired_at.isoformat(),
            "processing_level": asset.processing_level,
            "security_classification": security_classification,
            "stac_item_id": asset_tags.get("STAC_ITEM_ID"),
            "stac_item_url": asset_tags.get("STAC_ITEM_URL"),
            "source_product_uri": asset_tags.get("SOURCE_PRODUCT_URI"),
            "source_processing_baseline": asset_tags.get(
                "SOURCE_PROCESSING_BASELINE"
            ),
            "source_provider": asset_tags.get("SOURCE_PROVIDER"),
            "source_license": asset_tags.get("SOURCE_LICENSE"),
            "source_license_url": asset_tags.get("SOURCE_LICENSE_URL"),
        }
        for item in request.items:
            duplicate = await self.dao.find_existing_product(
                db,
                task.id,
                item.map_number,
                item.source_product_code,
                item.output_format,
            )
            if duplicate is not None:
                raise ValidationException(
                    f"图号 {item.map_number} 的 {item.source_product_code}/"
                    f"{item.output_format} 成果已存在"
                )
        final_paths: list[Path] = []
        products: list[ThematicMapProduct] = []
        try:
            for item in request.items:
                product_code = (
                    f"TM-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-"
                    f"{uuid4().hex[:12].upper()}"
                )
                result = await asyncio.to_thread(
                    self.renderer.render,
                    source_path,
                    item.source_product_code,
                    item.output_format,
                    template,
                    item.map_name,
                    item.map_number,
                    item.map_date,
                    classification_label,
                )
                relative_path = (
                    Path(task_code)
                    / f"{product_code}{result.file_suffix}"
                ).as_posix()
                final_path = self._resolve_storage_path(relative_path)
                final_path.parent.mkdir(parents=True, exist_ok=True)
                temporary_path = final_path.with_name(
                    f".{final_path.name}.{uuid4().hex}.tmp"
                )
                try:
                    temporary_path.write_bytes(result.content)
                    os.replace(temporary_path, final_path)
                finally:
                    temporary_path.unlink(missing_ok=True)
                final_paths.append(final_path)
                file_size = final_path.stat().st_size
                checksum = await asyncio.to_thread(calculate_sha256, final_path)
                products.append(
                    ThematicMapProduct(
                        template_id=template.id,
                        task_id=task.id,
                        asset_id=asset.id,
                        product_code=product_code,
                        map_name=item.map_name,
                        map_number=item.map_number,
                        map_date=item.map_date,
                        source_product_code=item.source_product_code,
                        output_format=item.output_format,
                        status="completed",
                        file_uri=f"storage://thematic_maps/{relative_path}",
                        file_size_bytes=file_size,
                        checksum_sha256=checksum,
                        page_width_px=template.page_width_px,
                        page_height_px=template.page_height_px,
                        dpi=template.dpi,
                        source_uri=source_uri,
                        source_checksum_sha256=source_checksum,
                        source_bounds_wgs84=result.manifest[
                            "source_bounds_wgs84"
                        ],
                        render_manifest={
                            **result.manifest,
                            "source_uri": source_uri,
                            "source_checksum_sha256": source_checksum,
                            "source_asset_lineage": source_asset_lineage,
                            "security_classification": security_classification,
                            "file_media_type": result.media_type,
                        },
                        generated_by=operator.display_name,
                        generated_by_code=operator.user_code,
                        generated_by_role=operator.role_code,
                    )
                )
            await self.dao.add_products(db, products)
            for product in products:
                await self.dao.add_event(
                    db,
                    ThematicMapEvent(
                        task_id=task.id,
                        entity_type="product",
                        entity_code=product.product_code,
                        action="product_generated",
                        event_values={
                            "map_number": product.map_number,
                            "source_product_code": product.source_product_code,
                            "output_format": product.output_format,
                            "file_size_bytes": product.file_size_bytes,
                            "checksum_sha256": product.checksum_sha256,
                            "source_checksum_sha256": source_checksum,
                            "security_classification": security_classification,
                        },
                        comment=request.comment,
                        operator=operator.display_name,
                        operator_code=operator.user_code,
                        operator_role=operator.role_code,
                    ),
                )
            await db.commit()
        except BaseException:
            await db.rollback()
            for path in final_paths:
                path.unlink(missing_ok=True)
            raise
        return ThematicMapBatchGenerateResponse(
            generated_count=len(products),
            products=[
                self._product_response(product, template, asset)
                for product in products
            ],
        )

    async def get_download(
        self,
        db: AsyncSession,
        product_code: str,
        operator_code: str,
        disposition: str,
    ) -> ThematicMapDownload:
        """鉴权、复核实体并记录专题图预览或下载。

        Args:
            db: 异步数据库会话。
            product_code: 专题图成果编号。
            operator_code: 下载人稳定编码。
            disposition: inline 或 attachment。

        Returns:
            ThematicMapDownload: 文件内容、类型和文件名。
        """
        row = await self.dao.get_product_row(db, product_code)
        if row is None:
            raise NotFoundException(f"未找到专题图成果 {product_code}")
        product = row[ThematicMapProduct]
        template = row[ThematicMapTemplate]
        operator = await self.project_user_service.require_capability(
            db,
            template.project_id,
            operator_code,
            "view_thematic_maps"
            if disposition == "inline"
            else "download_thematic_maps",
        )
        path = self.verify_product_file(product)
        task = await self.workbench_dao.get_task_by_id(db, product.task_id)
        if task is None:
            raise NotFoundException("专题图所属任务不存在")
        await self.dao.add_event(
            db,
            ThematicMapEvent(
                task_id=product.task_id,
                entity_type="product",
                entity_code=product.product_code,
                action="product_previewed"
                if disposition == "inline"
                else "product_downloaded",
                event_values={
                    "file_size_bytes": product.file_size_bytes,
                    "checksum_sha256": product.checksum_sha256,
                    "disposition": disposition,
                },
                comment=(
                    "在线预览专题图"
                    if disposition == "inline"
                    else "下载专题图成果"
                ),
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        return ThematicMapDownload(
            content=path.read_bytes(),
            media_type=self._media_type(product.output_format),
            filename=f"{product.map_number}_{product.source_product_code}."
            f"{product.output_format}",
        )
