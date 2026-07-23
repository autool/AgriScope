"""公开 Landsat 历史语料检索、实体裁取与影像资产入库服务。"""

import asyncio
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.public_imagery_dao import (
    PublicImageryCoverageAnalysis,
    PublicImageryDAO,
    PublicImageryItemCoverage,
)
from app.dao.workbench_dao import WorkbenchDAO
from app.schemas.imagery import (
    ImageryAssetBatchCreateRequest,
    ImageryAssetCreateRequest,
)
from app.schemas.public_imagery import (
    PublicImageryBatchImportRequest,
    PublicImageryBatchImportResponse,
    PublicImageryBatchSourceResponse,
    PublicImageryCandidateResponse,
    PublicImageryImportRequest,
    PublicImageryImportResponse,
    PublicImagerySearchRequest,
    PublicImagerySearchResponse,
)
from app.services.imagery_asset_service import (
    ImageryAssetService,
    ImageryBatchUploadFile,
)
from app.services.project_user_service import ProjectUserService
from app.services.public_imagery_client import PublicImageryClient
from app.services.public_imagery_engine import (
    PublicImageryEngine,
    PublicLandsatItem,
)


@dataclass(frozen=True)
class PreparedPublicImagerySubset:
    """一个已由服务端重新获取并裁取完成的公开 Landsat 临时实体。"""

    item: PublicLandsatItem
    output_path: Path
    original_filename: str
    subset_bbox: tuple[float, float, float, float]
    query_coverage_ratio: float


