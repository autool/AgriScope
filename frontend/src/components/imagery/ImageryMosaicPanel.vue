<script setup lang="ts">
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, reactive, watch } from 'vue'

import { useImageryMosaicStore } from '@/store/imageryMosaicStore'
import type {
  ImageryMosaicBoundaryFeature,
  ImageryMosaicColorBalanceMethod,
  ImageryMosaicBlendMethod,
  ImageryMosaicResamplingMethod,
  ImageryMosaicSource,
  ImageryMosaicStepCode,
} from '@/types/imageryMosaic'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

interface MosaicFormState {
  jobCode: string
  jobName: string
  boundaryCode: string
  targetCrs: string
  targetResolution: number
  colorBalanceMethod: ImageryMosaicColorBalanceMethod
  blendMethod: ImageryMosaicBlendMethod
  resamplingMethod: ImageryMosaicResamplingMethod
  coverageThreshold: number
  comment: string
  sourceStepByAsset: Record<string, ImageryMosaicStepCode | undefined>
}

interface MosaicSourceGroup {
  assetCode: string
  assetName: string
  sources: ImageryMosaicSource[]
}

const mosaicStore = useImageryMosaicStore()
const {
  overviewRef,
  boundariesRef,
  loadingRef,
  creatingRef,
  downloadingJobCodeRef,
  canProcessComputed,
} = storeToRefs(mosaicStore)

const form = reactive<MosaicFormState>({
  jobCode: '',
  jobName: '',
  boundaryCode: '',
  targetCrs: 'EPSG:4326',
  targetResolution: 0.0001,
  colorBalanceMethod: 'mean_std',
  blendMethod: 'mean',
  resamplingMethod: 'bilinear',
  coverageThreshold: 98,
  comment: '',
  sourceStepByAsset: {},
})

const stepOptions = [
  { value: 'geometric', label: '几何校正成果' },
  { value: 'clip', label: '行政区裁剪成果' },
  { value: 'enhancement', label: '增强成果' },
  { value: 'band_products', label: '波段产品成果' },
]

const sourceGroupsComputed = computed<MosaicSourceGroup[]>(() => {
  const groups = new Map<string, MosaicSourceGroup>()
  for (const source of overviewRef.value?.available_sources || []) {
    const group = groups.get(source.asset_code) || {
      assetCode: source.asset_code,
      assetName: source.asset_name,
      sources: [],
    }
    group.sources.push(source)
    groups.set(source.asset_code, group)
  }
  return [...groups.values()].map(group => ({
    ...group,
    sources: [...group.sources].sort((left, right) => (
      stepOptions.findIndex(item => item.value === left.step_code)
      - stepOptions.findIndex(item => item.value === right.step_code)
    )),
  }))
})

const selectedSourcesComputed = computed<ImageryMosaicSource[]>(() => (
  sourceGroupsComputed.value.flatMap((group) => {
    const stepCode = form.sourceStepByAsset[group.assetCode]
    const source = group.sources.find(item => item.step_code === stepCode)
    return source ? [source] : []
  })
))

const boundaryNameByCodeComputed = computed<Map<string, string>>(() => (
  new Map(boundariesRef.value.map(feature => [
    feature.properties.boundary_code,
    feature.properties.boundary_name,
  ]))
))

const boundaryOptionsComputed = computed(() => {
  const levelOrder = { province: 0, city: 1, district: 2, township: 3 }
  return [...boundariesRef.value]
    .sort((left, right) => {
      const levelDifference = (
        levelOrder[left.properties.boundary_level]
        - levelOrder[right.properties.boundary_level]
      )
      if (levelDifference !== 0) return levelDifference
      const parentDifference = (left.properties.parent_code || '').localeCompare(
        right.properties.parent_code || '',
      )
      if (parentDifference !== 0) return parentDifference
      return left.properties.boundary_code.localeCompare(right.properties.boundary_code)
    })
    .map((feature) => {
      const properties = feature.properties
      const levelLabel = {
        province: '省级',
        city: '地级',
        district: '县级',
        township: '乡级',
      }[properties.boundary_level]
      const parentName = properties.parent_code
        ? boundaryNameByCodeComputed.value.get(properties.parent_code)
        : null
      return {
        value: properties.boundary_code,
        label: `${levelLabel} · ${parentName ? `${parentName} / ` : ''}${properties.boundary_name}`,
      }
    })
})

