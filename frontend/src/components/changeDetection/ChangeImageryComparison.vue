<script setup lang="ts">
import {
  CompressOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SwapOutlined,
  ZoomInOutlined,
  ZoomOutOutlined,
} from '@ant-design/icons-vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import type { ChangeComparisonMetadata } from '@/types/changeDetection'

type ComparisonMode = 'swipe' | 'flicker' | 'side-by-side'

const props = defineProps<{
  metadata: ChangeComparisonMetadata | null
  loading: boolean
  error: string
}>()

const emit = defineEmits<{
  retry: []
}>()

const modeRef = ref<ComparisonMode>('swipe')
const swipePositionRef = ref<number>(50)
const zoomRef = ref<number>(1)
const translateXRef = ref<number>(0)
const translateYRef = ref<number>(0)
const draggingRef = ref<boolean>(false)
const dragOriginRef = ref<{ x: number; y: number } | null>(null)
const flickerRunningRef = ref<boolean>(false)
const flickerShowTargetRef = ref<boolean>(true)
let flickerTimer: number | null = null
const comparisonSides = ['baseline', 'target'] as const

const imageTransformComputed = computed<string>(() => (
  `translate(${translateXRef.value}px, ${translateYRef.value}px) scale(${zoomRef.value})`
))

const stopFlicker = (): void => {
  if (flickerTimer !== null) window.clearInterval(flickerTimer)
  flickerTimer = null
  flickerRunningRef.value = false
  flickerShowTargetRef.value = true
}

const toggleFlicker = (): void => {
  if (flickerRunningRef.value) {
    stopFlicker()
    return
  }
  flickerRunningRef.value = true
  flickerTimer = window.setInterval(() => {
    flickerShowTargetRef.value = !flickerShowTargetRef.value
  }, 700)
}

const setMode = (mode: ComparisonMode): void => {
  stopFlicker()
  modeRef.value = mode
}

const resetView = (): void => {
  zoomRef.value = 1
  translateXRef.value = 0
  translateYRef.value = 0
  swipePositionRef.value = 50
}

const changeZoom = (delta: number): void => {
  zoomRef.value = Math.min(4, Math.max(1, Number((zoomRef.value + delta).toFixed(2))))
  if (zoomRef.value === 1) {
    translateXRef.value = 0
    translateYRef.value = 0
  }
}

const handleWheel = (event: WheelEvent): void => {
  event.preventDefault()
  changeZoom(event.deltaY < 0 ? 0.2 : -0.2)
}

const startDrag = (event: PointerEvent): void => {
  if (zoomRef.value <= 1) return
  draggingRef.value = true
  dragOriginRef.value = {
    x: event.clientX - translateXRef.value,
    y: event.clientY - translateYRef.value,
  }
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
}

const moveDrag = (event: PointerEvent): void => {
  if (!draggingRef.value || !dragOriginRef.value) return
  translateXRef.value = event.clientX - dragOriginRef.value.x
  translateYRef.value = event.clientY - dragOriginRef.value.y
}

const endDrag = (): void => {
  draggingRef.value = false
  dragOriginRef.value = null
}

watch(() => props.metadata?.run_code, () => {
  stopFlicker()
  resetView()
})

onBeforeUnmount(stopFlicker)
</script>

