import request from './request'

import type {
  AreaStatistics,
  AreaStatisticsHistoryImportMetadata,
  AreaStatisticsHistoryImportResult,
  BatchPlotAttributeUpdatePayload,
  BatchPlotAttributeUpdateResult,
  BoundaryProperties,
  BoundingBox,
  DeliveryList,
  DeliveryGeneratePayload,
  DeliveryPackage,
  DisasterPatch,
  DisasterPatchUpdatePayload,
  DisasterGeoJsonImportPayload,
  DisasterGeoJsonImportResult,
  DisasterReport,
  DisasterReportGeneratePayload,
  DisasterReportList,
  DisasterSummary,
  FieldRematchPayload,
  FieldReopenPayload,
  FieldResolutionPayload,
  FieldVerificationBatchImportPayload,
  FieldVerificationBatchImportResult,
  FieldVerificationFileImportMetadata,
  FieldVerificationItem,
  FieldVerificationList,
  GeoJsonFeature,
  GeoJsonFeatureCollection,
  ImageryProcessing,
  ImageryQuicklook,
  ImagerySourceLevelAcceptPayload,
  ImageryArtifactRegisterPayload,
  ImageryStepExecutePayload,
  ImageryAssetCatalog,
  ImageryAssetItem,
  PlotAttributeMutationPayload,
  PlotAttributes,
  PlotCreatePayload,
  PlotDeletePayload,
  PlotGeometryUpdatePayload,
  PlotHistoryActionPayload,
  PlotHistoryActionResult,
  PlotMergePayload,
  PlotMergeResult,
  PlotOperationHistoryState,
  PlotCatalog,
  PlotViewportRequest,
  PlotViewportResponse,
  PlotRollbackPayload,
  PlotSplitPayload,
  PlotSplitResult,
  PlotProperties,
  PlotQualityCheckPayload,
  PlotVersionList,
  QualityCheckResult,
  QualityIssueList,
  QualityIssueQuery,
  QualityIssueResolvePayload,
  QualityIssueResolveResult,
  ProjectUserList,
  ReviewActionPayload,
  ReviewActionResult,
  TaskQualityCheckPayload,
  TaskQualityCheckResult,
  TaskSubmitPayload,
  RuleConfig,
  RuleConfigUpdatePayload,
  TaskSummary,
  WorkbenchOverview,
} from '@/types/workbench'

type JsonRecord = Record<string, unknown>

/**
 * 按 WGS84 坐标点查询所属图斑。
 * @param {{lon: number, lat: number}} point WGS84 坐标。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 图斑属性。
 */
export const queryPlotByPoint = (
  point: { lon: number; lat: number },
  taskCode: string = 'RS-2026-045',
) => request.post<PlotProperties>('/v1/plot/query-point', point, {
  params: { task_code: taskCode },
})

/**
 * 按图斑编号获取完整边界。
 * @param {string} plotCode 图斑编号。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} GeoJSON Feature。
 */
export const getPlotBoundary = (
  plotCode: string,
  taskCode: string = 'RS-2026-045',
) =>
  request.get<GeoJsonFeature<PlotProperties>>('/v1/plot/boundary', {
    params: { plot_code: plotCode, task_code: taskCode },
  })

/**
 * 查询 WGS84 包围盒内的图斑。
 * @param {object} bbox 包围盒参数。
 * @returns {Promise<object>} GeoJSON FeatureCollection。
 */
export const queryPlotsByBBox = (bbox: BoundingBox) =>
  request.post<GeoJsonFeatureCollection<PlotProperties>>('/v1/plot/bbox', bbox)

/**
 * 查询任务内不携带完整几何的轻量地块目录。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 按县区组织的地块目录。
 */
export const getPlotCatalog = (taskCode: string = 'RS-2026-045') =>
  request.get<PlotCatalog>('/v1/plot/catalog', {
    params: { task_code: taskCode },
  })