const selectedBoundaryComputed = computed<ImageryMosaicBoundaryFeature | null>(() => (
  boundariesRef.value.find(
    item => item.properties.boundary_code === form.boundaryCode,
  ) || null
))

const collectGeometryExtent = (
  feature: ImageryMosaicBoundaryFeature,
): [number, number, number, number] | null => {
  const points: Array<[number, number]> = []
  const collect = (value: unknown): void => {
    if (
      Array.isArray(value)
      && value.length >= 2
      && typeof value[0] === 'number'
      && typeof value[1] === 'number'
    ) {
      points.push([value[0], value[1]])
      return
    }
    if (Array.isArray(value)) value.forEach(collect)
  }
  collect(feature.geometry.coordinates)
  if (!points.length) return null
  return [
    Math.min(...points.map(item => item[0])),
    Math.min(...points.map(item => item[1])),
    Math.max(...points.map(item => item[0])),
    Math.max(...points.map(item => item[1])),
  ]
}

const estimatedPixelCountComputed = computed<number | null>(() => {
  const boundary = selectedBoundaryComputed.value
  if (!boundary || selectedSourcesComputed.value.length < 2) return null
  const extents = selectedSourcesComputed.value
    .map(item => item.bounds_wgs84)
    .filter((item): item is number[] => item?.length === 4)
  const boundaryExtent = collectGeometryExtent(boundary)
  if (!boundaryExtent || !extents.length || form.targetResolution <= 0) return null
  extents.push(boundaryExtent)
  let left = Math.min(...extents.map(item => item[0]))
  let bottom = Math.min(...extents.map(item => item[1]))
  let right = Math.max(...extents.map(item => item[2]))
  let top = Math.max(...extents.map(item => item[3]))
  if (form.targetCrs === 'EPSG:3857') {
    const projectLongitude = (longitude: number): number => (
      longitude * 20037508.34 / 180
    )
    const projectLatitude = (latitude: number): number => {
      const limited = Math.max(-85.05112878, Math.min(85.05112878, latitude))
      const radians = limited * Math.PI / 180
      return Math.log(Math.tan(Math.PI / 4 + radians / 2)) * 6378137
    }
    left = projectLongitude(left)
    right = projectLongitude(right)
    bottom = projectLatitude(bottom)
    top = projectLatitude(top)
  } else if (!['EPSG:4326', 'EPSG:4490'].includes(form.targetCrs.toUpperCase())) {
    return null
  }
  const width = Math.ceil((right - left) / form.targetResolution) + 2
  const height = Math.ceil((top - bottom) / form.targetResolution) + 2
  return width > 0 && height > 0 ? width * height : null
})

const exceedsPixelLimitComputed = computed<boolean>(() => (
  estimatedPixelCountComputed.value !== null
  && estimatedPixelCountComputed.value > (overviewRef.value?.max_output_pixels || 0)
))

const compatibilityMessageComputed = computed<string | null>(() => {
  const sources = selectedSourcesComputed.value
  if (sources.length < 2) return null
  const reference = sources[0]
  const referenceDescriptions = JSON.stringify(reference.band_descriptions)
  if (sources.some(item => item.source_band_count !== reference.source_band_count)) {
    return '所选来源波段数量不一致，服务端将拒绝镶嵌'
  }
  if (sources.some(item => JSON.stringify(item.band_descriptions) !== referenceDescriptions)) {
    return '所选来源波段描述不一致，请改选具有相同波段定义的步骤产物'
  }
  return null
})

const canSubmitComputed = computed<boolean>(() => (
  canProcessComputed.value
  && selectedSourcesComputed.value.length >= 2
  && selectedSourcesComputed.value.length <= 20
  && Boolean(form.jobCode.trim())
  && Boolean(form.jobName.trim())
  && Boolean(form.boundaryCode)
  && Boolean(form.targetCrs.trim())
  && form.targetResolution > 0
  && form.coverageThreshold > 0
  && form.coverageThreshold <= 100
  && form.comment.trim().length >= 10
  && !compatibilityMessageComputed.value
  && !exceedsPixelLimitComputed.value
))