<template>
  <section class="comparison-panel">
    <header>
      <span><SwapOutlined /><i><strong>前后时相同步对比</strong><small>同一 WGS84 公共网格、共同拉伸与一致变换</small></i></span>
      <div class="mode-actions">
        <a-segmented
          :value="modeRef"
          :options="[
            { label: '卷帘', value: 'swipe' },
            { label: '闪烁', value: 'flicker' },
            { label: '并排', value: 'side-by-side' },
          ]"
          @change="(value: ComparisonMode) => setMode(value)"
        />
        <a-button-group>
          <a-button title="缩小" :disabled="zoomRef <= 1" @click="changeZoom(-0.2)"><ZoomOutOutlined /></a-button>
          <a-button title="放大" :disabled="zoomRef >= 4" @click="changeZoom(0.2)"><ZoomInOutlined /></a-button>
          <a-button title="重置视图" @click="resetView"><CompressOutlined /></a-button>
        </a-button-group>
      </div>
    </header>

    <div v-if="loading" class="comparison-state">
      <a-spin tip="正在校验源文件并生成公共网格预览…" />
    </div>
    <div v-else-if="error" class="comparison-state error-state">
      <a-alert
        type="error"
        show-icon
        message="双时相预览不可用"
        :description="error"
      />
      <a-button @click="emit('retry')"><ReloadOutlined /> 重试</a-button>
    </div>
    <div v-else-if="!metadata" class="comparison-state">
      <a-empty description="选择变化检测任务后加载真实影像对比" />
    </div>

    <template v-else>
      <div v-if="modeRef === 'side-by-side'" class="side-by-side">
        <div
          v-for="side in comparisonSides"
          :key="side"
          class="comparison-stage"
          :class="{ dragging: draggingRef }"
          @wheel="handleWheel"
          @pointerdown="startDrag"
          @pointermove="moveDrag"
          @pointerup="endDrag"
          @pointercancel="endDrag"
        >
          <img
            :src="side === 'baseline' ? metadata.baseline_url : metadata.target_url"
            :alt="side === 'baseline' ? '前时相影像' : '后时相影像'"
            :style="{ transform: imageTransformComputed }"
            draggable="false"
          >
          <span class="time-label">{{ side === 'baseline' ? '前时相' : '后时相' }} · {{ (side === 'baseline' ? metadata.baseline.acquired_at : metadata.target.acquired_at).slice(0, 10) }}</span>
        </div>
      </div>

      <div
        v-else
        class="comparison-stage stacked"
        :class="{ dragging: draggingRef }"
        @wheel="handleWheel"
        @pointerdown="startDrag"
        @pointermove="moveDrag"
        @pointerup="endDrag"
        @pointercancel="endDrag"
      >
        <img
          :src="metadata.baseline_url"
          alt="前时相影像"
          :style="{ transform: imageTransformComputed }"
          draggable="false"
        >
        <div
          class="target-layer"
          :style="modeRef === 'swipe'
            ? { clipPath: `inset(0 0 0 ${swipePositionRef}%)` }
            : { opacity: flickerShowTargetRef ? 1 : 0 }"
        >
          <img
            :src="metadata.target_url"
            alt="后时相影像"
            :style="{ transform: imageTransformComputed }"
            draggable="false"
          >
        </div>
        <template v-if="modeRef === 'swipe'">
          <div class="swipe-line" :style="{ left: `${swipePositionRef}%` }"><i /></div>
          <input
            v-model.number="swipePositionRef"
            class="swipe-slider"
            type="range"
            min="0"
            max="100"
            aria-label="卷帘位置"
            @pointerdown.stop
          >
        </template>
        <a-button v-else class="flicker-button" @click.stop="toggleFlicker">
          <PauseCircleOutlined v-if="flickerRunningRef" />
          <PlayCircleOutlined v-else />
          {{ flickerRunningRef ? '暂停闪烁' : '开始闪烁' }}
        </a-button>
        <span class="time-label baseline-label">前时相 · {{ metadata.baseline.acquired_at.slice(0, 10) }}</span>
        <span class="time-label target-label">后时相 · {{ metadata.target.acquired_at.slice(0, 10) }}</span>
      </div>

      <footer>
        <span>公共范围 {{ metadata.bounds_wgs84.map((value) => value.toFixed(4)).join(', ') }}</span>
        <span>{{ metadata.width }} × {{ metadata.height }} · {{ metadata.renderer_version }}</span>
        <span>源 SHA {{ metadata.baseline.checksum_sha256.slice(0, 8) }} / {{ metadata.target.checksum_sha256.slice(0, 8) }}</span>
      </footer>
    </template>
  </section>
</template>

<style scoped>
.comparison-panel { display: grid; grid-template-rows: auto minmax(0, 1fr) auto; height: 100%; min-height: 420px; background: #17201c; }
.comparison-panel > header { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; color: #dce8e1; background: #233129; border-bottom: 1px solid #35463c; }
.comparison-panel > header > span, .mode-actions { display: flex; gap: 8px; align-items: center; }
.comparison-panel > header > span > :first-child { font-size: 18px; color: #77c69a; }
.comparison-panel header i { display: flex; flex-direction: column; font-style: normal; }
.comparison-panel header strong { font-size: 11px; }
.comparison-panel header small { font-size: 8px; color: #8fa299; }
.comparison-panel :deep(.ant-segmented) { background: #16231c; }
.comparison-panel :deep(.ant-segmented-item) { color: #b8c8c0; }
.comparison-panel :deep(.ant-segmented-item-selected) { color: #244331; background: #dcece2; }
.comparison-state { display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; min-height: 360px; padding: 24px; background: #f8faf8; }
.error-state { align-items: stretch; }
.side-by-side { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; min-height: 0; background: #314039; }
.comparison-stage { position: relative; min-width: 0; min-height: 360px; overflow: hidden; touch-action: none; cursor: grab; background: #0c100e; }
.comparison-stage.dragging { cursor: grabbing; }
.comparison-stage img, .target-layer { position: absolute; inset: 0; width: 100%; height: 100%; }
.comparison-stage img { object-fit: contain; user-select: none; transform-origin: center; transition: transform 80ms linear; }
.target-layer { pointer-events: none; transition: opacity 80ms linear; }
.swipe-line { position: absolute; top: 0; bottom: 0; width: 2px; background: #f4f7f5; box-shadow: 0 0 0 1px rgb(0 0 0 / 35%); pointer-events: none; }
.swipe-line i { position: absolute; top: 50%; left: 50%; width: 24px; height: 24px; background: #fff; border: 2px solid #2f7552; border-radius: 50%; transform: translate(-50%, -50%); }
.swipe-slider { position: absolute; right: 12px; bottom: 12px; left: 12px; z-index: 4; accent-color: #55a97a; }
.flicker-button { position: absolute; bottom: 12px; left: 50%; z-index: 4; transform: translateX(-50%); }
.time-label { position: absolute; top: 9px; z-index: 3; padding: 3px 7px; font-size: 9px; color: #fff; background: rgb(10 19 14 / 72%); border-radius: 3px; pointer-events: none; }
.baseline-label, .side-by-side .time-label { left: 9px; }
.target-label { right: 9px; }
.comparison-panel footer { display: flex; justify-content: space-between; gap: 10px; padding: 5px 9px; overflow: hidden; font-size: 8px; color: #9db0a6; background: #1b2821; border-top: 1px solid #35463c; }
.comparison-panel footer span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1100px) {
  .comparison-panel > header { align-items: flex-start; }
  .mode-actions { flex-wrap: wrap; justify-content: flex-end; }
  .side-by-side { grid-template-columns: 1fr; grid-template-rows: 1fr 1fr; }
  .comparison-stage { min-height: 260px; }
  .comparison-panel footer span:first-child { display: none; }
}
</style>
