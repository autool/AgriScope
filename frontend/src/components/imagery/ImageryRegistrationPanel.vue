<script setup lang="ts">
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { storeToRefs } from 'pinia'
import { computed, reactive, watch } from 'vue'

import { useImageryRegistrationStore } from '@/store/imageryRegistrationStore'
import type {
  ImageryRegistrationResamplingMethod,
  ImageryRegistrationSource,
} from '@/types/imageryRegistration'

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

interface RegistrationFormState {
  jobCode: string
  jobName: string
  referenceKey: string
  movingKey: string
  referenceBandIndex: number
  movingBandIndex: number
  resamplingMethod: ImageryRegistrationResamplingMethod
  maxInitialOffsetPixels: number
  maxResidualPixels: number
  minimumOverlapRatio: number
  minimumPeakToSidelobeRatio: number
  comment: string
}

const registrationStore = useImageryRegistrationStore()
const {
  overviewRef,
  loadingRef,
  creatingRef,
  downloadingJobCodeRef,
  canProcessComputed,
} = storeToRefs(registrationStore)

const form = reactive<RegistrationFormState>({
  jobCode: '',
  jobName: '',
  referenceKey: '',
  movingKey: '',
  referenceBandIndex: 1,
  movingBandIndex: 1,
  resamplingMethod: 'bilinear',
  maxInitialOffsetPixels: 100,
  maxResidualPixels: 1,
  minimumOverlapRatio: 0.2,
  minimumPeakToSidelobeRatio: 5,
  comment: '',
})

const sourceKey = (source: ImageryRegistrationSource): string => (
  `${source.asset_code}|${source.step_code}`
)

const sourceOptionsComputed = computed(() => (
  (overviewRef.value?.available_sources || []).map(source => ({
    value: sourceKey(source),
    label: `${source.asset_name} / ${source.step_name} / ${source.source_band_count} 波段 / ${source.source_crs}`,
    disabled: !source.eligible,
    source,
  }))
))

const sourceByKey = (key: string): ImageryRegistrationSource | null => (
  sourceOptionsComputed.value.find(item => item.value === key)?.source || null
)

const referenceSourceComputed = computed(() => sourceByKey(form.referenceKey))
const movingSourceComputed = computed(() => sourceByKey(form.movingKey))

const eligibleAssetCountComputed = computed<number>(() => (
  new Set(
    (overviewRef.value?.available_sources || [])
      .filter(source => source.eligible)
      .map(source => source.asset_code),
  ).size
))

const bandOptions = (source: ImageryRegistrationSource | null) => (
  Array.from({ length: source?.source_band_count || 0 }, (_, index) => ({
    value: index + 1,
    label: `波段 ${index + 1} · ${source?.band_descriptions[index] || '无描述'}`,
  }))
)

const recommendedBandIndex = (source: ImageryRegistrationSource): number => {
  const redIndex = source.band_descriptions.findIndex((description) => {
    const normalized = (description || '').toLowerCase()
    return normalized.includes('red') || normalized.includes('红')
  })
  return redIndex >= 0 ? redIndex + 1 : 1
}

const selectReference = (key: string): void => {
  form.referenceKey = key
  const source = sourceByKey(key)
  if (source) form.referenceBandIndex = recommendedBandIndex(source)
}

const selectMoving = (key: string): void => {
  form.movingKey = key
  const source = sourceByKey(key)
  if (source) form.movingBandIndex = recommendedBandIndex(source)
}

const sameAssetComputed = computed<boolean>(() => (
  Boolean(referenceSourceComputed.value && movingSourceComputed.value)
  && referenceSourceComputed.value?.asset_code === movingSourceComputed.value?.asset_code
))

const effectiveResidualThresholdComputed = computed<number>(() => Math.min(
  form.maxResidualPixels,
  overviewRef.value?.project_positional_accuracy_pixels || form.maxResidualPixels,
))