/**
 * 按任务和当前地图视野加载完整地块几何。
 * @param {object} payload WGS84 视野、任务编号和最大数量。
 * @returns {Promise<object>} 完整视野 GeoJSON 或继续放大提示。
 */
export const queryPlotViewport = (payload: PlotViewportRequest) =>
  request.post<PlotViewportResponse>('/v1/plot/viewport', payload)

/**
 * 处理地图点击坐标查询。
 * @param {number} lon WGS84 经度。
 * @param {number} lat WGS84 纬度。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 图斑属性。
 */
export const clickQuery = (
  lon: number,
  lat: number,
  taskCode: string = 'RS-2026-045',
) => request.get<PlotProperties>('/v1/plot/click', {
  params: { lon, lat, task_code: taskCode },
})

/**
 * 获取当前遥感监测工作台聚合数据。
 * @param {string} projectCode 项目编号。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 项目、任务、影像、统计与审核记录。
 */
export const getWorkbenchOverview = (
  projectCode: string = 'RS-2026',
  taskCode: string = 'RS-2026-045',
) => request.get<WorkbenchOverview>('/v1/workbench/overview', {
  params: { project_code: projectCode, task_code: taskCode },
})

/**
 * 获取解译图斑业务属性。
 * @param {string} plotCode 图斑编号。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 图斑业务属性。
 */
export const getWorkbenchPlot = (
  plotCode: string,
  taskCode: string = 'RS-2026-045',
) => request.get<PlotAttributes>(`/v1/workbench/plots/${plotCode}`, {
  params: { task_code: taskCode },
})

/**
 * 创建人工解译图斑并生成初始版本。
 * @param {object} payload 图斑几何、属性和操作信息。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 新建图斑属性。
 */
export const createWorkbenchPlot = (
  payload: PlotCreatePayload,
  taskCode: string = 'RS-2026-045',
) => request.post<PlotAttributes>('/v1/workbench/plots', payload, {
  params: { task_code: taskCode },
})

/**
 * 保存解译图斑业务属性并生成新版本。
 * @param {string} plotCode 图斑编号。
 * @param {object} attributes 业务属性。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 更新后的图斑属性。
 */
export const updateWorkbenchPlot = (
  plotCode: string,
  attributes: PlotAttributeMutationPayload,
  taskCode: string = 'RS-2026-045',
) => request.patch<PlotAttributes>(`/v1/workbench/plots/${plotCode}`, attributes, {
  params: { task_code: taskCode },
})

/**
 * 对显式选择的任务图斑批量赋值并生成新版本。
 * @param {string} taskCode 任务编号。
 * @param {object} payload 图斑编号、目标属性、操作人和说明。
 * @returns {Promise<object>} 更新数量和任务进度。
 */
export const batchUpdateWorkbenchPlotAttributes = (
  taskCode: string,
  payload: BatchPlotAttributeUpdatePayload,
) => request.post<BatchPlotAttributeUpdateResult>(
  `/v1/workbench/tasks/${taskCode}/plots/batch-attributes`,
  payload,
)

/**
 * 保存节点编辑后的图斑边界。
 * @param {string} plotCode 图斑编号。
 * @param {object} payload 新边界、操作人和说明。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 更新后的图斑属性。
 */
export const updateWorkbenchPlotGeometry = (
  plotCode: string,
  payload: PlotGeometryUpdatePayload,
  taskCode: string = 'RS-2026-045',
) => request.patch<PlotAttributes>(
  `/v1/workbench/plots/${plotCode}/geometry`,
  payload,
  { params: { task_code: taskCode } },
)

/**
 * 软删除图斑并保留版本和审计记录。
 * @param {string} plotCode 图斑编号。
 * @param {object} payload 操作人和删除原因。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 删除状态图斑属性。
 */
export const deleteWorkbenchPlot = (
  plotCode: string,
  payload: PlotDeletePayload,
  taskCode: string = 'RS-2026-045',
) => request.delete<PlotAttributes>(`/v1/workbench/plots/${plotCode}`, {
  data: payload,
  params: { task_code: taskCode },
})

