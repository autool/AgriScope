<script setup lang="ts">
import {
  ApartmentOutlined,
  BorderOutlined,
  CompressOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { computed, ref, watch } from 'vue'

import type { FarmlandHierarchyNode } from '@/store/layerStore'

interface LayerHierarchyCatalogProps {
  farmlandHierarchy: FarmlandHierarchyNode[]
  administrativeHierarchy: FarmlandHierarchyNode[]
  farmlandCount: number
  landClassCounts: Record<string, number>
}

const props = defineProps<LayerHierarchyCatalogProps>()
const emit = defineEmits<{
  selectNode: [node: FarmlandHierarchyNode]
}>()

const catalogTypeRef = ref<'farmland' | 'boundary'>('farmland')
const searchKeywordRef = ref<string>('')
const expandedKeysRef = ref<string[]>([])
const expansionLevelRef = ref<'collapsed' | 'city' | 'district' | 'plot'>('plot')

const activeHierarchyComputed = computed<FarmlandHierarchyNode[]>(() => (
  catalogTypeRef.value === 'farmland'
    ? props.farmlandHierarchy
    : props.administrativeHierarchy
))

const cityCountComputed = computed<number>(
  () => props.administrativeHierarchy[0]?.children?.length || 0,
)
const districtCountComputed = computed<number>(() => (
  props.administrativeHierarchy[0]?.children?.reduce(
    (total, city) => total + (city.children?.length || 0),
    0,
  ) || 0
))
const coveredDistrictCountComputed = computed<number>(() => (
  props.farmlandHierarchy[0]?.children?.reduce(
    (total, city) => total + (city.children?.filter((district) => district.count > 0).length || 0),
    0,
  ) || 0
))
const wellCoveredDistrictCountComputed = computed<number>(() => (
  props.farmlandHierarchy[0]?.children?.reduce(
    (total, city) => total + (city.children?.filter((district) => district.count >= 20).length || 0),
    0,
  ) || 0
))
const landClassCountsComputed = computed<Record<string, number>>(
  () => props.landClassCounts,
)
const landClassSummaryComputed = computed<string>(() => (
  ['耕地', '园地', '林地', '草地', '水域', '建设用地']
    .map((landClass) => `${landClass} ${landClassCountsComputed.value[landClass] || 0}`)
    .join(' · ')
))

/**
 * 递归过滤目录节点，并保留命中节点的完整祖先链。
 * Args:
 *   nodes: 当前层级节点。
 *   keyword: 已标准化的小写搜索词。
 * Returns:
 *   FarmlandHierarchyNode[]: 搜索命中的分级目录。
 */
const filterHierarchy = (
  nodes: FarmlandHierarchyNode[],
  keyword: string,
): FarmlandHierarchyNode[] => nodes.flatMap((node) => {
  const children = filterHierarchy(node.children || [], keyword)
  const selfMatched = node.title.toLocaleLowerCase().includes(keyword)
    || node.plotCode?.toLocaleLowerCase().includes(keyword)
  if (!selfMatched && children.length === 0) return []
  return [{ ...node, children: selfMatched ? node.children : children }]
})

const visibleHierarchyComputed = computed<FarmlandHierarchyNode[]>(() => {
  const keyword = searchKeywordRef.value.trim().toLocaleLowerCase()
  if (!keyword) return activeHierarchyComputed.value
  return filterHierarchy(activeHierarchyComputed.value, keyword)
})

/**
 * 收集省级和地级节点，使县区层级无需逐市点击即可直接看到。
 * Args:
 *   nodes: 分级目录节点。
 * Returns:
 *   string[]: 应展开的省、市节点键。
 */
const collectExpandedKeys = (
  nodes: FarmlandHierarchyNode[],
  targetLevel: 'city' | 'district' | 'plot',
): string[] => {
  const keys: string[] = []
  const visit = (items: FarmlandHierarchyNode[]): void => {
    items.forEach((node) => {
      const shouldExpand = node.level === 'province'
        || (targetLevel !== 'city' && node.level === 'city')
        || (targetLevel === 'plot' && node.level === 'district' && Boolean(node.children?.length))
      if (shouldExpand) keys.push(node.key)
      if (node.children) visit(node.children)
    })
  }
  visit(nodes)
  return keys
}

/**
 * 搜索时展开所有命中路径，确保县区或图斑结果可见。
 * Args:
 *   nodes: 搜索过滤后的目录节点。
 * Returns:
 *   string[]: 包含子节点的全部目录键。
 */
const collectExpandableKeys = (nodes: FarmlandHierarchyNode[]): string[] => {
  const keys: string[] = []
  const visit = (items: FarmlandHierarchyNode[]): void => {
    items.forEach((node) => {
      if (node.children?.length) {
        keys.push(node.key)
        visit(node.children)
      }
    })
  }
  visit(nodes)
  return keys
}

const expandToLevel = (targetLevel: 'city' | 'district' | 'plot'): void => {
  expansionLevelRef.value = targetLevel
  expandedKeysRef.value = collectExpandedKeys(activeHierarchyComputed.value, targetLevel)
}

const collapseAll = (): void => {
  expansionLevelRef.value = 'collapsed'
  expandedKeysRef.value = []
}

const getLevelLabel = (level: FarmlandHierarchyNode['level']): string => ({
  province: '省域',
  city: '地级',
  district: '县区',
  plot: '地块',
})[level]

const getCountLabel = (node: FarmlandHierarchyNode): string => {
  if (node.level === 'plot') {
    return [node.landClass, node.plotCode].filter(Boolean).join(' · ')
  }
  if (catalogTypeRef.value === 'boundary') {
    if (node.level === 'province') return `${node.count} 个地级区域`
    if (node.level === 'city') return `${node.count} 个县区`
    return node.key.split(':')[1] || ''
  }
  return node.count > 0 ? `${node.count} 个真实小地块` : '暂无公开地块'
}

const handleSelect = (selectedKeys: Array<string | number>): void => {
  const selectedKey = String(selectedKeys[0] || '')
  if (!selectedKey) return
  const findNode = (nodes: FarmlandHierarchyNode[]): FarmlandHierarchyNode | null => {
    for (const node of nodes) {
      if (node.key === selectedKey) return node
      const matched = findNode(node.children || [])
      if (matched) return matched
    }
    return null
  }
  const node = findNode(activeHierarchyComputed.value)
  if (node) emit('selectNode', node)
}

watch(
  [
    catalogTypeRef,
    () => props.farmlandCount,
    cityCountComputed,
    districtCountComputed,
  ],
  () => {
    searchKeywordRef.value = ''
    if (catalogTypeRef.value === 'farmland') {
      expandToLevel('plot')
      return
    }
    expandToLevel('district')
  },
  { flush: 'post', immediate: true },
)

watch(searchKeywordRef, (keyword) => {
  if (keyword.trim()) {
    expandedKeysRef.value = collectExpandableKeys(visibleHierarchyComputed.value)
  }
})
</script>

<template>
  <section class="hierarchy-catalog">
    <header class="catalog-overview">
      <span>
        <small>空间资源目录</small>
        <strong>{{ props.farmlandCount.toLocaleString('zh-CN') }} 个可追溯真实地块</strong>
      </span>
      <em :title="landClassSummaryComputed">OSM · 6 类</em>
    </header>

    <div class="coverage-line" aria-label="空间数据层级统计">
      <span><b>1</b>省</span><i>›</i>
      <span><b>{{ cityCountComputed }}</b>地级</span><i>›</i>
      <span><b>{{ districtCountComputed }}</b>县区</span><i>›</i>
      <span><b>{{ coveredDistrictCountComputed }}</b>作业区</span>
      <em>{{ wellCoveredDistrictCountComputed }} 县区 ≥ 20 块</em>
    </div>

    <div class="catalog-switch">
      <button
        :class="{ active: catalogTypeRef === 'farmland' }"
        @click="catalogTypeRef = 'farmland'"
      >
        <BorderOutlined />地块目录
      </button>
      <button
        :class="{ active: catalogTypeRef === 'boundary' }"
        @click="catalogTypeRef = 'boundary'"
      >
        <ApartmentOutlined />行政区划
      </button>
    </div>

    <div class="catalog-search">
      <a-input
        v-model:value="searchKeywordRef"
        allow-clear
        size="small"
        placeholder="搜索行政区或地块编号"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>

    <div class="catalog-toolbar">
      <span>
        {{ catalogTypeRef === 'farmland' ? '省 / 地级 / 县区 / 地块' : '省 / 地级 / 县区' }}
      </span>
      <div class="level-switch" aria-label="目录展开层级">
        <button title="全部折叠" @click="collapseAll">
          <CompressOutlined />
        </button>
        <button
          :class="{ active: expansionLevelRef === 'city' }"
          @click="expandToLevel('city')"
        >
          地级
        </button>
        <button
          :class="{ active: expansionLevelRef === 'district' }"
          @click="expandToLevel('district')"
        >
          县区
        </button>
        <button
          v-if="catalogTypeRef === 'farmland'"
          :class="{ active: expansionLevelRef === 'plot' }"
          @click="expandToLevel('plot')"
        >
          地块
        </button>
      </div>
    </div>

    <div class="tree-shell">
      <a-tree
        v-model:expanded-keys="expandedKeysRef"
        block-node
        show-line
        :auto-expand-parent="false"
        :height="560"
        :tree-data="visibleHierarchyComputed"
        :virtual="true"
        @select="handleSelect"
      >
        <template #title="node">
          <span
            class="node-title"
            :class="[
              `level-${node.level}`,
              { empty: node.level === 'district' && node.count === 0 },
            ]"
          >
            <i :class="node.level">{{ getLevelLabel(node.level) }}</i>
            <span class="node-copy">
              <strong>{{ node.title }}</strong>
              <small>{{ getCountLabel(node) }}</small>
            </span>
          </span>
        </template>
      </a-tree>

      <a-empty
        v-if="visibleHierarchyComputed.length === 0"
        description="没有匹配的层级节点"
      />
    </div>
  </section>
