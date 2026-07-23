import request from '@/api/request'
import type {
  PublicImageryBatchImportRequest,
  PublicImageryBatchImportResponse,
  PublicImageryImportRequest,
  PublicImageryImportResponse,
  PublicImagerySearchRequest,
  PublicImagerySearchResponse,
} from '@/types/publicImagery'

/** 从服务端固定 Planetary Computer collection 检索 Landsat 历史候选。 */
export const searchPublicImagery = (
  payload: PublicImagerySearchRequest,
) => request.post<PublicImagerySearchResponse>(
  '/v1/public-imagery/search',
  payload,
  { timeout: 45_000 },
)

/** 服务端重取 STAC Item、申请临时 SAS、裁取实体并原子入库。 */
export const importPublicImagery = (
  payload: PublicImageryImportRequest,
) => request.post<PublicImageryImportResponse>(
  '/v1/public-imagery/import',
  payload,
  { timeout: 20 * 60 * 1000 },
)

/** 服务端裁取全部公开条目后，通过一次影像批次事务整批入库。 */
export const importPublicImageryBatch = (
  payload: PublicImageryBatchImportRequest,
) => request.post<PublicImageryBatchImportResponse>(
  '/v1/public-imagery/import-batch',
  payload,
  { timeout: 40 * 60 * 1000 },
)