const canSubmitComputed = computed<boolean>(() => (
  canProcessComputed.value
  && eligibleAssetCountComputed.value >= 2
  && Boolean(referenceSourceComputed.value?.eligible)
  && Boolean(movingSourceComputed.value?.eligible)
  && !sameAssetComputed.value
  && Boolean(form.jobCode.trim())
  && Boolean(form.jobName.trim())
  && form.maxInitialOffsetPixels > 0
  && form.maxResidualPixels > 0
  && form.minimumOverlapRatio > 0
  && form.minimumOverlapRatio <= 1
  && form.minimumPeakToSidelobeRatio > 0
  && form.comment.trim().length >= 10
))

const resetForm = (): void => {
  form.jobCode = ''
  form.jobName = ''
  form.referenceKey = ''
  form.movingKey = ''
  form.referenceBandIndex = 1
  form.movingBandIndex = 1
  form.resamplingMethod = 'bilinear'
  form.maxInitialOffsetPixels = 100
  form.maxResidualPixels = Math.min(
    1,
    overviewRef.value?.project_positional_accuracy_pixels || 1,
  )
  form.minimumOverlapRatio = 0.2
  form.minimumPeakToSidelobeRatio = 5
  form.comment = ''
}

const refresh = async (): Promise<void> => {
  try {
    await registrationStore.load()
    if (overviewRef.value) {
      form.maxResidualPixels = Math.min(
        form.maxResidualPixels,
        overviewRef.value.project_positional_accuracy_pixels,
      )
    }
  } catch {
    return
  }
}

const submit = async (): Promise<void> => {
  const reference = referenceSourceComputed.value
  const moving = movingSourceComputed.value
  if (!canSubmitComputed.value || !reference || !moving) {
    message.warning('请完成两景业务影像、配准波段、精度门槛和依据配置')
    return
  }
  try {
    await registrationStore.createJob({
      job_code: form.jobCode.trim(),
      job_name: form.jobName.trim(),
      reference: {
        asset_code: reference.asset_code,
        step_code: reference.step_code,
        band_index: form.referenceBandIndex,
      },
      moving: {
        asset_code: moving.asset_code,
        step_code: moving.step_code,
        band_index: form.movingBandIndex,
      },
      resampling_method: form.resamplingMethod,
      max_initial_offset_pixels: form.maxInitialOffsetPixels,
      max_residual_pixels: form.maxResidualPixels,
      minimum_overlap_ratio: form.minimumOverlapRatio,
      minimum_peak_to_sidelobe_ratio: form.minimumPeakToSidelobeRatio,
      comment: form.comment.trim(),
    })
    message.success('影像配准实体已生成并通过服务端残差门禁')
    resetForm()
  } catch {
    return
  }
}

