<script setup lang="ts">
import { useLayoutStore } from '@/store/layoutStore'

const layoutStore = useLayoutStore()
</script>

<template>
  <a-drawer
    :open="layoutStore.preferencesDrawerOpenRef"
    title="界面与布局设置"
    :width="372"
    placement="right"
    @close="layoutStore.closePreferences()"
  >
    <div class="preference-intro">
      设置会自动保存在当前浏览器，仅影响界面布局，不改变业务数据。
    </div>

    <section class="preference-section">
      <h3>内容布局</h3>
      <div class="preference-row">
        <span><strong>内容宽度</strong><small>宽屏适合地图，居中适合表单和报告</small></span>
        <a-segmented
          :value="layoutStore.preferencesRef.app.contentMode"
          :options="[
            { label: '宽屏', value: 'wide' },
            { label: '居中', value: 'boxed' },
          ]"
          @change="(value: 'wide' | 'boxed') => layoutStore.updatePreferences({ app: { contentMode: value } })"
        />
      </div>
      <div class="preference-row">
        <span><strong>信息密度</strong><small>紧凑模式减少工作区内边距</small></span>
        <a-segmented
          :value="layoutStore.preferencesRef.app.density"
          :options="[
            { label: '舒适', value: 'comfortable' },
            { label: '紧凑', value: 'compact' },
          ]"
          @change="(value: 'comfortable' | 'compact') => layoutStore.updatePreferences({ app: { density: value } })"
        />
      </div>
    </section>

    <section class="preference-section">
      <h3>导航与标签页</h3>
      <div class="preference-row">
        <span><strong>折叠侧边栏</strong><small>保留图标，扩大业务工作区</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.sidebar.collapsed"
          @change="(value: boolean) => layoutStore.updatePreferences({ sidebar: { collapsed: value } })"
        />
      </div>
      <div class="preference-row">
        <span><strong>多标签页</strong><small>保留已访问业务模块并快速切换</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.tabbar.enabled"
          @change="(value: boolean) => layoutStore.updatePreferences({ tabbar: { enabled: value } })"
        />
      </div>
      <div class="preference-row">
        <span><strong>持久化标签页</strong><small>刷新浏览器后恢复已打开页面</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.tabbar.persist"
          @change="(value: boolean) => layoutStore.updatePreferences({ tabbar: { persist: value } })"
        />
      </div>
      <div class="preference-row">
        <span><strong>页面状态缓存</strong><small>切换模块时保留筛选和滚动位置</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.tabbar.keepAlive"
          @change="(value: boolean) => layoutStore.updatePreferences({ tabbar: { keepAlive: value } })"
        />
      </div>
    </section>

    <section class="preference-section">
      <h3>工作区</h3>
      <div class="preference-row">
        <span><strong>显示工作区标题</strong><small>展示任务状态、编号和快捷操作</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.header.workspaceVisible"
          @change="(value: boolean) => layoutStore.updatePreferences({ header: { workspaceVisible: value } })"
        />
      </div>
      <div class="preference-row">
        <span><strong>页面过渡</strong><small>使用短时淡入滑动，不影响地图相机</small></span>
        <a-switch
          :checked="layoutStore.preferencesRef.transition.enabled"
          @change="(value: boolean) => layoutStore.updatePreferences({ transition: { enabled: value } })"
        />
      </div>
    </section>

    <a-button block @click="layoutStore.resetPreferences()">恢复默认布局</a-button>
  </a-drawer>
</template>

<style scoped lang="less">
.preference-intro {
  padding: 10px 12px;
  margin-bottom: 18px;
  font-size: 11px;
  line-height: 18px;
  color: #68766f;
  background: #f3f7f5;
  border: 1px solid #e0e8e3;
  border-radius: 7px;
}

.preference-section {
  padding-bottom: 8px;
  margin-bottom: 18px;
  border-bottom: 1px solid #e5e9e7;
}

.preference-section h3 {
  margin: 0 0 7px;
  font-size: 12px;
  color: #263d32;
}

.preference-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 54px;
}

.preference-row > span {
  display: flex;
  flex-direction: column;
}

.preference-row strong { font-size: 11px; font-weight: 500; }
.preference-row small { margin-top: 2px; font-size: 9px; color: #89948e; }
</style>
