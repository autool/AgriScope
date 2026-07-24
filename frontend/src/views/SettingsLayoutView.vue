<script setup lang="ts">
import {
  ApartmentOutlined,
  FormOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import type { Component } from 'vue'
import { useRoute } from 'vue-router'

interface SettingsTab {
  path: string
  title: string
  description: string
  icon: Component
}

const route = useRoute()
const settingsTabs: SettingsTab[] = [
  {
    path: '/settings/rules',
    title: '业务规则',
    description: '质量、外业与生产阈值',
    icon: SafetyCertificateOutlined,
  },
  {
    path: '/settings/fields',
    title: '地块字段',
    description: '自定义属性与模式版本',
    icon: FormOutlined,
  },
  {
    path: '/settings/workflow',
    title: '审核流程',
    description: '三级审核职责与项目成员',
    icon: ApartmentOutlined,
  },
]
</script>

<template>
  <section class="settings-layout">
    <header class="settings-heading">
      <SettingOutlined />
      <span>
        <small>PROJECT GOVERNANCE</small>
        <strong>项目规则与流程</strong>
        <em>按业务职责分区维护，规则变更由服务端版本化并保留审计</em>
      </span>
      <a-tag color="green">项目级治理</a-tag>
    </header>

    <nav class="settings-tabs" aria-label="规则配置子菜单">
      <router-link
        v-for="tab in settingsTabs"
        :key="tab.path"
        :to="tab.path"
        :class="{ active: route.path === tab.path }"
      >
        <component :is="tab.icon" />
        <span>
          <strong>{{ tab.title }}</strong>
          <small>{{ tab.description }}</small>
        </span>
      </router-link>
    </nav>

    <div class="settings-content">
      <router-view />
    </div>
  </section>
</template>

<style scoped lang="less">
.settings-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.settings-heading {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: 34px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 14px 20px;
  color: #397d59;
  background: #fff;
  border-bottom: 1px solid #dfe6e2;
}

.settings-heading > :first-child { font-size: 24px; }
.settings-heading span { display: flex; flex-direction: column; }
.settings-heading small { font-size: 8px; color: #89958f; letter-spacing: 0.8px; }
.settings-heading strong { font-size: 15px; color: #28362f; }
.settings-heading em { margin-top: 2px; font-size: 9px; font-style: normal; color: #66736c; }

.settings-tabs {
  display: flex;
  flex: 0 0 auto;
  gap: 6px;
  padding: 8px 16px;
  overflow-x: auto;
  background: #f8faf9;
  border-bottom: 1px solid #dfe6e2;
}

.settings-tabs a {
  display: grid;
  grid-template-columns: 20px minmax(120px, 1fr);
  gap: 8px;
  align-items: center;
  min-width: 210px;
  padding: 8px 10px;
  color: #66736c;
  text-decoration: none;
  background: #fff;
  border: 1px solid #e2e8e4;
  border-radius: 6px;
}

.settings-tabs a:hover { color: #2d694b; border-color: #b9d5c5; }
.settings-tabs a.active { color: #286144; background: #edf6f1; border-color: #8fbea5; }
.settings-tabs a > :first-child { font-size: 16px; }
.settings-tabs span { display: flex; flex-direction: column; }
.settings-tabs strong { font-size: 10px; }
.settings-tabs small { font-size: 8px; color: #88938d; }

.settings-content {
  flex: 1;
  min-height: 0;
  padding: 12px 16px 24px;
  overflow: auto;
  scrollbar-gutter: stable;
}

@media (max-width: 760px) {
  .settings-heading { grid-template-columns: 28px 1fr; padding: 12px 14px; }
  .settings-heading .ant-tag { display: none; }
  .settings-tabs { padding: 8px; }
  .settings-tabs a { min-width: 170px; }
  .settings-content { padding: 10px 8px 20px; }
}
</style>