</template>

<style scoped lang="less">
.hierarchy-catalog {
  padding: 0 10px 12px;
}

.catalog-overview {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 40px;
  padding: 7px 9px;
  margin-bottom: 5px;
  background: #f7f9f8;
  border: 1px solid #e3e8e5;
  border-radius: 6px;
}

.catalog-overview > span {
  display: flex;
  flex-direction: column;
}

.catalog-overview small {
  font-size: 8px;
  color: #8a958f;
}

.catalog-overview strong {
  font-size: 11px;
  color: #294b39;
}

.catalog-overview em {
  padding: 3px 6px;
  font-style: normal;
  font-size: 8px;
  color: #496757;
  background: #e9f0ec;
  border-radius: 4px;
}

.coverage-line {
  display: flex;
  gap: 4px;
  align-items: center;
  min-height: 25px;
  padding: 0 3px;
  margin-bottom: 6px;
  font-size: 8px;
  color: #718078;
}

.coverage-line span {
  display: inline-flex;
  gap: 2px;
  align-items: baseline;
}

.coverage-line b {
  font-size: 10px;
  font-weight: 600;
  color: #356047;
}

.coverage-line > i {
  font-style: normal;
  color: #b1bbb5;
}

.coverage-line em {
  margin-left: auto;
  font-style: normal;
  color: #78867e;
}

