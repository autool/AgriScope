import type { DatasetAssetType } from '@/types/production'

export const datasetAssetTypeOptions = [
  ['imagery', '卫星/航空影像'],
  ['vector', '矢量数据'],
  ['table', '表格数据'],
  ['dem', 'DEM 高程'],
  ['control', '控制资料'],
  ['weather', '气象数据'],
  ['management', '管理信息'],
  ['uav', '无人机数据'],
  ['iot', '物联网数据'],
] as const

export const datasetAssetTypeLabels = Object.fromEntries(
  datasetAssetTypeOptions,
) as Record<DatasetAssetType, string>

export const datasetAssetAcceptMap: Record<DatasetAssetType, string> = {
  imagery: '.tif,.tiff,.img,.hdf,.zip',
  vector: '.geojson,.json,.gpkg,.kml,.zip',
  table: '.csv,.xlsx,.zip',
  dem: '.tif,.tiff,.img,.hdf,.zip',
  control: '.csv,.xlsx,.geojson,.json,.pdf,.zip',
  weather: '.csv,.json,.xlsx,.nc,.grb,.grib,.zip',
  management: '.csv,.json,.xlsx,.docx,.pdf,.zip',
  uav: '.tif,.tiff,.img,.jpg,.jpeg,.png,.mp4,.csv,.json,.zip',
  iot: '.csv,.json,.xlsx,.zip',
}
