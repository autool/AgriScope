<script setup lang="ts">
import { computed } from 'vue'

import type { AreaGroupItem } from '@/types/workbench'

interface StatisticsRankingTableProps {
  items: AreaGroupItem[]
  title: string
}

const props = defineProps<StatisticsRankingTableProps>()
const showCodeComputed = computed<boolean>(() => (
  props.items.some((item) => Boolean(item.code))
))
const showParentComputed = computed<boolean>(() => (
  props.items.some((item) => Boolean(item.parent_label))
))
</script>

<template>
  <div class="ranking-table">
    <a-empty
      v-if="props.items.length === 0"
      :description="`${props.title}暂无可统计数据`"
    />
    <table v-else>
      <thead>
        <tr>
          <th>排名</th>
          <th v-if="showCodeComputed">编码</th>
          <th>{{ props.title }}</th>
          <th v-if="showParentComputed">上级区域</th>
          <th>图斑数</th>
          <th>面积（公顷）</th>
          <th>面积（亩）</th>
          <th>占比</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(item, index) in props.items" :key="item.code || item.label">
          <td>{{ index + 1 }}</td>
          <td v-if="showCodeComputed"><code>{{ item.code || '--' }}</code></td>
          <td><strong>{{ item.label }}</strong></td>
          <td v-if="showParentComputed">{{ item.parent_label || '--' }}</td>
          <td>{{ item.plot_count }}</td>
          <td>{{ item.area_ha }}</td>
          <td>{{ item.area_mu }}</td>
          <td>{{ item.percentage }}%</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.ranking-table { max-height: 390px; overflow: auto; border: 1px solid #e7ece9; border-radius: 5px; }
table { width: 100%; font-size: 9px; border-collapse: collapse; }
th { position: sticky; top: 0; z-index: 1; padding: 8px; color: #74827a; text-align: left; white-space: nowrap; background: #f4f7f5; }
td { padding: 8px; color: #536159; border-bottom: 1px solid #ebeeec; }
tbody tr:hover { background: #f8faf9; }
td strong { font-weight: 500; color: #2f4338; }
code { font-size: 8px; color: #4d705e; }
</style>
