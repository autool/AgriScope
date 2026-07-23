import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  batchUpdateWorkbenchPlotAttributes,
  checkWorkbenchPlotQuality,
  clickQuery,
  createWorkbenchPlot,
  deleteWorkbenchPlot,
  getAdministrativeBoundaries,
  getPlotCatalog,
  getPlotBoundary,
  getPlotOperationHistoryState,
  getPlotVersions,
  getWorkbenchTaskQualityRuns,
  getWorkbenchOverview,
  getWorkbenchPlot,
  mergeWorkbenchPlots,
  queryPlotViewport,
  redoWorkbenchPlotOperation,
  runWorkbenchTaskQualityChecks,
  splitWorkbenchPlot,
  submitWorkbenchTask,
  updateWorkbenchPlot,
  updateWorkbenchPlotGeometry,
  undoWorkbenchPlotOperation,
} from '@/api/index'
import { useLayerStore } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import { useUserStore } from '@/store/userStore'
import type {
  BatchPlotAttributeUpdateDraft,
  BatchPlotAttributeUpdateResult,
  BoundingBox,
  GeoJsonFeature,
  LineStringGeometry,
  PlotAttributeUpdate,
  PlotAttributes,
  PlotCreateDraftPayload,
  PlotGeometryUpdatePayload,
  PlotHistoryActionResult,
  PlotMergeDraftPayload,
  PlotMergeResult,
  PlotOperationHistoryState,
  PolygonGeometry,
  PlotProperties,
  PlotSplitResult,
  PlotVersionList,
  QualityCheckResult,
  TaskQualityCheckResult,
  TaskQualityRunList,
  WorkbenchOverview,
} from '@/types/workbench'
import { getGeoJsonFeatureExtent } from '@/utils/geojson'

