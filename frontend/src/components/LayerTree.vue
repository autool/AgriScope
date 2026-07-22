<script setup lang="ts">
import {
  CloudOutlined,
  EyeOutlined,
  FileImageOutlined,
} from '@ant-design/icons-vue'
import { computed, ref } from 'vue'

import LayerHierarchyCatalog from '@/components/LayerHierarchyCatalog.vue'
import { useLayerStore } from '@/store/layerStore'
import type { FarmlandHierarchyNode } from '@/store/layerStore'
import { useMapStore } from '@/store/mapStore'
import { useWorkbenchStore } from '@/store/workbenchStore'

import type { ImagerySummary } from '@/types/workbench'

interface LayerTreeProps {
  imagery?: ImagerySummary | null
}

const props = withDefaults(defineProps<LayerTreeProps>(), {
  imagery: null,
})

const layerStore = useLayerStore()
const mapStore = useMapStore()
const workbenchStore = useWorkbenchStore()
const activeSectionRef = ref<'layers' | 'imagery'>('layers')
const farmlandCountComputed = computed<number>(
  () => layerStore.plotCatalogRef?.total_count || 0,
)

const handleHierarchySelect = async (node: FarmlandHierarchyNode): Promise<void> => {
  mapStore.focusExtent(node.extent)
  if (node.plotCode) {
    try {
      await workbenchStore.selectByCode(node.plotCode)
    } catch {
      // 请求拦截器已统一提示安全错误，组件只负责终止本次选择流程。
    }
  }
}
</script>

<template>
  <section class="resource-panel">
    <div class="resource-tabs">
      <button :class="{ active: activeSectionRef === 'layers' }" @click="activeSectionRef = 'layers'">图层</button>
      <button :class="{ active: activeSectionRef === 'imagery' }" @click="activeSectionRef = 'imagery'">影像</button>
    </div>

    <template v-if="activeSectionRef === 'layers'">
      <LayerHierarchyCatalog
        :farmland-hierarchy="layerStore.farmlandHierarchyComputed"
        :administrative-hierarchy="layerStore.administrativeHierarchyComputed"
        :farmland-count="farmlandCountComputed"
        :land-class-counts="layerStore.plotCatalogRef?.land_class_counts || {}"
        @select-node="handleHierarchySelect"
      />

      <div class="layer-list">
        <div v-for="layer in layerStore.layersRef" :key="layer.key" class="layer-row">
          <div class="layer-title-row">
            <i :class="layer.type"><EyeOutlined /></i>
            <span><strong>{{ layer.title }}</strong><small>{{ layer.type.toUpperCase() }}</small></span>
            <a-switch
              size="small"
              :checked="layer.visible"
              @change="(value: boolean) => layerStore.setVisibility(layer.key, value)"
            />
          </div>
          <div
            v-if="layer.visible && ['base', 'farmland', 'disaster', 'boundary'].includes(layer.key)"
            class="opacity-row"
          >
            <span>透明度</span>
            <a-slider
              :value="layer.opacity"
              :tooltip-open="false"
              @change="(value: number) => layerStore.setOpacity(layer.key, value)"
            />
            <b>{{ layer.opacity }}%</b>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div v-if="props.imagery" class="scene-card">
        <div class="scene-preview">
          <FileImageOutlined />
          <span>{{ props.imagery.asset_name }}</span>
        </div>
        <div class="scene-title">
          <span><small>当前业务影像</small><strong>{{ props.imagery.sensor_type }}</strong></span>
          <a-tag
            :color="props.imagery.correction_status === 'completed' ? 'green' : 'default'"
          >
            {{ props.imagery.correction_status === 'completed' ? '校正完成' : '待完成校正' }}
          </a-tag>
        </div>
        <dl>
          <div><dt>采集时间</dt><dd>{{ props.imagery.acquired_at.slice(0, 16).replace('T', ' ') }}</dd></div>
          <div><dt>空间分辨率</dt><dd>{{ props.imagery.resolution_m ?? '--' }}<template v-if="props.imagery.resolution_m !== null"> m</template></dd></div>
          <div><dt>云量</dt><dd>{{ props.imagery.cloud_cover ?? '--' }}<template v-if="props.imagery.cloud_cover !== null">%</template></dd></div>
          <div><dt>处理级别</dt><dd>{{ props.imagery.processing_level || '--' }}</dd></div>
        </dl>
      </div>

      <div v-if="props.imagery" class="band-section">
        <h3>波段与指数产品</h3>
        <a-alert
          type="info"
          show-icon
          message="以处理流水线实体校验为准"
          description="真彩色、假彩色和 NDVI 只有生成实体产物并通过大小与 SHA256 校验后才可使用。"
        />
      </div>

      <div v-if="props.imagery" class="processing-status">
        <CloudOutlined />
        <span>
          <strong>
            {{ props.imagery.calibration_status === 'completed' && props.imagery.correction_status === 'completed' ? '定标与校正已完成' : '预处理链尚未完成' }}
          </strong>
          <small>处理结果必须在影像预处理页面完成实体证据校验</small>
        </span>
      </div>
      <a-empty
        v-else
        class="imagery-empty"
        description="尚未上传可用业务影像"
      />
    </template>
  </section>