const setTargetCrs = (value: string): void => {
  form.targetCrs = value.trim().toUpperCase()
  form.targetResolution = ['EPSG:4326', 'EPSG:4490'].includes(form.targetCrs)
    ? 0.0001
    : 10
}

const resetForm = (): void => {
  form.jobCode = ''
  form.jobName = ''
  form.boundaryCode = ''
  form.targetCrs = 'EPSG:4326'
  form.targetResolution = 0.0001
  form.colorBalanceMethod = 'mean_std'
  form.blendMethod = 'mean'
  form.resamplingMethod = 'bilinear'
  form.coverageThreshold = 98
  form.comment = ''
  form.sourceStepByAsset = {}
}

const refresh = async (): Promise<void> => {
  try {
    await mosaicStore.load()
  } catch {
    return
  }
}

const submit = async (): Promise<void> => {
  if (!canSubmitComputed.value) {
    message.warning('请完成来源、行政区、目标网格和验收依据配置')
    return
  }
  try {
    await mosaicStore.createJob({
      job_code: form.jobCode.trim(),
      job_name: form.jobName.trim(),
      boundary_code: form.boundaryCode,
      target_crs: form.targetCrs.trim(),
      target_resolution: form.targetResolution,
      color_balance_method: form.colorBalanceMethod,
      blend_method: form.blendMethod,
      resampling_method: form.resamplingMethod,
      coverage_threshold: form.coverageThreshold,
      sources: selectedSourcesComputed.value.map(source => ({
        asset_code: source.asset_code,
        step_code: source.step_code,
      })),
      comment: form.comment.trim(),
    })
    message.success('多景镶嵌实体已生成并通过行政区覆盖率验收')
    resetForm()
  } catch {
    return
  }
}

const download = async (jobCode: string, filename: string): Promise<void> => {
  try {
    await mosaicStore.downloadJob(jobCode, filename)
  } catch {
    return
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void refresh()
  },
  { immediate: true },
)
</script>