/**
 * 使用 WGS84 分割线拆分任务内图斑。
 * @param {string} taskCode 作业任务编号。
 * @param {string} plotCode 待分割图斑编号。
 * @param {object} payload 分割线、操作人编码和判读依据。
 * @returns {Promise<object>} 两个子图斑和面积守恒结果。
 */
export const splitWorkbenchPlot = (
  taskCode: string,
  plotCode: string,
  payload: PlotSplitPayload,
) => request.post<PlotSplitResult>(
  `/v1/workbench/tasks/${taskCode}/plots/${plotCode}/split`,
  payload,
)

/**
 * 合并显式选择的相邻任务图斑。
 * @param {string} taskCode 作业任务编号。
 * @param {object} payload 图斑编号、确认属性、操作人和依据。
 * @returns {Promise<object>} 合并结果和面积守恒信息。
 */
export const mergeWorkbenchPlots = (
  taskCode: string,
  payload: PlotMergePayload,
) => request.post<PlotMergeResult>(
  `/v1/workbench/tasks/${taskCode}/plots/merge`,
  payload,
)

/** 获取任务当前撤销和重做候选。 */
export const getPlotOperationHistoryState = (
  taskCode: string,
) => request.get<PlotOperationHistoryState>(
  `/v1/workbench/tasks/${taskCode}/plot-operations/history-state`,
)

/** 撤销任务最近一个仍生效的分割或合并操作。 */
export const undoWorkbenchPlotOperation = (
  taskCode: string,
  payload: PlotHistoryActionPayload,
) => request.post<PlotHistoryActionResult>(
  `/v1/workbench/tasks/${taskCode}/plot-operations/undo`,
  payload,
)

/** 重做任务最近一个已撤销且尚未失效的操作。 */
export const redoWorkbenchPlotOperation = (
  taskCode: string,
  payload: PlotHistoryActionPayload,
) => request.post<PlotHistoryActionResult>(
  `/v1/workbench/tasks/${taskCode}/plot-operations/redo`,
  payload,
)

/**
 * 执行图斑质量规则检查。
 * @param {string} plotCode 图斑编号。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 质量得分和逐项规则结果。
 */
