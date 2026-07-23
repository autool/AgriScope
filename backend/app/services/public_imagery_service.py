"""公开 Landsat 历史语料检索、实体裁取与影像资产入库服务。"""

import asyncio
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException, ValidationException
from app.dao.workbench_dao import WorkbenchDAO
from app.schemas.imagery import ImageryAssetCreateRequest
from app.schemas.public_imagery import (
    PublicImageryCandidateResponse,
    PublicImageryImportRequest,
    PublicImageryImportResponse,
    PublicImagerySearchRequest,
    PublicImagerySearchResponse,
)
from app.services.imagery_asset_service import ImageryAssetService
from app.services.project_user_service import ProjectUserService
from app.services.public_imagery_client import PublicImageryClient
from app.services.public_imagery_engine import (
    PublicImageryEngine,
    PublicLandsatItem,
)


class PublicImageryService:
    """编排固定公开 STAC 搜索、服务端 SAS 读取和原子影像入库。"""

    def __init__(
        self,
        client: PublicImageryClient | None = None,
        engine: PublicImageryEngine | None = None,
        asset_service: ImageryAssetService | None = None,
        workbench_dao: WorkbenchDAO | None = None,
        project_user_service: ProjectUserService | None = None,
    ) -> None:
        """初始化公开历史影像服务。

        Args:
            client: 固定 Planetary Computer 客户端。
            engine: Landsat 反射率裁取引擎。
            asset_service: 统一影像实体原子入库服务。
            workbench_dao: 项目任务 DAO。
            project_user_service: 稳定用户能力服务。

        Returns:
            None: 无返回值。
        """
        self.client = client or PublicImageryClient()
        self.engine = engine or PublicImageryEngine()
        self.asset_service = asset_service or ImageryAssetService()
        self.workbench_dao = workbench_dao or WorkbenchDAO()
        self.project_user_service = project_user_service or ProjectUserService()

    async def search(
        self,
        request: PublicImagerySearchRequest,
    ) -> PublicImagerySearchResponse:
        """检索并筛选具备四个反射率波段的真实 Landsat 候选。

        Args:
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
        parsed_items.sort(
            key=lambda item: (
                self.engine.fully_covers(item.bbox, request.bbox),
                -(item.cloud_cover if item.cloud_cover is not None else 101),
                item.acquired_at,
            ),
            reverse=True,
        )
        candidates = [
            self._candidate_response(item, request.bbox)
            for item in parsed_items[:20]
        ]
        return PublicImagerySearchResponse(
            provider=self.engine.PROVIDER,
            collection=self.client.COLLECTION,
            license_name=self.engine.LICENSE_NAME,
            license_url=self.engine.LICENSE_URL,
            non_statutory_notice=self.engine.NON_STATUTORY_NOTICE,
            query_bbox=request.bbox,
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
        project = await self.workbench_dao.get_project_by_code(
            db,
            request.project_code,
        )
        task = await self.workbench_dao.get_task_by_code(db, request.task_code)
        if project is None:
            raise NotFoundException(f"未找到项目 {request.project_code}")
        if task is None or task.project_id != project.id:
            raise ValidationException("作业任务不属于当前项目")
        await self.project_user_service.require_capability(
            db,
            project.id,
            request.operator_code,
            "manage_imagery",
        )

        feature = await asyncio.to_thread(self.client.get_item, request.item_id)
        item = self.engine.parse_item(feature)
        if item.item_id != request.item_id:
            raise ValidationException("公开 STAC 返回的 Item ID 与请求不一致")
        if not self.engine.fully_covers(item.bbox, request.bbox):
            raise ValidationException("选中 Landsat 条目未完整覆盖目标 WGS84 范围")

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
                request.bbox,
                signed_urls,
                temporary_path,
            )
            with temporary_path.open("rb") as file_handle:
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
                    temporary_path.name,
                    file_handle,
                )
        finally:
            temporary_path.unlink(missing_ok=True)
        return PublicImageryImportResponse(
            provider=self.engine.PROVIDER,
            collection=self.client.COLLECTION,
            item_id=item.item_id,
            source_product_id=item.product_id,
            source_acquired_at=item.acquired_at,
            source_cloud_cover=item.cloud_cover,
            source_wrs_path=item.wrs_path,
            source_wrs_row=item.wrs_row,
            license_name=self.engine.LICENSE_NAME,
            non_statutory_notice=self.engine.NON_STATUTORY_NOTICE,
            asset=asset,
        )

    @classmethod
    def _candidate_response(
        cls,
        item: PublicLandsatItem,
        query_bbox: tuple[float, float, float, float],
    ) -> PublicImageryCandidateResponse:
        """组装不含临时 SAS 的公开影像候选响应。

        Args:
            item: 已校验 Landsat 条目。
            query_bbox: 本次检索 WGS84 范围。

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
            fully_covers_query=PublicImageryEngine.fully_covers(
                item.bbox,
                query_bbox,
            ),
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