</template>

<style scoped lang="less">
.resource-panel {
  height: 100%;
  overflow: auto;
  background: #fff;
}

.resource-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  height: 42px;
  border-bottom: 1px solid #e2e6e4;
}

.resource-tabs button {
  position: relative;
  font-size: 10px;
  color: #7a8780;
  cursor: pointer;
  background: #fafbfb;
  border: 0;
}

.resource-tabs button.active {
  color: #265e43;
  font-weight: 600;
  background: #fff;
}

.resource-tabs button.active::after {
  position: absolute;
  right: 24px;
  bottom: 0;
  left: 24px;
  height: 2px;
  content: '';
  background: #3f8f66;
}

.layer-title-row,
.opacity-row,
.scene-title,
.band-option,
.processing-status {
  display: flex;
  align-items: center;
}

.scene-title > span,
.band-option > span,
.processing-status > span {
  display: flex;
  flex-direction: column;
}

.scene-title small,
.band-option small,
.processing-status small {
  font-size: 8px;
  color: #8c9791;
}

.scene-title strong {
  font-size: 11px;
}

.layer-list {
  border-top: 1px solid #e6eae8;
}

.layer-row {
  padding: 9px 12px 7px;
  border-bottom: 1px solid #edf0ee;
}

.layer-title-row {
  gap: 8px;
}

.layer-title-row > i {
  display: grid;
  width: 24px;
  height: 24px;
  font-style: normal;
  color: #47765e;
  background: #edf4f0;
  border-radius: 5px;
  place-items: center;
}

.layer-title-row > i.raster {
  color: #886d35;
  background: #f5f0e6;
}

.layer-title-row > span {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
}

.layer-title-row strong {
  overflow: hidden;
  font-size: 9px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.layer-title-row small {
  font-size: 7px;
  color: #9aa39e;
}

.opacity-row {
  display: grid;
  grid-template-columns: 38px 1fr 27px;
  gap: 7px;
  margin-top: 6px;
  font-size: 7px;
  color: #8b9690;
}

.opacity-row b {
  font-weight: 400;
}

:deep(.opacity-row .ant-slider) {
  margin: 4px 0;
}

.scene-card,
.band-section {
  padding: 12px;
  border-bottom: 1px solid #e7ebe9;
}

.scene-preview {
  position: relative;
  display: grid;
  height: 96px;
  overflow: hidden;
  color: rgb(255 255 255 / 75%);
  background:
    linear-gradient(135deg, rgb(27 58 43 / 18%), rgb(176 154 86 / 14%)),
    url('/imagery-tiles/10/365/872') center / cover;
  border-radius: 6px;
  place-items: center;
}

.scene-preview > :first-child {
  font-size: 22px;
}

.scene-preview span {
  position: absolute;
  right: 7px;
  bottom: 6px;
  left: 7px;
  padding: 3px 5px;
  overflow: hidden;
  font-family: ui-monospace, monospace;
  font-size: 7px;
  color: #fff;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: rgb(15 34 26 / 66%);
  border-radius: 3px;
}

.scene-title {
  justify-content: space-between;
  margin: 10px 0 8px;
}

.scene-card dl {
  margin: 0;
}

.scene-card dl > div {
  display: flex;
  justify-content: space-between;
  min-height: 22px;
  font-size: 8px;
  border-bottom: 1px dashed #e5e9e7;
}

.scene-card dt {
  color: #8a958f;
}

.scene-card dd {
  margin: 0;
}

.band-section h3 {
  margin: 0 0 8px;
  font-size: 10px;
}

.band-option {
  gap: 9px;
  width: 100%;
  min-height: 39px;
  padding: 5px 7px;
  margin-bottom: 4px;
  text-align: left;
  cursor: pointer;
  background: #fff;
  border: 1px solid #e2e7e4;
  border-radius: 5px;
}

.band-option.active {
  border-color: #65a681;
  box-shadow: 0 0 0 2px rgb(80 160 117 / 9%);
}

.band-option i {
  width: 27px;
  height: 27px;
  border-radius: 4px;
}

.band-option i.rgb {
  background: linear-gradient(135deg, #bd7255, #74915d 52%, #687fa8);
}

.band-option i.false-color {
  background: linear-gradient(135deg, #b33d52, #da8175 52%, #557a6a);
}

.band-option i.ndvi {
  background: linear-gradient(135deg, #b85b43, #e1c761 45%, #3d935e);
}

.band-option strong,
.processing-status strong {
  font-size: 9px;
}

.processing-status {
  gap: 8px;
  padding: 10px;
  margin: 12px;
  color: #3d825d;
  background: #eff7f2;
  border: 1px solid #d9e9df;
  border-radius: 6px;
}
</style>
