<script setup lang="ts">
import type { PlotProperties } from '@/types/workbench'

withDefaults(defineProps<{
  dataSource?: PlotProperties[]
  loading?: boolean
}>(), {
  dataSource: () => [],
  loading: false,
})

const emit = defineEmits<{ 'fly-to': [record: PlotProperties] }>()

const columns = [
  { title: '图斑编号', dataIndex: 'plot_code', key: 'plot_code', width: 140 },
  { title: '权属村', dataIndex: 'owner_village', key: 'owner_village', width: 140 },
  { title: '面积（公顷）', dataIndex: 'area_ha', key: 'area_ha', width: 130 },
]

const rowEvents = (record: PlotProperties) => ({
  onClick: () => emit('fly-to', record),
})
</script>

<template>
  <section class="result-panel">
    <div class="result-heading">
      <span>查询结果</span>
      <span class="result-count">共 {{ dataSource.length }} 条</span>
    </div>
    <a-table
      row-key="plot_code"
      size="small"
      :columns="columns"
      :data-source="dataSource"
      :loading="loading"
      :custom-row="rowEvents"
      :pagination="{ pageSize: 10, showSizeChanger: false, size: 'small' }"
      :scroll="{ y: 220 }"
    />
  </section>
</template>

<style scoped lang="less">
.result-panel {
  height: 100%;
  padding: 14px 16px 0;
  background: #fff;
  border-top: 1px solid #e5ece7;
}

.result-heading {
  display: flex;
  align-items: baseline;
  margin-bottom: 10px;
  font-size: 15px;
  font-weight: 600;
}

.result-count {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 400;
  color: #849188;
}

:deep(.ant-table-row) {
  cursor: pointer;
}

:deep(.ant-table-row:hover td) {
  background: #eff8f2 !important;
}
</style>