<template>
  <a-drawer
    :open="open"
    title="多景匀色、镶嵌与覆盖率验收"
    width="min(960px, 94vw)"
    class="imagery-mosaic-drawer"
    @close="emit('update:open', false)"
  >
    <a-result
      v-if="!canProcessComputed"
      status="403"
      title="当前项目身份无影像处理权限"
      sub-title="多景生产只能由具备 process_imagery 能力的稳定项目用户执行。"
    />
    <a-spin v-else :spinning="loadingRef || creatingRef">
      <div class="drawer-actions">
        <a-alert
          type="info"
          show-icon
          message="覆盖率使用完整行政区作为分母"
          description="服务端按影像并集与完整行政区共同构建目标网格；行政区落在影像之外的部分计为 NoData，局部成果不能冒充完整镶嵌。"
        />
        <a-button :loading="loadingRef" @click="refresh">
          <ReloadOutlined /> 刷新真实来源
        </a-button>
      </div>

      <section class="mosaic-section">
        <header>
          <div><small>VERIFIED INPUTS</small><h3>显式选择 2–20 景实体来源</h3></div>
          <a-tag :color="selectedSourcesComputed.length >= 2 ? 'green' : 'orange'">
            已选 {{ selectedSourcesComputed.length }} 景
          </a-tag>
        </header>
        <a-empty
          v-if="!sourceGroupsComputed.length"
          description="当前没有通过实体文件、大小和 SHA-256 复核的可用来源"
        />
        <div v-else class="source-grid">
          <article v-for="group in sourceGroupsComputed" :key="group.assetCode">
            <div>
              <strong>{{ group.assetName }}</strong>
              <small>{{ group.assetCode }}</small>
            </div>
            <a-select
              v-model:value="form.sourceStepByAsset[group.assetCode]"
              allow-clear
              placeholder="选择该景的一个步骤产物"
              :options="group.sources.map(source => ({
                value: source.step_code,
                label: `${source.step_name} · ${source.source_band_count} 波段 · ${source.source_crs}`,
              }))"
            />
            <p v-if="form.sourceStepByAsset[group.assetCode]">
              SHA-256
              {{ group.sources.find(item => item.step_code === form.sourceStepByAsset[group.assetCode])?.source_sha256.slice(0, 16) }}…
            </p>
          </article>
        </div>
        <a-alert
          v-if="compatibilityMessageComputed"
          type="error"
          show-icon
          :message="compatibilityMessageComputed"
        />
      </section>

      <section class="mosaic-section">
        <header>
          <div><small>PRODUCTION PARAMETERS</small><h3>目标网格、算法与验收门槛</h3></div>
        </header>
        <div class="form-grid">
          <label><span>任务编号</span><a-input v-model:value="form.jobCode" placeholder="如 MOSAIC-2026-001" /></label>
          <label><span>任务名称</span><a-input v-model:value="form.jobName" placeholder="填写真实生产任务名称" /></label>
          <label class="wide">
            <span>真实行政区范围</span>
            <a-select
              v-model:value="form.boundaryCode"
              show-search
              :filter-option="(input: string, option: { label?: string }) => String(option.label || '').toLowerCase().includes(input.toLowerCase())"
              :options="boundaryOptionsComputed"
              placeholder="搜索省、市、县行政区"
            />
          </label>
          <label>
            <span>目标 CRS</span>
            <a-select
              :value="form.targetCrs"
              :options="[
                { value: 'EPSG:4326', label: 'EPSG:4326 · WGS84' },
                { value: 'EPSG:4490', label: 'EPSG:4490 · CGCS2000' },
                { value: 'EPSG:3857', label: 'EPSG:3857 · Web Mercator' },
              ]"
              @change="setTargetCrs"
            />
          </label>
          <label>
            <span>目标分辨率</span>
            <a-input-number
              v-model:value="form.targetResolution"
              :min="0.00000001"
              :max="1000000"
              :step="form.targetCrs === 'EPSG:3857' ? 1 : 0.00001"
            />
          </label>
          <label><span>匀色方法</span><a-select v-model:value="form.colorBalanceMethod" :options="[{ value: 'mean_std', label: '全局均值 / 标准差' }, { value: 'none', label: '不匀色' }]" /></label>
          <label><span>重叠合成</span><a-select v-model:value="form.blendMethod" :options="[{ value: 'mean', label: '重叠像元均值' }, { value: 'first', label: '首景优先' }]" /></label>
          <label><span>重采样</span><a-select v-model:value="form.resamplingMethod" :options="[{ value: 'bilinear', label: '双线性' }, { value: 'nearest', label: '最近邻' }, { value: 'cubic', label: '三次卷积' }]" /></label>
          <label>
            <span>最低覆盖率（%）</span>
            <a-input-number
              v-model:value="form.coverageThreshold"
              :min="0.001"
              :max="100"
              :step="0.1"
            />
          </label>
          <label class="wide">
            <span>生产与验收依据</span>
            <a-textarea
              v-model:value="form.comment"
              :rows="3"
              :maxlength="500"
              show-count
              placeholder="至少 10 个字，说明来源、匀色策略和验收用途"
            />
          </label>
        </div>
        <a-alert
          v-if="estimatedPixelCountComputed !== null"
          :type="exceedsPixelLimitComputed ? 'error' : 'success'"
          show-icon
          :message="`前端保守估算 ${estimatedPixelCountComputed.toLocaleString()} 像元；服务端上限 ${(overviewRef?.max_output_pixels || 0).toLocaleString()} 像元`"
          :description="exceedsPixelLimitComputed ? '当前参数预计超限，请降低分辨率或缩小行政区范围。' : '最终以服务端按目标 CRS 对齐后的完整网格计算为准。'"
        />
        <a-alert
          v-else
          type="warning"
          show-icon
          message="当前 CRS 无法在浏览器可靠估算像元数"
          description="服务端仍会使用完整行政区和影像并集计算，并在超出配置上限时明确拒绝且不保留部分成果。"
        />
        <div class="submit-row">
          <a-button @click="resetForm">清空参数</a-button>
          <a-button
            type="primary"
            :disabled="!canSubmitComputed"
            :loading="creatingRef"
            @click="submit"
          >
            执行实体镶嵌与覆盖验收
          </a-button>
        </div>
      </section>

      <section class="mosaic-section">
        <header>
          <div><small>PHYSICAL OUTPUTS</small><h3>历史实体成果与输入血缘</h3></div>
          <a-tag>{{ overviewRef?.jobs.length || 0 }} 个成果</a-tag>
        </header>
        <a-empty v-if="!overviewRef?.jobs.length" description="当前没有持久化镶嵌成果" />
        <div v-else class="job-list">
          <article v-for="job in overviewRef.jobs" :key="job.job_code">
            <header>
              <div><strong>{{ job.job_name }}</strong><small>{{ job.job_code }} · {{ job.boundary_name }}</small></div>
              <a-tag :color="job.artifact_verified && job.meets_coverage ? 'green' : 'error'">
                {{ job.artifact_verified ? `覆盖率 ${job.coverage_ratio.toFixed(3)}%` : '实体失效' }}
              </a-tag>
            </header>
            <a-progress :percent="Math.min(job.coverage_ratio, 100)" :show-info="false" :status="job.artifact_verified ? 'normal' : 'exception'" />
            <div class="job-evidence">
              <span>{{ job.raster_width.toLocaleString() }} × {{ job.raster_height.toLocaleString() }} · {{ job.band_count }} 波段 · {{ job.dtype }}</span>
              <span>{{ (job.file_size_bytes / 1024 / 1024).toFixed(2) }} MB · SHA-256 {{ job.checksum_sha256.slice(0, 16) }}…</span>
              <span>{{ job.target_crs }} · 分辨率 {{ job.target_resolution }} · {{ job.source_count }} 景</span>
              <span>{{ new Date(job.created_at).toLocaleString() }} · {{ job.created_by }}（{{ job.created_by_role }}）</span>
            </div>
            <a-alert
              v-if="job.artifact_error"
              type="error"
              show-icon
              :message="job.artifact_error"
            />
            <div class="lineage-list">
              <a-tag v-for="source in job.inputs" :key="`${source.asset_code}-${source.step_code}`">
                {{ source.asset_code }} / {{ source.step_name }} / {{ source.source_sha256.slice(0, 10) }}…
              </a-tag>
            </div>
            <div class="job-actions">
              <a-button
                size="small"
                :disabled="!job.artifact_verified || !job.download_url"
                :loading="downloadingJobCodeRef === job.job_code"
                @click="download(job.job_code, job.original_filename)"
              >
                <DownloadOutlined /> 下载 GeoTIFF
              </a-button>
            </div>
          </article>
        </div>
      </section>
    </a-spin>
  </a-drawer>
