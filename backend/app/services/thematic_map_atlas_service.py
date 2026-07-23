"""任务专题图集生成、版本、实体复核和交付当前性服务。"""

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.core.imagery_files import calculate_sha256
from app.dao.thematic_map_dao import ThematicMapDAO
from app.dao.workbench_dao import WorkbenchDAO
from app.models.thematic_map import (
    ThematicMapAtlas,
    ThematicMapAtlasItem,
    ThematicMapEvent,
    ThematicMapProduct,
)
from app.schemas.thematic_map import (
    ThematicMapAtlasGenerateRequest,
    ThematicMapAtlasGenerateResponse,
    ThematicMapAtlasItemResponse,
    ThematicMapAtlasResponse,
)
from app.services.project_user_service import ProjectUserService
from app.services.thematic_map_atlas_renderer import (
    ThematicMapAtlasRenderer,
    ThematicMapAtlasSource,
)


@dataclass(frozen=True)
class ThematicMapAtlasDownload:
    """已校验专题图集 ZIP 下载内容。"""

    content: bytes
    media_type: str
    filename: str


class ThematicMapAtlasService:
    """管理完整专题图集合、图集版本和校验型实体下载。"""

    def __init__(
        self,
        dao: ThematicMapDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
        renderer: ThematicMapAtlasRenderer | None = None,
    ) -> None:
        """初始化专题图集服务。

        Args:
            dao: 专题图和图集 DAO。
            workbench_dao: 项目任务 DAO。
            project_user_service: 项目稳定用户能力服务。
            renderer: 封面、目录和 PDF 编排器。

        Returns:
            None: 无返回值。
        """
        self.dao = dao or ThematicMapDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()
        self.renderer = renderer or ThematicMapAtlasRenderer()
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
            raise ValidationException("专题图集存储路径越界")
        return resolved

    def verify_product_file(self, product: ThematicMapProduct) -> Path:
        """重新校验图集来源 PNG 专题图。

        Args:
            product: 专题图产品模型。

        Returns:
            Path: 已通过路径、签名、大小和 SHA256 校验的 PNG。
        """
        prefix = "storage://thematic_maps/"
        if product.output_format != "png" or not product.file_uri.startswith(prefix):
            raise ValidationException("图集来源必须是受控 PNG 专题图")
        path = self._resolve_storage_path(product.file_uri.removeprefix(prefix))
        if not path.is_file():
            raise ValidationException("图集来源专题图实体不存在")
        if path.stat().st_size != product.file_size_bytes:
            raise ValidationException("图集来源专题图大小与登记值不一致")
        with path.open("rb") as source:
            signature = source.read(8)
        if signature != b"\x89PNG\r\n\x1a\n":
            raise ValidationException("图集来源专题图 PNG 签名不合法")
        if calculate_sha256(path) != product.checksum_sha256:
            raise ValidationException("图集来源专题图 SHA256 与登记值不一致")
        return path

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
            raise ValidationException("专题图集任务不属于当前项目")
        return project, task

    @staticmethod
    def _source_snapshot(
        products: list[ThematicMapProduct],
    ) -> tuple[str, datetime]:
        """计算当前全部有效 PNG 专题图的规范化来源快照。

        Args:
            products: 已通过实体复核的 PNG 专题图。

        Returns:
            tuple[str, datetime]: 来源 SHA256 和最近生成时间。
        """
        if not products:
            raise ValidationException("当前任务没有可用于图集的 PNG 专题图")
        payload = [
            {
                "product_code": product.product_code,
                "map_number": product.map_number,
                "map_name": product.map_name,
                "map_date": product.map_date.isoformat(),
                "file_size_bytes": product.file_size_bytes,
                "checksum_sha256": product.checksum_sha256,
                "generated_at": product.generated_at.isoformat(),
            }
            for product in sorted(products, key=lambda item: item.product_code)
        ]
        digest = hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return digest, max(product.generated_at for product in products)

    def verify_atlas_package(
        self,
        atlas: ThematicMapAtlas,
        items: list[ThematicMapAtlasItem],
    ) -> Path:
        """复核图集 ZIP、PDF、manifest 和全部原始专题图成员。

        Args:
            atlas: 图集主记录。
            items: 图集成员快照。

        Returns:
            Path: 已通过完整性校验的实体 ZIP。
        """
        prefix = "storage://thematic_maps/"
        if not atlas.package_uri.startswith(prefix):
            raise ValidationException("专题图集未登记受控文件地址")
        path = self._resolve_storage_path(atlas.package_uri.removeprefix(prefix))
        if not path.is_file():
            raise ValidationException("专题图集实体包不存在")
        if path.stat().st_size != atlas.package_size_bytes:
            raise ValidationException("专题图集实体包大小与登记值不一致")
        with path.open("rb") as source:
            signature = source.read(4)
        if signature != b"PK\x03\x04":
            raise ValidationException("专题图集不是有效 ZIP")
        if calculate_sha256(path) != atlas.package_checksum_sha256:
            raise ValidationException("专题图集 ZIP SHA256 与登记值不一致")
        expected_names = {
            "manifest.json",
            atlas.pdf_filename,
            *(item.member_path for item in items),
        }
        try:
            with ZipFile(path) as archive:
                names = archive.namelist()
                if (
                    len(names) != len(expected_names)
                    or set(names) != expected_names
                    or any(
                        name.startswith("/") or ".." in Path(name).parts
                        for name in names
                    )
                ):
                    raise ValidationException("专题图集 ZIP 成员不完整或不安全")
                manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                pdf_content = archive.read(atlas.pdf_filename)
                member_contents = {
                    item.member_path: archive.read(item.member_path)
                    for item in items
                }
        except (BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationException("专题图集 ZIP 或 manifest 损坏") from exc
        if manifest != atlas.atlas_manifest:
            raise ValidationException("专题图集 manifest 与数据库快照不一致")
        if (
            not pdf_content.startswith(b"%PDF-")
            or len(pdf_content) != atlas.pdf_size_bytes
            or hashlib.sha256(pdf_content).hexdigest()
            != atlas.pdf_checksum_sha256
        ):
            raise ValidationException("专题图集 PDF 实体校验失败")
        try:
            reader = PdfReader(BytesIO(pdf_content), strict=True)
        except PdfReadError as exc:
            raise ValidationException("专题图集 PDF 结构损坏") from exc
        if reader.is_encrypted or len(reader.pages) != atlas.pdf_page_count:
            raise ValidationException("专题图集 PDF 页数或加密状态校验失败")
        if len(items) != atlas.member_count:
            raise ValidationException("专题图集成员数量与数据库快照不一致")
        for item in items:
            content = member_contents[item.member_path]
            if (
                len(content) != item.product_size_bytes
                or hashlib.sha256(content).hexdigest()
                != item.product_checksum_sha256
            ):
                raise ValidationException(
                    f"专题图集成员 {item.product_code} 实体校验失败"
                )
        return path

    @staticmethod
    def _stale_reason(
        atlas: ThematicMapAtlas,
        current_product_count: int,
        current_product_latest_at: datetime | None,
        current_source_snapshot_sha256: str | None,
    ) -> str | None:
        """判断图集是否仍覆盖任务当前全部有效 PNG 专题图。

        Args:
            atlas: 图集记录。
            current_product_count: 当前有效 PNG 专题图数量。
            current_product_latest_at: 当前最近成图时间。
            current_source_snapshot_sha256: 当前来源摘要。

        Returns:
            str | None: 失效原因或空值。
        """
        if atlas.status == "superseded":
            return "图集已被新版本替代"
        if atlas.status != "completed":
            return "图集未处于已完成状态"
        if current_product_count != atlas.product_count_snapshot:
            return "任务 PNG 专题图数量在图集生成后发生变化"
        if current_product_latest_at != atlas.product_latest_at_snapshot:
            return "任务 PNG 专题图在图集生成后发生更新"
        if current_source_snapshot_sha256 != atlas.source_snapshot_sha256:
            return "任务 PNG 专题图实体来源快照发生变化"
        return None

    def _response(
        self,
        atlas: ThematicMapAtlas,
        items: list[ThematicMapAtlasItem],
        current_product_count: int,
        current_product_latest_at: datetime | None,
        current_source_snapshot_sha256: str | None,
    ) -> ThematicMapAtlasResponse:
        """组装专题图集当前性、成员和下载响应。

        Args:
            atlas: 图集主记录。
            items: 图集成员快照。
            current_product_count: 当前有效 PNG 专题图数量。
            current_product_latest_at: 当前最近成图时间。
            current_source_snapshot_sha256: 当前来源摘要。

        Returns:
            ThematicMapAtlasResponse: 前端图集响应。
        """
        stale_reason = self._stale_reason(
            atlas,
            current_product_count,
            current_product_latest_at,
            current_source_snapshot_sha256,
        )
        if stale_reason is None:
            try:
                self.verify_atlas_package(atlas, items)
            except ValidationException as exc:
                stale_reason = exc.message
        is_current = stale_reason is None
        return ThematicMapAtlasResponse(
            atlas_code=atlas.atlas_code,
            atlas_name=atlas.atlas_name,
            atlas_number=atlas.atlas_number,
            version=atlas.version,
            status=atlas.status if is_current else (
                "superseded" if atlas.status == "superseded" else "invalid"
            ),
            package_size_bytes=atlas.package_size_bytes,
            package_checksum_sha256=atlas.package_checksum_sha256,
            pdf_filename=atlas.pdf_filename,
            pdf_size_bytes=atlas.pdf_size_bytes,
            pdf_checksum_sha256=atlas.pdf_checksum_sha256,
            pdf_page_count=atlas.pdf_page_count,
            member_count=atlas.member_count,
            product_count_snapshot=atlas.product_count_snapshot,
            product_latest_at_snapshot=atlas.product_latest_at_snapshot,
            source_snapshot_sha256=atlas.source_snapshot_sha256,
            atlas_manifest=atlas.atlas_manifest,
            generated_by=atlas.generated_by,
            generated_by_code=atlas.generated_by_code,
            generated_by_role=atlas.generated_by_role,
            generated_at=atlas.generated_at,
            superseded_at=atlas.superseded_at,
            members=[
                ThematicMapAtlasItemResponse(
                    sequence=item.sequence,
                    product_code=item.product_code,
                    map_name=item.map_name,
                    map_number=item.map_number,
                    map_date=item.map_date,
                    product_size_bytes=item.product_size_bytes,
                    product_checksum_sha256=item.product_checksum_sha256,
                    member_path=item.member_path,
                )
                for item in items
            ],
            is_current=is_current,
            stale_reason=stale_reason,
            download_url=(
                f"/api/v1/thematic-maps/atlases/{atlas.atlas_code}/download"
                if is_current
                else None
            ),
        )

    async def _current_source_state(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[list[ThematicMapProduct], str | None, datetime | None]:
        """加载并复核任务当前全部 PNG 专题图来源。

        Args:
            db: 异步数据库会话。
            task_id: 任务主键。

        Returns:
            tuple: 有效产品、来源摘要和最近时间。
        """
        products = await self.dao.list_atlas_eligible_products(db, task_id)
        valid_products: list[ThematicMapProduct] = []
        for product in products:
            try:
                self.verify_product_file(product)
            except ValidationException:
                continue
            valid_products.append(product)
        if not valid_products:
            return [], None, None
        digest, latest_at = self._source_snapshot(valid_products)
        return valid_products, digest, latest_at

    async def build_overview(
        self,
        db: AsyncSession,
        task_id: int,
    ) -> tuple[int, list[ThematicMapAtlasResponse]]:
        """构建专题制图总览所需的图集当前态和历史。

        Args:
            db: 异步数据库会话。
            task_id: 作业任务主键。

        Returns:
            tuple[int, list[ThematicMapAtlasResponse]]: 有效页数和图集版本。
        """
        valid_products, digest, latest_at = await self._current_source_state(
            db,
            task_id,
        )
        atlases = await self.dao.list_atlases(db, task_id)
        atlas_items = await self.dao.list_atlas_items(
            db,
            [atlas.id for atlas in atlases],
        )
        items_by_atlas: dict[int, list[ThematicMapAtlasItem]] = {}
        for item in atlas_items:
            items_by_atlas.setdefault(item.atlas_id, []).append(item)
        return len(valid_products), [
            self._response(
                atlas,
                items_by_atlas.get(atlas.id, []),
                len(valid_products),
                latest_at,
                digest,
            )
            for atlas in atlases
        ]

    async def generate(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        request: ThematicMapAtlasGenerateRequest,
    ) -> ThematicMapAtlasGenerateResponse:
        """把任务当前全部有效 PNG 专题图原子编排为图集。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            request: 图集名称、编号、成员顺序和审计说明。

        Returns:
            ThematicMapAtlasGenerateResponse: 当前图集实体和成员证据。
        """
        project, task = await self._project_task(db, project_code, task_code)
        operator = await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "generate_thematic_maps",
        )
        eligible_products = await self.dao.list_atlas_eligible_products(
            db,
            task.id,
        )
        if len(eligible_products) < 2:
            raise ValidationException("至少需要 2 张有效 PNG 专题图才能编排图集")
        if len(eligible_products) > 50:
            raise ValidationException(
                "当前任务有效 PNG 专题图超过 50 张，需先按业务范围分册"
            )
        product_by_code = {
            product.product_code: product for product in eligible_products
        }
        requested_codes = set(request.product_codes)
        eligible_codes = set(product_by_code)
        if requested_codes != eligible_codes:
            missing = sorted(eligible_codes - requested_codes)
            unknown = sorted(requested_codes - eligible_codes)
            details: list[str] = []
            if missing:
                details.append("缺少 " + "、".join(missing[:5]))
            if unknown:
                details.append("无效 " + "、".join(unknown[:5]))
            raise ValidationException(
                "图集必须覆盖任务当前全部有效 PNG 专题图；" + "；".join(details)
            )
        ordered_products = [
            product_by_code[product_code]
            for product_code in request.product_codes
        ]
        member_contents: list[bytes] = []
        atlas_sources: list[ThematicMapAtlasSource] = []
        total_source_bytes = 0
        for product in ordered_products:
            path = await asyncio.to_thread(self.verify_product_file, product)
            content = await asyncio.to_thread(path.read_bytes)
            total_source_bytes += len(content)
            if total_source_bytes > 250 * 1024 * 1024:
                raise ValidationException("图集原始专题图总大小不得超过 250MB")
            member_contents.append(content)
            atlas_sources.append(
                ThematicMapAtlasSource(
                    product_code=product.product_code,
                    map_name=product.map_name,
                    map_number=product.map_number,
                    map_date=product.map_date,
                    path=path,
                    file_size_bytes=product.file_size_bytes,
                    checksum_sha256=product.checksum_sha256,
                )
            )
        source_snapshot_sha256, product_latest_at = self._source_snapshot(
            eligible_products
        )
        version = await self.dao.get_next_atlas_version(db, task.id)
        generated_at = datetime.now(UTC)
        atlas_code = (
            f"TMA-{generated_at:%Y%m%d%H%M%S}-"
            f"{uuid4().hex[:12].upper()}"
        )
        producers = {
            str(product.render_manifest.get("producer") or "").strip()
            for product in ordered_products
        }
        producers.discard("")
        producer = (
            next(iter(producers))
            if len(producers) == 1
            else "多版式专题图编制单位详见成员清单"
        )
        render_result = await asyncio.to_thread(
            self.renderer.render,
            request.atlas_name,
            request.atlas_number,
            task_code,
            producer,
            generated_at,
            atlas_sources,
        )
        pdf_filename = f"{request.atlas_number}_v{version}.pdf"
        pdf_size = len(render_result.pdf_content)
        pdf_checksum = hashlib.sha256(render_result.pdf_content).hexdigest()
        member_manifest: list[dict] = []
        for sequence, product in enumerate(ordered_products, start=1):
            member_path = f"members/{sequence:03d}_{product.product_code}.png"
            lineage = product.render_manifest.get("source_asset_lineage") or {}
            member_manifest.append({
                "sequence": sequence,
                "product_code": product.product_code,
                "map_name": product.map_name,
                "map_number": product.map_number,
                "map_date": product.map_date.isoformat(),
                "member_path": member_path,
                "file_size_bytes": product.file_size_bytes,
                "checksum_sha256": product.checksum_sha256,
                "source_uri": product.source_uri,
                "source_checksum_sha256": product.source_checksum_sha256,
                "source_asset_code": lineage.get("asset_code"),
                "source_acquired_at": lineage.get("acquired_at"),
                "security_classification": product.render_manifest.get(
                    "security_classification"
                ),
            })
        atlas_manifest = {
            "schema_version": "thematic-map-atlas-v1",
            "atlas_code": atlas_code,
            "atlas_name": request.atlas_name,
            "atlas_number": request.atlas_number,
            "version": version,
            "task_code": task_code,
            "generated_at": generated_at.isoformat(),
            "generated_by": operator.display_name,
            "generated_by_code": operator.user_code,
            "generated_by_role": operator.role_code,
            "generation_comment": request.comment,
            "producer": producer,
            "member_count": len(ordered_products),
            "product_count_snapshot": len(eligible_products),
            "product_latest_at_snapshot": product_latest_at.isoformat(),
            "source_snapshot_sha256": source_snapshot_sha256,
            "pdf": {
                "filename": pdf_filename,
                "file_size_bytes": pdf_size,
                "checksum_sha256": pdf_checksum,
                "page_count": render_result.page_count,
            },
            "render": render_result.manifest,
            "members": member_manifest,
        }
        manifest_content = json.dumps(
            atlas_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        package_buffer = BytesIO()
        with ZipFile(
            package_buffer,
            "w",
            ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.writestr(pdf_filename, render_result.pdf_content)
            archive.writestr("manifest.json", manifest_content)
            for item, content in zip(
                member_manifest,
                member_contents,
                strict=True,
            ):
                archive.writestr(item["member_path"], content)
        package_content = package_buffer.getvalue()
        relative_path = (
            Path("atlases") / task_code / f"{atlas_code}.zip"
        ).as_posix()
        final_path = self._resolve_storage_path(relative_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = final_path.with_name(
            f".{final_path.name}.{uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_bytes(package_content)
            os.replace(temporary_path, final_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        atlas = ThematicMapAtlas(
            task_id=task.id,
            atlas_code=atlas_code,
            atlas_name=request.atlas_name,
            atlas_number=request.atlas_number,
            version=version,
            status="completed",
            package_uri=f"storage://thematic_maps/{relative_path}",
            package_size_bytes=len(package_content),
            package_checksum_sha256=hashlib.sha256(package_content).hexdigest(),
            pdf_filename=pdf_filename,
            pdf_size_bytes=pdf_size,
            pdf_checksum_sha256=pdf_checksum,
            pdf_page_count=render_result.page_count,
            member_count=len(ordered_products),
            product_count_snapshot=len(eligible_products),
            product_latest_at_snapshot=product_latest_at,
            source_snapshot_sha256=source_snapshot_sha256,
            atlas_manifest=atlas_manifest,
            generated_by=operator.display_name,
            generated_by_code=operator.user_code,
            generated_by_role=operator.role_code,
            generated_at=generated_at,
        )
        try:
            await self.dao.supersede_current_atlases(db, task.id)
            await self.dao.add_atlas(db, atlas)
            items = [
                ThematicMapAtlasItem(
                    atlas_id=atlas.id,
                    product_id=product.id,
                    sequence=manifest["sequence"],
                    product_code=product.product_code,
                    map_name=product.map_name,
                    map_number=product.map_number,
                    map_date=product.map_date,
                    product_size_bytes=product.file_size_bytes,
                    product_checksum_sha256=product.checksum_sha256,
                    member_path=manifest["member_path"],
                )
                for product, manifest in zip(
                    ordered_products,
                    member_manifest,
                    strict=True,
                )
            ]
            await self.dao.add_atlas_items(db, items)
            await self.dao.add_event(
                db,
                ThematicMapEvent(
                    task_id=task.id,
                    entity_type="atlas",
                    entity_code=atlas.atlas_code,
                    action="atlas_generated",
                    event_values={
                        "atlas_number": atlas.atlas_number,
                        "version": atlas.version,
                        "member_count": atlas.member_count,
                        "pdf_page_count": atlas.pdf_page_count,
                        "package_size_bytes": atlas.package_size_bytes,
                        "package_checksum_sha256": atlas.package_checksum_sha256,
                        "pdf_checksum_sha256": atlas.pdf_checksum_sha256,
                        "source_snapshot_sha256": atlas.source_snapshot_sha256,
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
            final_path.unlink(missing_ok=True)
            raise
        return ThematicMapAtlasGenerateResponse(
            atlas=self._response(
                atlas,
                items,
                len(eligible_products),
                product_latest_at,
                source_snapshot_sha256,
            )
        )

    async def get_download(
        self,
        db: AsyncSession,
        atlas_code: str,
        operator_code: str,
    ) -> ThematicMapAtlasDownload:
        """鉴权并复核当前专题图集后返回 ZIP 实体。

        Args:
            db: 异步数据库会话。
            atlas_code: 图集业务编号。
            operator_code: 下载人稳定编码。

        Returns:
            ThematicMapAtlasDownload: 图集 ZIP 内容。
        """
        atlas = await self.dao.get_atlas_by_code(db, atlas_code)
        if atlas is None:
            raise NotFoundException(f"未找到专题图集 {atlas_code}")
        task = await self.workbench_dao.get_task_by_id(db, atlas.task_id)
        if task is None:
            raise NotFoundException("专题图集所属任务不存在")
        operator = await self.project_user_service.require_capability(
            db,
            task.project_id,
            operator_code,
            "download_thematic_maps",
        )
        path = await self.require_current_file(db, atlas)
        await self.dao.add_event(
            db,
            ThematicMapEvent(
                task_id=task.id,
                entity_type="atlas",
                entity_code=atlas.atlas_code,
                action="atlas_downloaded",
                event_values={
                    "version": atlas.version,
                    "member_count": atlas.member_count,
                    "package_size_bytes": atlas.package_size_bytes,
                    "package_checksum_sha256": atlas.package_checksum_sha256,
                },
                comment="下载当前专题图集实体包",
                operator=operator.display_name,
                operator_code=operator.user_code,
                operator_role=operator.role_code,
            ),
        )
        await db.commit()
        return ThematicMapAtlasDownload(
            content=await asyncio.to_thread(path.read_bytes),
            media_type="application/zip",
            filename=f"{atlas.atlas_number}_v{atlas.version}.zip",
        )

    async def require_current_file(
        self,
        db: AsyncSession,
        atlas: ThematicMapAtlas,
    ) -> Path:
        """复核图集仍覆盖当前全部有效专题图并返回实体。

        Args:
            db: 异步数据库会话。
            atlas: 待下载或归档图集。

        Returns:
            Path: 已通过当前性和完整性校验的 ZIP。
        """
        valid_products, digest, latest_at = await self._current_source_state(
            db,
            atlas.task_id,
        )
        stale_reason = self._stale_reason(
            atlas,
            len(valid_products),
            latest_at,
            digest,
        )
        if stale_reason:
            raise ValidationException(f"专题图集已失效：{stale_reason}")
        items = await self.dao.get_atlas_items(db, atlas.id)
        return await asyncio.to_thread(self.verify_atlas_package, atlas, items)