const download = async (jobCode: string, filename: string): Promise<void> => {
  try {
    await registrationStore.downloadJob(jobCode, filename)
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
    title="双景自动配准与像素残差验收"
    width="min(920px, 94vw)"
    @close="emit('update:open', false)"
  >
    <a-result
      v-if="!loadingRef && !canProcessComputed"
      status="403"
      title="当前项目身份无影像处理权限"
      sub-title="自动配准只能由具备 process_imagery 能力的稳定项目用户执行。"
    />
    <a-spin v-else :spinning="loadingRef || creatingRef">
      <div class="registration-actions">
        <a-alert
          type="info"
          show-icon
          message="位移与残差均由服务端计算"
          description="平台在真实公共像元窗口执行相位相关，生成与参考影像同 CRS、同分辨率、同网格的 GeoTIFF，再次计算残差；前端不能填写结果冒充配准证据。"
        />
        <a-button :loading="loadingRef" @click="refresh">
          <ReloadOutlined /> 刷新来源
        </a-button>
      </div>

      <a-alert
        v-if="eligibleAssetCountComputed < 2"
        class="blocker-alert"
        type="warning"
        show-icon
        message="当前不足两景正式业务影像"
        :description="`已校验来源涉及 ${eligibleAssetCountComputed} 个 operational 影像资产；演示影像会显示但不能参与正式配准。`"
      />

      <section class="registration-section">
        <header>
          <div><small>VERIFIED PAIR</small><h3>参考影像与待配准影像</h3></div>
          <a-tag>{{ sourceOptionsComputed.length }} 个步骤实体</a-tag>
        </header>
        <div class="form-grid">
          <label class="wide">
            <span>参考影像步骤实体</span>
            <a-select
              :value="form.referenceKey || undefined"
              show-search
              :options="sourceOptionsComputed"
              :filter-option="(input: string, option: { label?: string }) => String(option.label || '').toLowerCase().includes(input.toLowerCase())"
              placeholder="选择 operational 参考影像"
              @change="selectReference"
            />
          </label>
          <label>
            <span>参考配准波段</span>
            <a-select
              v-model:value="form.referenceBandIndex"
              :disabled="!referenceSourceComputed"
              :options="bandOptions(referenceSourceComputed)"
            />
          </label>
          <label><span>参考 SHA-256</span><a-input :value="referenceSourceComputed?.source_sha256 || ''" readonly /></label>
          <label class="wide">
            <span>待配准影像步骤实体</span>
            <a-select
              :value="form.movingKey || undefined"
              show-search
              :options="sourceOptionsComputed"
              :filter-option="(input: string, option: { label?: string }) => String(option.label || '').toLowerCase().includes(input.toLowerCase())"
              placeholder="选择另一景 operational 影像"
              @change="selectMoving"
            />
          </label>
          <label>
            <span>待配准波段</span>
            <a-select
              v-model:value="form.movingBandIndex"
              :disabled="!movingSourceComputed"
              :options="bandOptions(movingSourceComputed)"
            />
          </label>
          <label><span>待配准 SHA-256</span><a-input :value="movingSourceComputed?.source_sha256 || ''" readonly /></label>
        </div>
        <a-alert
          v-if="sameAssetComputed"
          type="error"
          show-icon
          message="参考影像与待配准影像必须是不同资产"
        />
      </section>

      <section class="registration-section">
        <header><div><small>QUALITY GATES</small><h3>自动估计与残差验收参数</h3></div></header>
        <div class="form-grid">
          <label><span>任务编号</span><a-input v-model:value="form.jobCode" placeholder="如 REG-2026-001" /></label>
          <label><span>任务名称</span><a-input v-model:value="form.jobName" placeholder="填写真实配准任务名称" /></label>
          <label><span>重采样</span><a-select v-model:value="form.resamplingMethod" :options="[{ value: 'bilinear', label: '双线性' }, { value: 'nearest', label: '最近邻' }, { value: 'cubic', label: '三次卷积' }]" /></label>
          <label><span>最大初始偏移（像素）</span><a-input-number v-model:value="form.maxInitialOffsetPixels" :min="0.001" :max="1000" /></label>
          <label>
            <span>请求最大残差（像素）</span>
            <a-input-number
              v-model:value="form.maxResidualPixels"
              :min="0.001"
              :max="10"
              :step="0.1"
            />
          </label>
          <label>
            <span>最小有效重叠率</span>
            <a-input-number
              v-model:value="form.minimumOverlapRatio"
              :min="0.001"
              :max="1"
              :step="0.01"
            />
          </label>
          <label>
            <span>最小相关峰旁比</span>
            <a-input-number
              v-model:value="form.minimumPeakToSidelobeRatio"
              :min="0.1"
              :max="1000"
              :step="0.5"
            />
          </label>
          <label><span>项目精度上限</span><a-input :value="`${overviewRef?.project_positional_accuracy_pixels ?? '--'} 像素`" readonly /></label>
          <label class="wide">
            <span>生产依据</span>
            <a-textarea
              v-model:value="form.comment"
              :rows="3"
              :maxlength="500"
              show-count
              placeholder="至少 10 个字，说明同名地物、影像时相和配准用途"
            />
          </label>
        </div>
        <a-alert
          type="success"
          show-icon
          :message="`实际残差门槛：${effectiveResidualThresholdComputed.toFixed(3)} 像素`"
          description="服务端取请求门槛与项目位置精度规则中的更严格值，输出超限时删除部分文件。"
        />
        <div class="submit-row">
          <a-button @click="resetForm">清空参数</a-button>
          <a-button
            type="primary"
            :disabled="!canSubmitComputed"
            :loading="creatingRef"
            @click="submit"
          >
            执行自动配准与残差验收
          </a-button>
        </div>
      </section>

      <section class="registration-section">
        <header>
          <div><small>PHYSICAL OUTPUTS</small><h3>历史配准实体与质量证据</h3></div>
          <a-tag>{{ overviewRef?.jobs.length || 0 }} 个成果</a-tag>
        </header>
        <a-empty v-if="!overviewRef?.jobs.length" description="当前没有持久化配准成果" />
        <div v-else class="job-list">
          <article v-for="job in overviewRef.jobs" :key="job.job_code">
            <header>
              <div><strong>{{ job.job_name }}</strong><small>{{ job.job_code }} · {{ job.reference_asset_code }} → {{ job.moving_asset_code }}</small></div>
              <a-tag :color="job.artifact_verified ? 'green' : 'error'">{{ job.artifact_verified ? `残差 ${job.residual_offset_pixels.toFixed(4)} px` : '实体失效' }}</a-tag>
            </header>
            <div class="job-metrics">
              <span>初始偏移 {{ job.initial_offset_pixels.toFixed(4) }} px</span>
              <span>残差门槛 {{ job.residual_threshold_pixels.toFixed(3) }} px</span>
              <span>有效重叠 {{ (job.overlap_ratio * 100).toFixed(2) }}%</span>
              <span>峰旁比 {{ job.peak_to_sidelobe_ratio.toFixed(3) }}</span>
              <span>{{ job.raster_width }} × {{ job.raster_height }} · {{ job.output_crs }}</span>
              <span>SHA-256 {{ job.checksum_sha256.slice(0, 16) }}…</span>
            </div>
            <a-alert
              v-if="job.artifact_error"
              type="error"
              show-icon
              :message="job.artifact_error"
            />
            <div class="job-actions">
              <small>{{ new Date(job.created_at).toLocaleString() }} · {{ job.created_by }}（{{ job.created_by_role }}）</small>
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
.registration-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: start; }
.blocker-alert { margin-top: 10px; }
.registration-section { padding: 14px 0; border-bottom: 1px solid #e8ece9; }
.registration-section:last-child { border-bottom: 0; }
.registration-section > header, .job-list article > header, .submit-row, .job-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.registration-section > header { margin-bottom: 10px; }
.registration-section header div { display: flex; flex-direction: column; min-width: 0; }
.registration-section header small { color: #87928c; font-size: 9px; letter-spacing: .08em; }
.registration-section h3 { margin: 1px 0 0; font-size: 14px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-bottom: 10px; }
.form-grid label { display: grid; gap: 5px; min-width: 0; }
.form-grid label > span { color: #56635c; font-size: 11px; }
.form-grid .wide { grid-column: 1 / -1; }
.form-grid :deep(.ant-select), .form-grid :deep(.ant-input-number) { width: 100%; }
.submit-row { margin-top: 10px; }
.job-list { display: grid; gap: 9px; }
.job-list article { padding: 12px; background: #f8faf9; border: 1px solid #e0e7e3; border-radius: 7px; }
.job-list article > header strong, .job-list article > header small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px 12px; margin: 8px 0; color: #68766e; font-size: 10px; }
.job-actions { margin-top: 8px; }
.job-actions small { color: #7e8b84; }
@media (width <= 720px) {
  .registration-actions, .form-grid, .job-metrics { grid-template-columns: 1fr; }
  .form-grid .wide { grid-column: auto; }
}
</style>