</template>

<style scoped>
.drawer-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: start; }
.mosaic-section { padding: 14px 0; border-bottom: 1px solid #e8ece9; }
.mosaic-section:last-child { border-bottom: 0; }
.mosaic-section > header, .job-list article > header, .submit-row, .job-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.mosaic-section > header { margin-bottom: 10px; }
.mosaic-section header div { display: flex; flex-direction: column; }
.mosaic-section header small { font-size: 9px; color: #87928c; letter-spacing: .08em; }
.mosaic-section h3 { margin: 1px 0 0; font-size: 14px; }
.source-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.source-grid article { display: grid; gap: 7px; padding: 10px; background: #f7f9f8; border: 1px solid #e2e8e4; border-radius: 6px; }
.source-grid article > div { display: flex; flex-direction: column; min-width: 0; }
.source-grid strong, .source-grid small, .source-grid p { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.source-grid small, .source-grid p { color: #7f8c85; font-size: 10px; }
.source-grid p { margin: 0; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 10px; }
.form-grid label { display: grid; gap: 5px; min-width: 0; }
.form-grid label > span { font-size: 11px; color: #56635c; }
.form-grid .wide { grid-column: 1 / -1; }
.form-grid :deep(.ant-input-number), .form-grid :deep(.ant-select) { width: 100%; }
.submit-row { margin-top: 10px; }
.job-list { display: grid; gap: 9px; }
.job-list article { padding: 12px; background: #f8faf9; border: 1px solid #e0e7e3; border-radius: 7px; }
.job-list article > header > div { min-width: 0; }
.job-list article > header strong, .job-list article > header small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-evidence { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px 12px; margin: 7px 0; color: #68766e; font-size: 10px; }
.lineage-list { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 8px; }
.job-actions { margin-top: 9px; }
@media (width <= 720px) {
  .drawer-actions, .source-grid, .form-grid, .job-evidence { grid-template-columns: 1fr; }
  .form-grid .wide { grid-column: auto; }
}
</style>