class PublicImageryService:
    """编排固定公开 STAC 搜索、服务端 SAS 读取和原子影像入库。"""

    COVERAGE_BASIS = "STAC_GEOMETRY_POSTGIS_GEOGRAPHY"

    def __init__(
        self,
        client: PublicImageryClient | None = None,
        engine: PublicImageryEngine | None = None,
        asset_service: ImageryAssetService | None = None,
        dao: PublicImageryDAO | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化公开历史影像服务。

        Args:
            client: 固定 Planetary Computer 客户端。
            engine: Landsat 反射率裁取引擎。
            asset_service: 统一影像实体原子入库服务。
            dao: STAC 足迹联合覆盖分析 DAO。
            workbench_dao: 项目任务 DAO。
            project_user_service: 稳定用户能力服务。

        Returns:
            None: 无返回值。
        """
        self.client = client or PublicImageryClient()
        self.engine = engine or PublicImageryEngine()
        self.asset_service = asset_service or ImageryAssetService()
        self.dao = dao or PublicImageryDAO()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()

    async def search(
        self,
        db: AsyncSession,
        request: PublicImagerySearchRequest,
    ) -> PublicImagerySearchResponse:
        """检索并筛选具备四个反射率波段的真实 Landsat 候选。

        Args:
            db: 用于 PostGIS STAC 足迹覆盖分析的异步会话。
            request: 日期、云量和 WGS84 检索窗口。

        Returns:
            PublicImagerySearchResponse: 固定来源说明和最多 20 个候选。
        """
        features = await asyncio.to_thread(
            self.client.search,
            request.bbox,
            request.start_date,
            request.end_date,
            request.max_cloud_cover,
        )
        parsed_items: list[PublicLandsatItem] = []
        for feature in features:
            try:
                parsed_items.append(self.engine.parse_item(feature))
            except ValidationException:
                continue
        coverage = await self._analyze_coverage(db, request.bbox, parsed_items)
        covered_items = [
            (item, item_coverage)
            for item, item_coverage in zip(
                parsed_items,
                coverage.items,
                strict=True,
            )
            if item_coverage.geometry_valid
            and item_coverage.coverage_ratio > 0
        ]
        covered_items.sort(
            key=lambda pair: (
                pair[1].fully_covers_query,
                pair[1].coverage_ratio,
                -(
                    pair[0].cloud_cover
                    if pair[0].cloud_cover is not None
                    else 101
                ),
                pair[0].acquired_at,
            ),
            reverse=True,
        )
        candidates = [
            self._candidate_response(item, item_coverage)
            for item, item_coverage in covered_items[:20]
        ]
        return PublicImagerySearchResponse(
            provider=self.engine.PROVIDER,
            collection=self.client.COLLECTION,
            license_name=self.engine.LICENSE_NAME,
            license_url=self.engine.LICENSE_URL,
            non_statutory_notice=self.engine.NON_STATUTORY_NOTICE,
            query_bbox=request.bbox,
            coverage_basis=self.COVERAGE_BASIS,
            total=len(candidates),
            items=candidates,
        )

    async def import_item(
        self,
        db: AsyncSession,
        request: PublicImageryImportRequest,
    ) -> PublicImageryImportResponse:
        """服务端重取 STAC Item、裁取实体并通过统一批次流程原子入库。

        Args:
            db: 异步数据库会话。
            request: Item ID、WGS84 范围、资产编号和操作人。

        Returns:
            PublicImageryImportResponse: 公开来源和已校验资产结果。
        """
        await self._require_import_scope(
            db,
            request.project_code,
            request.task_code,
            request.operator_code,
        )
        item = await self._fetch_item(request.item_id)
        coverage = await self._analyze_coverage(db, request.bbox, [item])
        self._validate_coverage_geometries(coverage)
        item_coverage = coverage.items[0]
        if not item_coverage.fully_covers_query:
            raise ValidationException(
                "选中 Landsat 条目真实 STAC 足迹未完整覆盖目标范围，"
                "请改用多景联合覆盖批次"
            )
        prepared = await self._prepare_item_subset(
            item,
            request.bbox,
            request.bbox,
            item_coverage=item_coverage,
            union_coverage_ratio=coverage.union_coverage_ratio,
            union_scene_count=1,
        )
        try:
            with prepared.output_path.open("rb") as file_handle:
                asset = await self.asset_service.upload_asset(
                    db,
                    request.project_code,
                    request.task_code,
                    ImageryAssetCreateRequest(
                        asset_code=request.asset_code,
                        asset_name=request.asset_name,
                        sensor_type=None,
                        acquired_at=None,
                        cloud_cover=None,
                        processing_level=None,
                        data_status="operational",
                        operator_code=request.operator_code,
                    ),
                    prepared.original_filename,
                    file_handle,
                )
        finally:
            prepared.output_path.unlink(missing_ok=True)
        return PublicImageryImportResponse(
            provider=self.engine.PROVIDER,
            collection=self.client.COLLECTION,
            item_id=prepared.item.item_id,
            source_product_id=prepared.item.product_id,
            source_acquired_at=prepared.item.acquired_at,
            source_cloud_cover=prepared.item.cloud_cover,
            source_wrs_path=prepared.item.wrs_path,
            source_wrs_row=prepared.item.wrs_row,
            query_coverage_ratio=prepared.query_coverage_ratio,
            coverage_basis=self.COVERAGE_BASIS,
            license_name=self.engine.LICENSE_NAME,
            non_statutory_notice=self.engine.NON_STATUTORY_NOTICE,
            asset=asset,
        )

    async def import_batch(
        self,
        db: AsyncSession,
        request: PublicImageryBatchImportRequest,
    ) -> PublicImageryBatchImportResponse:
        """裁取全部公开条目后复用统一影像批次服务一次原子入库。

        Args:
            db: 异步数据库会话。
            request: 共同 WGS84 范围、1–10 个条目和批次审计信息。

        Returns:
            PublicImageryBatchImportResponse: 来源清单和原子批次结果。
        """
        await self._require_import_scope(
            db,
            request.project_code,
            request.task_code,
            request.operator_code,
        )
        prepared_subsets: list[PreparedPublicImagerySubset] = []
        try:
            items = [
                await self._fetch_item(request_item.item_id)
                for request_item in request.items
            ]
            coverage = await self._analyze_coverage(db, request.bbox, items)
            self._validate_coverage_geometries(coverage)
            if not coverage.union_covers_query:
                raise ValidationException(
                    "所选 Landsat STAC 足迹联合覆盖不足，当前真实覆盖率 "
                    f"{coverage.union_coverage_ratio * 100:.2f}%"
                )
            for item, item_coverage in zip(
                items,
                coverage.items,
                strict=True,
            ):
                if item_coverage.coverage_ratio <= 0:
                    raise ValidationException(
                        f"Landsat 条目 {item.item_id} 未实际覆盖目标范围"
                    )
                subset_bbox = self._intersection_bbox(item.bbox, request.bbox)
                prepared_subsets.append(await self._prepare_item_subset(
                    item,
                    subset_bbox,
                    request.bbox,
                    item_coverage=item_coverage,
                    union_coverage_ratio=coverage.union_coverage_ratio,
                    union_scene_count=len(items),
                ))
            batch_request = ImageryAssetBatchCreateRequest.model_validate({
                "batch_code": request.batch_code,
                "operator_code": request.operator_code,
                "comment": request.comment,
                "items": [
                    {
                        "filename": prepared.original_filename,
                        "asset_code": request_item.asset_code,
                        "asset_name": request_item.asset_name,
                        "sensor_type": None,
                        "acquired_at": None,
                        "cloud_cover": None,
                        "processing_level": None,
                        "data_status": "operational",
                    }
                    for request_item, prepared in zip(
                        request.items,
                        prepared_subsets,
                        strict=True,
                    )
                ],
            })
            with ExitStack() as stack:
                upload_files = [
                    ImageryBatchUploadFile(
                        filename=prepared.original_filename,
                        file_handle=stack.enter_context(
                            prepared.output_path.open("rb")
                        ),
                    )
                    for prepared in prepared_subsets
                ]
                batch = await self.asset_service.upload_assets_batch(
                    db,
                    request.project_code,
                    request.task_code,
                    batch_request,
                    upload_files,
                )
            return PublicImageryBatchImportResponse(
                provider=self.engine.PROVIDER,
                collection=self.client.COLLECTION,
                license_name=self.engine.LICENSE_NAME,
                license_url=self.engine.LICENSE_URL,
                non_statutory_notice=self.engine.NON_STATUTORY_NOTICE,
                query_bbox=request.bbox,
                coverage_basis=self.COVERAGE_BASIS,
                coverage_mode=(
                    "single_scene_complete"
                    if len(prepared_subsets) == 1
                    else "multi_scene_union"
                ),
                union_coverage_ratio=coverage.union_coverage_ratio,
                union_covers_query=coverage.union_covers_query,
                sources=[
                    PublicImageryBatchSourceResponse(
                        item_id=prepared.item.item_id,
                        asset_code=request_item.asset_code,
                        source_product_id=prepared.item.product_id,
                        source_acquired_at=prepared.item.acquired_at,
                        source_cloud_cover=prepared.item.cloud_cover,
                        source_wrs_path=prepared.item.wrs_path,
                        source_wrs_row=prepared.item.wrs_row,
                        subset_bbox=prepared.subset_bbox,
                        query_coverage_ratio=prepared.query_coverage_ratio,
                    )
                    for request_item, prepared in zip(
                        request.items,
                        prepared_subsets,
                        strict=True,
                    )
                ],
                batch=batch,
            )
        finally:
            for prepared in prepared_subsets:
                prepared.output_path.unlink(missing_ok=True)

    async def _require_import_scope(
        self,
        db: AsyncSession,
        project_code: str,
        task_code: str,
        operator_code: str,
    ) -> None:
        """在访问外部影像前校验项目、任务和稳定用户能力。

        Args:
            db: 异步数据库会话。
            project_code: 项目编号。
            task_code: 作业任务编号。
            operator_code: 稳定操作人编码。

        Returns:
            None: 校验通过后无返回值。
        """
        project = await self.workbench_dao.get_project_by_code(db, project_code)
        task = await self.workbench_dao.get_task_by_code(db, task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {project_code}")
        if task is None or task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        await self.project_user_service.require_capability(
            db,
            project.id,
            operator_code,
            "manage_imagery",
        )

    async def _fetch_item(
        self,
        item_id: str,
    ) -> PublicLandsatItem:
        """按稳定 Item ID 从固定 collection 重取并校验 STAC 条目。

        Args:
            item_id: 浏览器仅提交的稳定 STAC Item ID。

        Returns:
            PublicLandsatItem: 已校验且不含临时 SAS 的 STAC 条目。
        """
        feature = await asyncio.to_thread(self.client.get_item, item_id)
        item = self.engine.parse_item(feature)
        if item.item_id != item_id:
            raise ValidationException("公开 STAC 返回的 Item ID 与请求不一致")
        return item

    async def _prepare_item_subset(
        self,
        item: PublicLandsatItem,
        subset_bbox: tuple[float, float, float, float],
        query_bbox: tuple[float, float, float, float],
        *,
        item_coverage: PublicImageryItemCoverage,
        union_coverage_ratio: float,
        union_scene_count: int,
    ) -> PreparedPublicImagerySubset:
        """签名一个已重取条目的四波段并生成交集范围反射率实体。

        Args:
            item: 已从固定 collection 重取并校验的 STAC 条目。
            subset_bbox: 本景 bbox 与共同目标范围的相交裁取矩形。
            query_bbox: 本批次共同目标 WGS84 范围。
            item_coverage: 本景真实 STAC 足迹覆盖分析。
            union_coverage_ratio: 所选全部景的真实联合覆盖比例。
            union_scene_count: 参与联合覆盖校核的景数。

        Returns:
            PreparedPublicImagerySubset: 已完成裁取的临时实体和来源证据。
        """
        signed_pairs = await asyncio.gather(*[
            asyncio.to_thread(
                self.client.sign_asset_url,
                band.unsigned_href,
            )
            for band in item.bands
        ])
        signed_urls = {
            band.asset_name: signed_href
            for band, signed_href in zip(item.bands, signed_pairs, strict=True)
        }
        temporary_path = self._temporary_output_path(item.item_id)
        try:
            await asyncio.to_thread(
                self.engine.build_reflectance_subset,
                item,
                subset_bbox,
                signed_urls,
                temporary_path,
            )
            await asyncio.to_thread(
                self.engine.annotate_coverage_evidence,
                temporary_path,
                query_bbox=query_bbox,
                subset_bbox=subset_bbox,
                item_coverage_ratio=item_coverage.coverage_ratio,
                union_coverage_ratio=union_coverage_ratio,
                union_scene_count=union_scene_count,
            )
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
        return PreparedPublicImagerySubset(
            item=item,
            output_path=temporary_path,
            original_filename=f"{item.item_id}_SR_SUBSET.tif",
            subset_bbox=subset_bbox,
            query_coverage_ratio=item_coverage.coverage_ratio,
        )

    async def _analyze_coverage(
        self,
        db: AsyncSession,
        query_bbox: tuple[float, float, float, float],
        items: list[PublicLandsatItem],
    ) -> PublicImageryCoverageAnalysis:
        """使用 PostGIS 对真实 STAC 足迹执行逐景和联合覆盖分析。

        Args:
            db: 异步数据库会话。
            query_bbox: 共同目标 WGS84 范围。
            items: 已通过 STAC 结构和来源校验的候选。

        Returns:
            PublicImageryCoverageAnalysis: 与候选顺序一致的覆盖结果。
        """
        if not items:
            return PublicImageryCoverageAnalysis(
                items=(),
                union_coverage_ratio=0,
                union_covers_query=False,
            )
        try:
            analysis = await self.dao.analyze_query_coverage(
                db,
                query_bbox,
                [item.geometry for item in items],
            )
        except DBAPIError as exc:
            raise ValidationException("公开 STAC 足迹无法完成空间覆盖校核") from exc
        if len(analysis.items) != len(items):
            raise ValidationException("公开 STAC 足迹覆盖结果数量不完整")
        return analysis

    @staticmethod
    def _validate_coverage_geometries(
        analysis: PublicImageryCoverageAnalysis,
    ) -> None:
        """拒绝拓扑无效的公开 STAC 来源足迹。

        Args:
            analysis: PostGIS 返回的逐景和联合覆盖结果。

        Returns:
            None: 全部来源足迹有效时无返回值。
        """
        invalid_indexes = [
            item.index for item in analysis.items if not item.geometry_valid
        ]
        if invalid_indexes:
            raise ValidationException(
                "公开 STAC 来源足迹拓扑无效，条目序号："
                + ", ".join(str(index + 1) for index in invalid_indexes)
            )

    @staticmethod
    def _intersection_bbox(
        item_bbox: tuple[float, float, float, float],
        query_bbox: tuple[float, float, float, float],
    ) -> tuple[float, float, float, float]:
        """计算单景 bbox 与共同目标范围的非空矩形交集。

        Args:
            item_bbox: 当前 STAC 条目 WGS84 bbox。
            query_bbox: 本批次共同目标 WGS84 bbox。

        Returns:
            tuple[float, float, float, float]: 实际裁取交集。
        """
        intersection = (
            max(item_bbox[0], query_bbox[0]),
            max(item_bbox[1], query_bbox[1]),
            min(item_bbox[2], query_bbox[2]),
            min(item_bbox[3], query_bbox[3]),
        )
        if intersection[0] >= intersection[2] or intersection[1] >= intersection[3]:
            raise ValidationException("选中 Landsat 条目与目标范围没有有效交集")
        return intersection

    @classmethod
    def _candidate_response(
        cls,
        item: PublicLandsatItem,
        coverage: PublicImageryItemCoverage,
    ) -> PublicImageryCandidateResponse:
        """组装不含临时 SAS 的公开影像候选响应。

        Args:
            item: 已校验 Landsat 条目。
            coverage: PostGIS 计算的真实 STAC 足迹覆盖结果。

        Returns:
            PublicImageryCandidateResponse: 前端安全候选信息。
        """
        return PublicImageryCandidateResponse(
            item_id=item.item_id,
            acquired_at=item.acquired_at,
            cloud_cover=item.cloud_cover,
            platform=item.platform,
            instrument=item.instrument,
            processing_level=item.processing_level,
            collection_category=item.collection_category,
            wrs_path=item.wrs_path,
            wrs_row=item.wrs_row,
            resolution_m=item.resolution_m,
            bbox=item.bbox,
            query_coverage_ratio=coverage.coverage_ratio,
            fully_covers_query=coverage.fully_covers_query,
            stac_item_url=item.item_url,
        )

    @staticmethod
    def _temporary_output_path(item_id: str) -> Path:
        """创建不含 SAS 的本地临时 GeoTIFF 路径。

        Args:
            item_id: Landsat STAC Item ID。

        Returns:
            Path: 已关闭且待引擎写入的临时路径。
        """
        safe_item_id = item_id[:120]
        with tempfile.NamedTemporaryFile(
            prefix=f"landsat-{safe_item_id}-",
            suffix=".tif",
            delete=False,
        ) as temporary_file:
            return Path(temporary_file.name)
