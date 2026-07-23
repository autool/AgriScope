import request from '@/api/request'
import type {
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