export const useWorkbenchStore = defineStore('workbench', () => {
  const layerStore = useLayerStore()
  const mapStore = useMapStore()
  const userStore = useUserStore()
  const initializedRef = ref<boolean>(false)
  const loadingRef = ref<boolean>(false)
  const overviewRef = ref<WorkbenchOverview | null>(null)
  const plotAttributesRef = ref<PlotAttributes | null>(null)
  const plotDraftRef = ref<PlotAttributeUpdate | null>(null)
  const plotVersionsRef = ref<PlotVersionList | null>(null)
  const savingPlotRef = ref<boolean>(false)
  const qualityCheckingRef = ref<boolean>(false)
  const qualityResultRef = ref<QualityCheckResult | null>(null)
  const taskQualityCheckingRef = ref<boolean>(false)
  const taskQualityResultRef = ref<TaskQualityCheckResult | null>(null)
  const taskQualityRunsRef = ref<TaskQualityRunList | null>(null)
  const taskQualityRunsLoadingRef = ref<boolean>(false)
  const taskQualityRunsErrorRef = ref<string | null>(null)
  const taskSubmittingRef = ref<boolean>(false)
  const batchUpdatingPlotsRef = ref<boolean>(false)
  const creatingPlotRef = ref<boolean>(false)
  const savingGeometryRef = ref<boolean>(false)
  const deletingPlotRef = ref<boolean>(false)
  const splittingPlotRef = ref<boolean>(false)
  const mergingPlotsRef = ref<boolean>(false)
  const mergeSelectionRef = ref<PlotAttributes[]>([])
  const plotOperationHistoryRef = ref<PlotOperationHistoryState>({
    can_undo: false,
    can_redo: false,
    undo_operation: null,
    redo_operation: null,
  })
  const historyActionLoadingRef = ref<boolean>(false)
  const viewportLoadingRef = ref<boolean>(false)
  const viewportMatchedCountRef = ref<number>(0)
  const viewportRequiresZoomRef = ref<boolean>(false)
  const viewportOverviewModeRef = ref<boolean>(true)
  const lastViewportRef = ref<{ bbox: BoundingBox, zoom: number } | null>(null)
  let viewportRequestId = 0
  const viewportMinimumZoom = 8
  const viewportMaxFeatures = 5000

  const taskCodeComputed = computed<string>(
    () => overviewRef.value?.task.task_code || 'RS-2026-045',
  )
  const projectCodeComputed = computed<string>(
    () => overviewRef.value?.project.project_code || 'RS-2026',
  )
  const selectedPlotCodeComputed = computed<string | null>(
    () => mapStore.selectedPlotRef?.plot_code || null,
  )
  const plotDirtyComputed = computed<boolean>(() => {
    if (!plotAttributesRef.value || !plotDraftRef.value) return false
    return (
      plotAttributesRef.value.land_class !== plotDraftRef.value.land_class
      || plotAttributesRef.value.crop_type !== plotDraftRef.value.crop_type
      || plotAttributesRef.value.planting_mode !== plotDraftRef.value.planting_mode
      || plotAttributesRef.value.irrigation_condition
        !== plotDraftRef.value.irrigation_condition
      || JSON.stringify(plotAttributesRef.value.custom_attributes)
        !== JSON.stringify(plotDraftRef.value.custom_attributes)
    )
  })
  const taskEditableComputed = computed<boolean>(() => (
    overviewRef.value?.task.status === 'interpreting'
  ))
  const canEditPlotsComputed = computed<boolean>(() => (
    taskEditableComputed.value && userStore.hasCapability('edit_plots')
  ))
  const canRunPlotQualityComputed = computed<boolean>(() => (
    taskEditableComputed.value
    && userStore.hasCapability('run_plot_quality_check')
  ))
  const canRunTaskQualityComputed = computed<boolean>(() => (
    taskEditableComputed.value && userStore.hasCapability('run_quality_check')
  ))
  const mergeSelectionCodesComputed = computed<string[]>(() => (
    mergeSelectionRef.value.map((item) => item.plot_code)
  ))

  const requireCurrentUser = (capability: string, errorMessage: string) => {
    const user = userStore.currentUserComputed
    if (!user || !userStore.hasCapability(capability)) {
      throw new Error(errorMessage)
    }
    return user
  }

  /**
   * 根据服务端图斑属性创建可编辑草稿。
   * Args:
   *   attributes: 服务端返回的图斑属性。
   * Returns:
   *   PlotAttributeUpdate: 与接口更新模型一致的草稿。
   */
  const createPlotDraft = (attributes: PlotAttributes): PlotAttributeUpdate => ({
    land_class: attributes.land_class || '',
    crop_type: attributes.crop_type,
    planting_mode: attributes.planting_mode,
    irrigation_condition: attributes.irrigation_condition,
    custom_attributes: { ...attributes.custom_attributes },
  })

  /**
   * 初始化项目概览、图斑和行政区划边界。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 共享工作台数据加载完成后结束。
   */
  const initialize = async (): Promise<void> => {
    if (initializedRef.value || loadingRef.value) return
    loadingRef.value = true
    try {
      const [overviewData, catalog, boundaryData] = await Promise.all([
        getWorkbenchOverview(),
        getPlotCatalog(taskCodeComputed.value),
        getAdministrativeBoundaries(),
      ])
      overviewRef.value = overviewData
      layerStore.setPlotCatalog(catalog)
      layerStore.setFarmlandFeatures({ type: 'FeatureCollection', features: [] })
      layerStore.setBoundaryFeatures(boundaryData)
      const firstPlot = catalog.districts.find(
        (district) => district.plots.length > 0,
      )?.plots[0]
      if (firstPlot) {
        await selectByCode(firstPlot.plot_code)
      }
      await refreshPlotOperationHistory()
      initializedRef.value = true
    } finally {
      loadingRef.value = false
    }
  }

  /**
   * 刷新项目、任务和审核概览。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 项目概览刷新完成后结束。
   */
  const refreshOverview = async (): Promise<void> => {
    overviewRef.value = await getWorkbenchOverview(
      projectCodeComputed.value,
      taskCodeComputed.value,
    )
  }

  /**
   * 刷新任务轻量地块目录。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 地块目录替换完成后结束。
   */
  const refreshPlotCatalog = async (): Promise<void> => {
    layerStore.setPlotCatalog(await getPlotCatalog(taskCodeComputed.value))
  }

  /**
   * 按当前地图视野加载任务图斑；省级尺度不请求完整地块几何。
   * Args:
   *   bbox: WGS84 当前视野包围盒。
   *   zoom: 当前地图缩放级别。
   * Returns:
   *   Promise<void>: 最新有效视野请求应用后结束。
   */
  const loadPlotsForViewport = async (
    bbox: BoundingBox,
    zoom: number,
  ): Promise<void> => {
    lastViewportRef.value = { bbox: { ...bbox }, zoom }
    const requestId = ++viewportRequestId
    if (zoom < viewportMinimumZoom) {
      layerStore.setFarmlandFeatures({ type: 'FeatureCollection', features: [] })
      viewportMatchedCountRef.value = 0
      viewportRequiresZoomRef.value = false
      viewportOverviewModeRef.value = true
      viewportLoadingRef.value = false
      return
    }
    viewportLoadingRef.value = true
    viewportOverviewModeRef.value = false
    try {
      const response = await queryPlotViewport({
        ...bbox,
        task_code: taskCodeComputed.value,
        max_features: viewportMaxFeatures,
      })
      if (requestId !== viewportRequestId) return
      viewportMatchedCountRef.value = response.matched_count
      viewportRequiresZoomRef.value = response.requires_zoom
      layerStore.setFarmlandFeatures(response)
    } finally {
      if (requestId === viewportRequestId) {
        viewportLoadingRef.value = false
      }
    }
  }

  /**
   * 刷新轻量目录，并重新加载最近一次地图视野。
   * Args:
   *   无。
   * Returns:
   *   Promise<void>: 目录和当前视野同步完成后结束。
   */
  const refreshPlots = async (): Promise<void> => {
    await refreshPlotCatalog()
    if (lastViewportRef.value) {
      await loadPlotsForViewport(
        lastViewportRef.value.bbox,
        lastViewportRef.value.zoom,
      )
    }
  }

  const refreshPlotOperationHistory = async (): Promise<void> => {
    plotOperationHistoryRef.value = await getPlotOperationHistoryState(
      taskCodeComputed.value,
    )
  }

  /**
   * 加载选中图斑属性和历史版本。
   * Args:
   *   plotCode: 图斑编号。
   * Returns:
   *   Promise<void>: 图斑详情加载完成后结束。
   */
  const loadSelectedPlot = async (plotCode: string): Promise<void> => {
    const [attributes, versions] = await Promise.all([
      getWorkbenchPlot(plotCode, taskCodeComputed.value),
      getPlotVersions(plotCode, taskCodeComputed.value),
    ])
    plotAttributesRef.value = attributes
    plotDraftRef.value = createPlotDraft(attributes)
    plotVersionsRef.value = versions
    qualityResultRef.value = null
  }

  /**
   * 更新当前图斑属性草稿。
   * Args:
   *   patch: 待更新的一个或多个业务属性。
   * Returns:
   *   void: 无返回值。
   */
  const updatePlotDraft = (patch: Partial<PlotAttributeUpdate>): void => {
    if (!plotDraftRef.value) return
    plotDraftRef.value = { ...plotDraftRef.value, ...patch }
    qualityResultRef.value = null
  }

  /**
   * 放弃未保存修改并恢复服务端属性。
   * Args:
   *   无。
   * Returns:
   *   void: 无返回值。
   */
  const resetPlotDraft = (): void => {
    if (!plotAttributesRef.value) return
    plotDraftRef.value = createPlotDraft(plotAttributesRef.value)
  }

  /**
   * 清空地图选中图斑及右侧编辑上下文。
   * Args:
   *   无。
   * Returns:
   *   void: 无返回值。
   */
  const clearSelectedPlot = (): void => {
    mapStore.clearSelection()
    plotAttributesRef.value = null
    plotDraftRef.value = null
    plotVersionsRef.value = null
    qualityResultRef.value = null
  }

  /**
   * 保存当前图斑属性并刷新版本、任务概览。
   * Args:
   *   无。
   * Returns:
   *   Promise<PlotAttributes>: 保存后的最新图斑属性。
   */
  const saveSelectedPlot = async (): Promise<PlotAttributes> => {
    const plotCode = selectedPlotCodeComputed.value
    const draft = plotDraftRef.value
    if (!plotCode || !draft) throw new Error('请先选择需要编辑的图斑')
    const user = requireCurrentUser('edit_plots', '当前项目身份无权编辑图斑')
    savingPlotRef.value = true
    try {
      const attributes = await updateWorkbenchPlot(
        plotCode,
        {
          ...draft,
          operator_code: user.user_code,
          comment: '更新图斑业务属性',
        },
        taskCodeComputed.value,
      )
      plotAttributesRef.value = attributes
      plotDraftRef.value = createPlotDraft(attributes)
      const [versions] = await Promise.all([
        getPlotVersions(plotCode, taskCodeComputed.value),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      plotVersionsRef.value = versions
      qualityResultRef.value = null
      taskQualityResultRef.value = null
      return attributes
    } finally {
      savingPlotRef.value = false
    }
  }

  /**
   * 创建人工解译图斑并选中新记录。
   * Args:
   *   payload: 几何、属性和操作信息。
   * Returns:
   *   Promise<PlotAttributes>: 新建图斑属性。
   */
  const createPlot = async (
    payload: PlotCreateDraftPayload,
  ): Promise<PlotAttributes> => {
    const user = requireCurrentUser('edit_plots', '当前项目身份无权新建图斑')
    creatingPlotRef.value = true
    try {
      const attributes = await createWorkbenchPlot(
        { ...payload, operator_code: user.user_code },
        taskCodeComputed.value,
      )
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      await selectByCode(attributes.plot_code)
      return attributes
    } finally {
      creatingPlotRef.value = false
    }
  }

  /**
   * 保存当前选中图斑的节点编辑结果。
   * Args:
   *   geometry: WGS84 GeoJSON Polygon。
   *   comment: 编辑说明。
   * Returns:
   *   Promise<PlotAttributes>: 更新后的图斑属性。
   */
  const saveSelectedPlotGeometry = async (
    geometry: PolygonGeometry,
    comment?: string,
  ): Promise<PlotAttributes> => {
    const plotCode = selectedPlotCodeComputed.value
    if (!plotCode) throw new Error('请先选择需要编辑的图斑')
    const user = requireCurrentUser('edit_plots', '当前项目身份无权编辑图斑边界')
    savingGeometryRef.value = true
    const payload: PlotGeometryUpdatePayload = {
      geometry,
      operator_code: user.user_code,
      comment: comment || null,
    }
    try {
      const attributes = await updateWorkbenchPlotGeometry(
        plotCode,
        payload,
        taskCodeComputed.value,
      )
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      await selectByCode(plotCode)
      return attributes
    } finally {
      savingGeometryRef.value = false
    }
  }

  /**
   * 软删除当前选中图斑并清空编辑状态。
   * Args:
   *   comment: 删除原因。
   * Returns:
   *   Promise<PlotAttributes>: 删除状态图斑属性。
   */
  const deleteSelectedPlot = async (
    comment: string,
  ): Promise<PlotAttributes> => {
    const plotCode = selectedPlotCodeComputed.value
    if (!plotCode) throw new Error('请先选择需要删除的图斑')
    const user = requireCurrentUser('edit_plots', '当前项目身份无权删除图斑')
    deletingPlotRef.value = true
    try {
      const attributes = await deleteWorkbenchPlot(
        plotCode,
        { operator_code: user.user_code, comment },
        taskCodeComputed.value,
      )
      clearSelectedPlot()
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      return attributes
    } finally {
      deletingPlotRef.value = false
    }
  }

  /**
   * 使用用户绘制的 WGS84 线分割当前选中图斑。
   * Args:
   *   cutter: 完整穿过源图斑的 GeoJSON LineString。
   *   comment: 影像田埂、权属界或外业证据说明。
   * Returns:
   *   Promise<PlotSplitResult>: 两个子图斑和面积守恒结果。
   */
  const splitSelectedPlot = async (
    cutter: LineStringGeometry,
    comment: string,
  ): Promise<PlotSplitResult> => {
    const plotCode = selectedPlotCodeComputed.value
    if (!plotCode) throw new Error('请先选择需要分割的图斑')
    const user = requireCurrentUser('edit_plots', '当前项目身份无权分割图斑')
    splittingPlotRef.value = true
    try {
      const result = await splitWorkbenchPlot(
        taskCodeComputed.value,
        plotCode,
        {
          cutter,
          operator_code: user.user_code,
          comment,
        },
      )
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      const firstChild = result.result_plots[0]
      if (firstChild) await selectByCode(firstChild.plot_code)
      return result
    } finally {
      splittingPlotRef.value = false
    }
  }

  /**
   * 进入显式地图多选合并模式，并以当前图斑作为第一个来源。
   * Args:
   *   无。
   * Returns:
   *   void: 无返回值。
   */
  const beginMergeSelection = (): void => {
    if (!plotAttributesRef.value) throw new Error('请先选择需要合并的图斑')
    requireCurrentUser('edit_plots', '当前项目身份无权合并图斑')
    mergeSelectionRef.value = [plotAttributesRef.value]
    mapStore.setViewType('2d')
  }

  /**
   * 根据地图点击坐标将一个同县图斑加入合并选择。
   * Args:
   *   coordinate: WGS84 经纬度。
   * Returns:
   *   Promise<PlotAttributes | null>: 新增图斑；重复选择时返回 null。
   */
  const addMergePlotByCoordinate = async (
    coordinate: { lon: number; lat: number },
  ): Promise<PlotAttributes | null> => {
    if (mergeSelectionRef.value.length >= 20) {
      throw new Error('单次最多合并 20 个图斑')
    }
    const plot = await clickQuery(
      coordinate.lon,
      coordinate.lat,
      taskCodeComputed.value,
    )
    if (mergeSelectionCodesComputed.value.includes(plot.plot_code)) return null
    const attributes = await getWorkbenchPlot(
      plot.plot_code,
      taskCodeComputed.value,
    )
    const first = mergeSelectionRef.value[0]
    if (first?.district_code !== attributes.district_code) {
      throw new Error('只能选择同一县区内的图斑进行合并')
    }
    mergeSelectionRef.value = [...mergeSelectionRef.value, attributes]
    return attributes
  }

  const removeMergePlot = (plotCode: string): void => {
    mergeSelectionRef.value = mergeSelectionRef.value.filter(
      (item) => item.plot_code !== plotCode,
    )
  }

  const cancelMergeSelection = (): void => {
    mergeSelectionRef.value = []
  }

  /**
   * 提交显式选择图斑及人工确认的冲突属性。
   * Args:
   *   payload: 合并图斑编号、结果属性和判读依据。
   * Returns:
   *   Promise<PlotMergeResult>: 合并结果和面积守恒信息。
   */
  const mergeSelectedPlots = async (
    payload: PlotMergeDraftPayload,
  ): Promise<PlotMergeResult> => {
    const user = requireCurrentUser('edit_plots', '当前项目身份无权合并图斑')
    const plotCodes = mergeSelectionCodesComputed.value
    if (plotCodes.length < 2) throw new Error('合并至少需要两个图斑')
    mergingPlotsRef.value = true
    try {
      const result = await mergeWorkbenchPlots(
        taskCodeComputed.value,
        {
          ...payload,
          plot_codes: plotCodes,
          operator_code: user.user_code,
        },
      )
      cancelMergeSelection()
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      await selectByCode(result.result_plot.plot_code)
      return result
    } finally {
      mergingPlotsRef.value = false
    }
  }

  const executePlotHistoryAction = async (
    action: 'undo' | 'redo',
    comment: string,
  ): Promise<PlotHistoryActionResult> => {
    const user = requireCurrentUser(
      'edit_plots',
      '当前项目身份无权撤销或重做图斑操作',
    )
    historyActionLoadingRef.value = true
    try {
      const request = action === 'undo'
        ? undoWorkbenchPlotOperation
        : redoWorkbenchPlotOperation
      const result = await request(
        taskCodeComputed.value,
        { operator_code: user.user_code, comment },
      )
      cancelMergeSelection()
      await Promise.all([
        refreshPlots(),
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      taskQualityResultRef.value = null
      const firstActive = result.active_plot_codes[0]
      if (firstActive) {
        await selectByCode(firstActive)
      } else {
        clearSelectedPlot()
      }
      return result
    } finally {
      historyActionLoadingRef.value = false
    }
  }

  const undoLastPlotOperation = (
    comment: string,
  ): Promise<PlotHistoryActionResult> => executePlotHistoryAction('undo', comment)

  const redoLastPlotOperation = (
    comment: string,
  ): Promise<PlotHistoryActionResult> => executePlotHistoryAction('redo', comment)

  /**
   * 对当前选中图斑执行服务端质量规则检查。
   * Args:
   *   无。
   * Returns:
   *   Promise<QualityCheckResult>: 质量得分和逐项规则结果。
   */
  const checkSelectedPlotQuality = async (): Promise<QualityCheckResult> => {
    const plotCode = selectedPlotCodeComputed.value
    if (!plotCode) throw new Error('请先选择需要检查的图斑')
    const user = requireCurrentUser(
      'run_plot_quality_check',
      '当前项目身份无权执行图斑质量检查',
    )
    qualityCheckingRef.value = true
    try {
      const result = await checkWorkbenchPlotQuality(
        plotCode,
        { operator_code: user.user_code },
        taskCodeComputed.value,
      )
      qualityResultRef.value = result
      await Promise.all([refreshOverview(), refreshPlotOperationHistory()])
      return result
    } finally {
      qualityCheckingRef.value = false
    }
  }

  /**
   * 执行任务作用域内全部图斑质量检查。
   * Args:
   *   comment: 可选执行说明。
   * Returns:
   *   Promise<TaskQualityCheckResult>: 任务质量门禁汇总。
   */
  const runTaskQualityChecks = async (
    comment?: string,
  ): Promise<TaskQualityCheckResult> => {
    const user = requireCurrentUser(
      'run_quality_check',
      '当前项目身份无权运行全量质量检查',
    )
    taskQualityCheckingRef.value = true
    try {
      const result = await runWorkbenchTaskQualityChecks(
        taskCodeComputed.value,
        { operator_code: user.user_code, comment: comment || null },
      )
      taskQualityResultRef.value = result
      await Promise.all([refreshOverview(), refreshTaskQualityRunsSafely()])
      return result
    } finally {
      taskQualityCheckingRef.value = false
    }
  }

  /** 读取最近的不可变全量质检批次账本。 */
  const loadTaskQualityRuns = async (limit: number = 10): Promise<void> => {
    taskQualityRunsLoadingRef.value = true
    taskQualityRunsErrorRef.value = null
    try {
      taskQualityRunsRef.value = await getWorkbenchTaskQualityRuns(
        taskCodeComputed.value,
        limit,
      )
    } catch (error) {
      taskQualityRunsErrorRef.value = error instanceof Error
        ? error.message
        : '全量质检批次账本加载失败'
      throw error
    } finally {
      taskQualityRunsLoadingRef.value = false
    }
  }

  /** 刷新辅助账本失败时保留主业务成功结果，并由账本区域显示错误状态。 */
  const refreshTaskQualityRunsSafely = async (): Promise<void> => {
    try {
      await loadTaskQualityRuns()
    } catch {
      // 请求拦截器和 taskQualityRunsErrorRef 已保留可见错误证据。
    }
  }

  /**
   * 将当前任务提交至内业自检节点。
   * Args:
   *   reviewerCode: 提交人稳定编码。
   *   comment: 可选提交说明。
   * Returns:
   *   Promise<void>: 任务状态和概览刷新完成后结束。
   */
  const submitTaskForSelfCheck = async (
    reviewerCode: string,
    comment?: string,
  ): Promise<void> => {
    taskSubmittingRef.value = true
    try {
      await submitWorkbenchTask(
        taskCodeComputed.value,
        { reviewer_code: reviewerCode, comment: comment || null },
      )
      await Promise.all([refreshOverview(), refreshTaskQualityRunsSafely()])
    } finally {
      taskSubmittingRef.value = false
    }
  }

  /**
   * 对显式选择的问题图斑批量赋值并刷新任务状态。
   * Args:
   *   payload: 图斑编号、目标属性和判读说明。
   * Returns:
   *   Promise<BatchPlotAttributeUpdateResult>: 更新数量和任务进度。
   */
  const batchUpdatePlotAttributes = async (
    payload: BatchPlotAttributeUpdateDraft,
  ): Promise<BatchPlotAttributeUpdateResult> => {
    const user = requireCurrentUser('edit_plots', '当前项目身份无权批量修改图斑')
    batchUpdatingPlotsRef.value = true
    try {
      const result = await batchUpdateWorkbenchPlotAttributes(
        taskCodeComputed.value,
        { ...payload, operator_code: user.user_code },
      )
      taskQualityResultRef.value = null
      await Promise.all([
        refreshOverview(),
        refreshPlotOperationHistory(),
        refreshTaskQualityRunsSafely(),
      ])
      const selectedCode = selectedPlotCodeComputed.value
      if (selectedCode && payload.plot_codes.includes(selectedCode)) {
        await loadSelectedPlot(selectedCode)
      }
      return result
    } finally {
      batchUpdatingPlotsRef.value = false
    }
  }

  /**
   * 按地图坐标查询并选中图斑。
   * Args:
   *   coordinate: WGS84 经纬度。
   * Returns:
   *   Promise<void>: 图斑选中状态同步完成后结束。
   */
  const selectByCoordinate = async (
    coordinate: { lon: number; lat: number },
  ): Promise<void> => {
    const plot = await clickQuery(
      coordinate.lon,
      coordinate.lat,
      taskCodeComputed.value,
    )
    const feature = await getPlotBoundary(
      plot.plot_code,
      taskCodeComputed.value,
    )
    mapStore.selectPlot({ ...plot, feature })
    await loadSelectedPlot(plot.plot_code)
  }

  /**
   * 按编号查询并选中图斑。
   * Args:
   *   plotCode: 图斑编号。
   * Returns:
   *   Promise<GeoJsonFeature<PlotProperties>>: 用于地图定位的图斑。
   */
  const selectByCode = async (
    plotCode: string,
  ): Promise<GeoJsonFeature<PlotProperties>> => {
    const feature = await getPlotBoundary(plotCode, taskCodeComputed.value)
    mapStore.selectPlot({ ...feature.properties, feature })
    await loadSelectedPlot(plotCode)
    return feature
  }

  /**
   * 按编号选中并将地图定位到问题图斑。
   * Args:
   *   plotCode: 图斑编号。
   * Returns:
   *   Promise<void>: 图斑详情和地图范围同步完成后结束。
   */
  const focusByCode = async (plotCode: string): Promise<void> => {
    const feature = await selectByCode(plotCode)
    const extent = getGeoJsonFeatureExtent(feature)
    if (extent) mapStore.focusExtent(extent)
  }

  return {
    initializedRef,
    loadingRef,
    overviewRef,
    plotAttributesRef,
    plotDraftRef,
    plotVersionsRef,
    savingPlotRef,
    qualityCheckingRef,
    qualityResultRef,
    taskQualityCheckingRef,
    taskQualityResultRef,
    taskQualityRunsRef,
    taskQualityRunsLoadingRef,
    taskQualityRunsErrorRef,
    taskSubmittingRef,
    batchUpdatingPlotsRef,
    creatingPlotRef,
    savingGeometryRef,
    deletingPlotRef,
    splittingPlotRef,
    mergingPlotsRef,
    mergeSelectionRef,
    plotOperationHistoryRef,
    historyActionLoadingRef,
    viewportLoadingRef,
    viewportMatchedCountRef,
    viewportRequiresZoomRef,
    viewportOverviewModeRef,
    taskCodeComputed,
    projectCodeComputed,
    selectedPlotCodeComputed,
    plotDirtyComputed,
    taskEditableComputed,
    canEditPlotsComputed,
    canRunPlotQualityComputed,
    canRunTaskQualityComputed,
    mergeSelectionCodesComputed,
    initialize,
    refreshOverview,
    refreshPlots,
    refreshPlotOperationHistory,
    loadSelectedPlot,
    updatePlotDraft,
    resetPlotDraft,
    clearSelectedPlot,
    saveSelectedPlot,
    createPlot,
    saveSelectedPlotGeometry,
    deleteSelectedPlot,
    splitSelectedPlot,
    beginMergeSelection,
    addMergePlotByCoordinate,
    removeMergePlot,
    cancelMergeSelection,
    mergeSelectedPlots,
    undoLastPlotOperation,
    redoLastPlotOperation,
    checkSelectedPlotQuality,
    runTaskQualityChecks,
    loadTaskQualityRuns,
    submitTaskForSelfCheck,
    batchUpdatePlotAttributes,
    selectByCoordinate,
    selectByCode,
    focusByCode,
    loadPlotsForViewport,
  }
})