export const checkWorkbenchPlotQuality = (
  plotCode: string,
  payload: PlotQualityCheckPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<QualityCheckResult>(`/v1/workbench/plots/${plotCode}/quality-check`, payload, {
  params: { task_code: taskCode },
})

/**
 * 执行任务作用域内全部图斑质量检查。
 * @param {string} taskCode 任务编号。
 * @param {object} payload 操作人和执行说明。
 * @returns {Promise<object>} 覆盖率、通过率和规则汇总。
 */
export const runWorkbenchTaskQualityChecks = (
  taskCode: string,
  payload: TaskQualityCheckPayload,
) => request.post<TaskQualityCheckResult>(
  `/v1/workbench/tasks/${taskCode}/quality-checks/run`,
  payload,
)

/**
 * 分页查询任务质量问题及图斑上下文。
 * @param {string} taskCode 任务编号。
 * @param {object} params 状态、规则、严重度、关键词和分页参数。
 * @returns {Promise<object>} 问题分页和规则汇总。
 */
export const getWorkbenchQualityIssues = (
  taskCode: string,
  params: QualityIssueQuery,
) => request.get<QualityIssueList>(
  `/v1/workbench/tasks/${taskCode}/quality-issues`,
  { params },
)

/**
 * 确认关闭审核人员提出的人工问题。
 * @param {string} taskCode 任务编号。
 * @param {number} issueId 问题主键。
 * @param {object} payload 操作人编码和关闭依据。
 * @returns {Promise<object>} 问题关闭审计结果。
 */
export const resolveWorkbenchQualityIssue = (
  taskCode: string,
  issueId: number,
  payload: QualityIssueResolvePayload,
) => request.patch<QualityIssueResolveResult>(
  `/v1/workbench/tasks/${taskCode}/quality-issues/${issueId}/resolve`,
  payload,
)

/**
 * 提交作业任务至内业自检。
 * @param {string} taskCode 任务编号。
 * @param {object} payload 提交人和备注。
 * @returns {Promise<object>} 更新后的任务摘要。
 */
export const submitWorkbenchTask = (taskCode: string, payload: TaskSubmitPayload) =>
  request.post<TaskSummary>(`/v1/workbench/tasks/${taskCode}/submit`, payload)

/**
 * 获取任务外业核查记录。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 外业核查列表和统计。
 */
export const getFieldVerifications = (taskCode: string = 'RS-2026-045') =>
  request.get<FieldVerificationList>('/v1/field-verifications', {
    params: { task_code: taskCode },
  })

/**
 * 批量导入已解析的外业核查 CSV 记录。
 * @param {object} payload 来源、上传人和外业记录。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 导入批次与自动匹配统计。
 */
export const importFieldVerificationCsv = (
  payload: FieldVerificationBatchImportPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<FieldVerificationBatchImportResult>(
  '/v1/field-verifications/import-csv',
  payload,
  { params: { task_code: taskCode }, timeout: 60_000 },
)

/**
 * 上传并导入外业核查 XLSX 实体文件。
 * @param {File} file 原始 Excel 工作簿。
 * @param {object} metadata 来源、上传人和审计说明。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 导入批次与自动匹配统计。
 */
export const importFieldVerificationXlsx = (
  file: File,
  metadata: FieldVerificationFileImportMetadata,
  taskCode: string = 'RS-2026-045',
) => {
  const formData = new FormData()
  formData.append('file', file)
  Object.entries(metadata).forEach(([key, value]) => formData.append(key, value))
  return request.post<FieldVerificationBatchImportResult>(
    '/v1/field-verifications/import-xlsx',
    formData,
    {
      params: { task_code: taskCode },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60_000,
    },
  )
}

/**
 * 下载外业核查 XLSX 标准模板。
 * @returns {Promise<Blob>} Excel 模板实体文件。
 */
export const downloadFieldVerificationXlsxTemplate = () => request.get<Blob>(
  '/v1/field-verifications/import-template.xlsx',
  { responseType: 'blob', timeout: 60_000 },
)

/**
 * 按当前偏差阈值重新匹配外业记录。
 * @param {object} payload 当前操作人稳定编码。
 * @param {string} taskCode 任务编号。
 * @returns {Promise<object>} 批量匹配结果。
 */
export const rematchFieldVerifications = (
  payload: FieldRematchPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<JsonRecord>('/v1/field-verifications/rematch', payload, {
    params: { task_code: taskCode },
  })

/**
 * 人工处置外业疑点。
 * @param {string} verificationCode 外业记录编号。
 * @param {object} payload 决策、审核人和说明。
 * @returns {Promise<object>} 处置后的外业记录。
 */
export const resolveFieldVerification = (
  verificationCode: string,
  payload: FieldResolutionPayload,
) => request.patch<FieldVerificationItem>(
  `/v1/field-verifications/${verificationCode}/resolve`,
  payload,
)

/**
 * 重新打开已处置外业疑点并回退任务门禁。
 * @param {string} verificationCode 外业记录编号。
 * @param {object} payload 操作人稳定编码和重开依据。
 * @returns {Promise<object>} 恢复待处置状态的外业记录。
 */
export const reopenFieldVerification = (
  verificationCode: string,
  payload: FieldReopenPayload,
) => request.patch<FieldVerificationItem>(
  `/v1/field-verifications/${verificationCode}/reopen`,
  payload,
)

/**
 * 执行任务三级审核动作。
 * @param {string} taskCode 作业任务编号。
 * @param {object} payload 审核动作、审核人、意见和问题类型。
 * @returns {Promise<object>} 审核状态流转结果。
 */
export const executeReviewAction = (
  taskCode: string,
  payload: ReviewActionPayload,
) => request.post<ReviewActionResult>(
  `/v1/reviews/tasks/${taskCode}/actions`,
  payload,
)

/**
 * 查询图斑当前版本和历史版本。
 * @param {string} plotCode 图斑编号。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 当前版本号和版本列表。
 */
export const getPlotVersions = (
  plotCode: string,
  taskCode: string = 'RS-2026-045',
) => request.get<PlotVersionList>(`/v1/reviews/plots/${plotCode}/versions`, {
  params: { task_code: taskCode },
})

/**
 * 将图斑恢复到指定历史版本并生成新版本。
 * @param {string} plotCode 图斑编号。
 * @param {object} payload 目标版本、操作人和说明。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 回退后的图斑属性。
 */
export const rollbackPlotVersion = (
  plotCode: string,
  payload: PlotRollbackPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<PlotAttributes>(`/v1/reviews/plots/${plotCode}/rollback`, payload, {
  params: { task_code: taskCode },
})

/**
 * 查询项目启用成员、业务角色与能力。
 * @param {string} projectCode 项目编号。
 * @returns {Promise<object>} 项目用户目录。
 */
export const getProjectUsers = (projectCode: string = 'RS-2026') =>
  request.get<ProjectUserList>('/v1/project-users', {
    params: { project_code: projectCode },
  })

/**
 * 获取任务多维面积统计和年度变化趋势。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 总量、地类、作物、村级和年度统计。
 */
export const getAreaStatistics = (taskCode: string = 'RS-2026-045') =>
  request.get<AreaStatistics>('/v1/statistics/area-summary', {
    params: { task_code: taskCode },
  })

/**
 * 上传真实历史年度面积统计 CSV。
 * @param {File} file 原始 UTF-8 CSV 文件。
 * @param {object} metadata 来源、冲突策略和项目负责人审计。
 * @param {string} taskCode 当前作业任务编号。
 * @returns {Promise<object>} 导入批次与年度结果。
 */
export const importAreaStatisticsHistoryCsv = (
  file: File,
  metadata: AreaStatisticsHistoryImportMetadata,
  taskCode: string = 'RS-2026-045',
) => {
  const formData = new FormData()
  formData.append('file', file)
  Object.entries(metadata).forEach(([key, value]) => formData.append(key, value))
  return request.post<AreaStatisticsHistoryImportResult>(
    '/v1/statistics/annual-snapshots/import-csv',
    formData,
    {
      params: { task_code: taskCode },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60_000,
    },
  )
}

/**
 * 下载历史年度面积统计 CSV 模板。
 * @returns {Promise<Blob>} UTF-8 BOM CSV 模板。
 */
export const downloadAreaStatisticsHistoryTemplate = () => request.get<Blob>(
  '/v1/statistics/annual-snapshots/import-template.csv',
  { responseType: 'blob', timeout: 60_000 },
)

/**
 * 下载任务作用域多维面积统计 CSV。
 * @param {string} operatorCode 导出人稳定用户编码。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<Blob>} UTF-8 BOM CSV 文件。
 */
export const exportAreaStatisticsCsv = (
  operatorCode: string,
  taskCode: string = 'RS-2026-045',
) => request.get<Blob>('/v1/statistics/area-summary/export.csv', {
  params: { task_code: taskCode, operator_code: operatorCode },
  responseType: 'blob',
  timeout: 60_000,
})

/**
 * 获取任务灾害斑块、受灾面积和专题图层。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 灾害评估汇总。
 */
export const getDisasterSummary = (taskCode: string = 'RS-2026-045') =>
  request.get<DisasterSummary>('/v1/disasters/summary', {
    params: { task_code: taskCode },
  })

/**
 * 导入外部灾害模型 GeoJSON FeatureCollection。
 * @param {object} payload 来源、冲突策略、用户编码和灾害斑块。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 导入批次和新增/替换统计。
 */
export const importDisasterGeoJson = (
  payload: DisasterGeoJsonImportPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<DisasterGeoJsonImportResult>(
  '/v1/disasters/import-geojson',
  payload,
  { params: { task_code: taskCode }, timeout: 60_000 },
)

/**
 * 人工修正灾害斑块等级和确认状态。
 * @param {string} patchCode 灾害斑块编号。
 * @param {object} payload 等级、状态、审核人和意见。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 修正后的灾害斑块。
 */
export const updateDisasterPatch = (
  patchCode: string,
  payload: DisasterPatchUpdatePayload,
  taskCode: string = 'RS-2026-045',
) => request.patch<DisasterPatch>(`/v1/disasters/${patchCode}`, payload, {
  params: { task_code: taskCode },
})

/**
 * 查询任务灾害监测专题报告及实体状态。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 当前和历史专题报告列表。
 */
export const getDisasterReports = (taskCode: string = 'RS-2026-045') =>
  request.get<DisasterReportList>('/v1/disasters/reports', {
    params: { task_code: taskCode },
  })

/**
 * 通过全部斑块复核门禁后生成 XLSX 灾害专题报告。
 * @param {object} payload 报告标题、操作人和生成依据。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 新生成报告实体摘要。
 */
export const generateDisasterReport = (
  payload: DisasterReportGeneratePayload,
  taskCode: string = 'RS-2026-045',
) => request.post<DisasterReport>('/v1/disasters/reports', payload, {
  params: { task_code: taskCode },
  timeout: 120_000,
})

/**
 * 下载并触发灾害专题报告实体复核与稳定用户审计。
 * @param {string} reportCode 报告编号。
 * @param {string} requesterCode 下载人稳定用户编码。
 * @returns {Promise<Blob>} 已验证 XLSX 实体。
 */
export const downloadDisasterReport = (
  reportCode: string,
  requesterCode: string,
) => request.get<Blob>(`/v1/disasters/reports/${reportCode}/download`, {
  params: { requester_code: requesterCode },
  responseType: 'blob',
  timeout: 120_000,
})

/**
 * 获取影像元数据和预处理流水线状态。
 * @param {string} assetCode 影像资产编号。
 * @returns {Promise<object>} 影像处理进度和步骤列表。
 */
export const getImageryProcessing = (assetCode: string) => request.get<ImageryProcessing>(
  `/v1/imagery-assets/${assetCode}/processing`,
)

/**
 * 从实体源影像和已校验波段产物获取真实快视图。
 * @param {string} assetCode 影像资产编号。
 * @returns {Promise<object>} 快视图 URL、波段、范围和校验值。
 */
export const getImageryQuicklooks = (assetCode: string) => request.get<ImageryQuicklook>(
  `/v1/imagery-assets/${assetCode}/quicklooks`,
)

/**
 * 查询项目影像资产目录和实体文件状态。
 * @param {string} projectCode 项目编号。
 * @returns {Promise<object>} 真实影像资产目录。
 */
export const getImageryAssets = (projectCode: string = 'RS-2026') =>
  request.get<ImageryAssetCatalog>('/v1/imagery-assets', {
    params: { project_code: projectCode },
  })

/**
 * 上传 GeoTIFF、IMG 或 HDF，并由后端读取栅格元数据。
 * @param {FormData} formData 文件和业务元数据。
 * @param {string} projectCode 项目编号。
 * @param {string} taskCode 审计所属任务编号。
 * @param {(progress: number) => void} onProgress 上传进度回调。
 * @returns {Promise<object>} 已入库影像资产。
 */
export const uploadImageryAsset = (
  formData: FormData,
  projectCode: string = 'RS-2026',
  taskCode: string = 'RS-2026-045',
  onProgress?: (progress: number) => void,
) => request.post<ImageryAssetItem>('/v1/imagery-assets', formData, {
  params: { project_code: projectCode, task_code: taskCode },
  headers: { 'Content-Type': 'multipart/form-data' },
  timeout: 10 * 60 * 1000,
  onUploadProgress: (event) => {
    if (!onProgress || !event.total) return
    onProgress(Math.round((event.loaded / event.total) * 100))
  },
})

/**
 * 校验并登记指定影像预处理步骤的实体产物。
 * @param {string} assetCode 影像资产编号。
 * @param {string} stepCode 处理步骤编号。
 * @param {object} payload 产物相对路径、处理器、操作人和说明。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 更新后的处理流水线。
 */
export const runImageryProcessingStep = (
  assetCode: string,
  stepCode: string,
  payload: ImageryArtifactRegisterPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<ImageryProcessing>(
  `/v1/imagery-assets/${assetCode}/processing/${stepCode}/run`,
  payload,
  { params: { task_code: taskCode } },
)

/**
 * 使用平台内置 Rasterio 处理器执行影像步骤。
 * @param {string} assetCode 影像资产编号。
 * @param {string} stepCode 处理步骤编号。
 * @param {object} payload 项目用户编码、处理参数和说明。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 更新后的处理流水线。
 */
export const executeImageryProcessingStep = (
  assetCode: string,
  stepCode: string,
  payload: ImageryStepExecutePayload,
  taskCode: string = 'RS-2026-045',
) => request.post<ImageryProcessing>(
  `/v1/imagery-assets/${assetCode}/processing/${stepCode}/execute`,
  payload,
  { params: { task_code: taskCode }, timeout: 10 * 60 * 1000 },
)

/**
 * 使用实体 L2A 源产品级别证据满足定标或大气校正步骤。
 * @param {string} assetCode 影像资产编号。
 * @param {string} stepCode 辐射定标或大气校正步骤编码。
 * @param {object} payload 稳定用户、产品级别、无算法确认和承认依据。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 更新后的影像处理流水线。
 */
export const acceptImagerySourceLevelStep = (
  assetCode: string,
  stepCode: string,
  payload: ImagerySourceLevelAcceptPayload,
  taskCode: string = 'RS-2026-045',
) => request.post<ImageryProcessing>(
  `/v1/imagery-assets/${assetCode}/processing/${stepCode}/accept-source`,
  payload,
  { params: { task_code: taskCode } },
)

/**
 * 查询任务成果包和当前生成条件。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 成果包列表和生成门禁。
 */
export const getDeliveryPackages = (taskCode: string = 'RS-2026-045') =>
  request.get<DeliveryList>('/v1/deliveries', {
    params: { task_code: taskCode },
  })

/**
 * 生成完整成果 ZIP 交付包。
 * @param {object} payload 操作人和成果包名称。
 * @param {string} taskCode 作业任务编号。
 * @returns {Promise<object>} 已生成成果包。
 */
export const generateDeliveryPackage = (
  payload: DeliveryGeneratePayload,
  taskCode: string = 'RS-2026-045',
) => request.post<DeliveryPackage>('/v1/deliveries/generate', payload, {
  params: { task_code: taskCode },
})

/**
 * 获取项目行政区划边界 GeoJSON。
 * @param {string} projectCode 项目编号。
 * @returns {Promise<object>} 行政区划边界 FeatureCollection。
 */
export const getAdministrativeBoundaries = (projectCode: string = 'RS-2026') =>
  request.get<GeoJsonFeatureCollection<BoundaryProperties>>('/v1/boundaries', {
    params: { project_code: projectCode },
  })

/**
 * 查询项目当前生效的质量和外业校核规则。
 * @param {string} projectCode 项目编号。
 * @returns {Promise<object>} 当前生效规则和更新信息。
 */
export const getRuleConfig = (projectCode: string = 'RS-2026') =>
  request.get<RuleConfig>('/v1/rule-configs', {
    params: { project_code: projectCode },
  })

/**
 * 更新项目规则并由后端保存修改审计。
 * @param {object} payload 阈值和操作人。
 * @param {string} projectCode 项目编号。
 * @returns {Promise<object>} 更新后的当前规则。
 */
export const updateRuleConfig = (
  payload: RuleConfigUpdatePayload,
  projectCode: string = 'RS-2026',
) => request.patch<RuleConfig>('/v1/rule-configs', payload, {
  params: { project_code: projectCode },
})