.catalog-switch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 6px;
  padding: 3px;
  background: #f1f4f2;
  border-radius: 5px;
}

.catalog-search {
  margin-bottom: 3px;
}

.catalog-switch button {
  display: flex;
  gap: 5px;
  align-items: center;
  justify-content: center;
  min-height: 25px;
  font-size: 10px;
  color: #718078;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 4px;
}

.catalog-switch button.active {
  color: #245a3f;
  font-weight: 600;
  background: #fff;
  box-shadow: 0 1px 2px rgb(33 62 46 / 9%);
}

.catalog-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 30px;
  font-size: 9px;
  color: #87938c;
}

.catalog-toolbar > span b {
  color: #4c8062;
}

.catalog-toolbar .level-switch {
  display: flex;
  gap: 2px;
  padding: 2px;
  background: #eef3f0;
  border-radius: 4px;
}

.catalog-toolbar button {
  min-width: 24px;
  padding: 2px 4px;
  font-size: 9px;
  color: #397356;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 3px;
}

.catalog-toolbar button:first-child {
  min-width: 22px;
  color: #748078;
}

.catalog-toolbar button.active {
  font-weight: 600;
  color: #245a3f;
  background: #fff;
}

:deep(.ant-input-affix-wrapper) {
  font-size: 10px;
}

.tree-shell {
  overflow: hidden;
  background: #fff;
  border: 1px solid #e6eae8;
  border-radius: 5px;
}

:deep(.ant-tree) {
  padding: 3px 2px 6px;
  font-size: 10px;
  background: transparent;
}

:deep(.ant-tree .ant-tree-treenode) {
  min-height: 30px;
  padding: 1px 0;
}

:deep(.ant-tree .ant-tree-node-content-wrapper) {
  width: calc(100% - 4px);
  min-height: 28px;
  padding: 2px 4px;
}

.node-title {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
  width: 100%;
  padding: 2px 5px 2px 2px;
  background: transparent;
  border-radius: 4px;
}

.node-title.level-city {
  background: #f3f7f5;
}

.node-title.level-district {
  background: #fafbfa;
}

.node-title.level-plot {
  background: transparent;
}

.node-title > i {
  display: grid;
  flex: 0 0 27px;
  width: 27px;
  height: 18px;
  font-style: normal;
  font-size: 8px;
  color: #fff;
  background: #4c8062;
  border-radius: 4px;
  place-items: center;
}

.node-title > i.city {
  color: #38634d;
  background: #dbe9e1;
}

.node-title > i.district {
  color: #65736c;
  background: #edf1ef;
}

.node-title > i.plot {
  color: #7b642e;
  background: #f2ead7;
}

.node-copy {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-direction: column;
}

.node-title strong,
.node-title small {
  overflow: hidden;
  line-height: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-title strong {
  font-size: 10px;
  font-weight: 500;
  color: #2f3934;
}

.node-title small {
  font-size: 8px;
  color: #8b9690;
}

.node-title.empty {
  opacity: 0.62;
}
</style>
