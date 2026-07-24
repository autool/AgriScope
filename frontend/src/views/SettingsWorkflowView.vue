<script setup lang="ts">
import {
  AuditOutlined,
  CheckCircleOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { storeToRefs } from 'pinia'
import { computed } from 'vue'

import { useUserStore } from '@/store/userStore'
import { useWorkbenchStore } from '@/store/workbenchStore'
import type { ProjectUser, UserRoleCode } from '@/types/workbench'

interface WorkflowStep {
  code: string
  title: string
  roleCode: UserRoleCode
  capability: string
  capabilityLabel: string
  description: string
}

const userStore = useUserStore()
const workbenchStore = useWorkbenchStore()
const { usersRef, loadingRef } = storeToRefs(userStore)

const workflowSteps: WorkflowStep[] = [
  {
    code: 'self_check',
    title: '内业自检',
    roleCode: 'interpreter',
    capability: 'review_self_check',
    capabilityLabel: '提交并审核内业自检',
    description: '校验完整质量批次和任务快照，通过后进入质检员审核。',
  },
  {
    code: 'quality_review',
    title: '质检员审核',
    roleCode: 'quality_inspector',
    capability: 'review_quality',
    capabilityLabel: '质检通过、退回或驳回',
    description: '检查质量问题闭环和成果一致性，通过后进入甲方复核。',
  },
  {
    code: 'client_review',
    title: '甲方复核',
    roleCode: 'client_reviewer',
    capability: 'review_client',
    capabilityLabel: '甲方最终复核',
    description: '复核未关闭问题和外业疑点，全部满足后完成任务。',
  },
]

const projectCodeComputed = computed<string>(() => workbenchStore.projectCodeComputed)
const activeUsersComputed = computed<ProjectUser[]>(() => (
  usersRef.value.filter((user) => user.status === 'active')
))
const stepUsers = (step: WorkflowStep): ProjectUser[] => (
  activeUsersComputed.value.filter((user) => (
    user.role_code === step.roleCode && user.capabilities.includes(step.capability)
  ))
)
</script>

<template>
  <div class="settings-workflow-view">
    <a-alert
      type="warning"
      show-icon
      message="审核顺序是服务端固定业务规则"
      description="此页面用于核对真实项目成员和能力，不提供伪配置开关；通过、退回、驳回均在成果审核模块执行并写入审计。"
    />

    <section class="workflow-card">
      <header>
        <span><AuditOutlined /><strong>三级审核链路</strong></span>
        <small>项目 {{ projectCodeComputed }} · 顺序不可跳级</small>
      </header>
      <a-spin :spinning="loadingRef">
        <div class="workflow-steps">
          <article v-for="(step, index) in workflowSteps" :key="step.code">
            <div class="step-index">{{ index + 1 }}</div>
            <div class="step-main">
              <h3>{{ step.title }}</h3>
              <p>{{ step.description }}</p>
              <span class="capability"><SafetyCertificateOutlined />{{ step.capabilityLabel }}</span>
            </div>
            <div class="step-users">
              <small>当前责任人</small>
              <template v-if="stepUsers(step).length">
                <span v-for="user in stepUsers(step)" :key="user.user_code">
                  <UserOutlined />
                  <strong>{{ user.display_name }}</strong>
                  <em>{{ user.user_code }}</em>
                </span>
              </template>
              <a-tag v-else color="red">缺少具备能力的启用成员</a-tag>
            </div>
            <CheckCircleOutlined v-if="stepUsers(step).length" class="step-ready" />
          </article>
        </div>
      </a-spin>
    </section>

    <section class="member-card">
      <header>
        <span><UserOutlined /><strong>项目成员与角色</strong></span>
        <small>{{ activeUsersComputed.length }} 名启用成员</small>
      </header>
      <div class="member-grid">
        <article v-for="user in usersRef" :key="user.user_code">
          <div>
            <strong>{{ user.display_name }}</strong>
            <small>{{ user.user_code }}</small>
          </div>
          <a-tag :color="user.status === 'active' ? 'green' : 'default'">
            {{ user.role_name }} · {{ user.status === 'active' ? '启用' : '停用' }}
          </a-tag>
          <p>{{ user.capabilities.length }} 项服务端能力</p>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped lang="less">
.settings-workflow-view { width: min(1040px, 100%); margin: 0 auto; }
.workflow-card, .member-card { padding: 18px 20px; margin-top: 10px; background: #fff; border: 1px solid #dfe6e2; border-radius: 8px; }
.workflow-card > header, .member-card > header { display: flex; align-items: center; justify-content: space-between; padding-bottom: 12px; border-bottom: 1px solid #e5e9e7; }
.workflow-card > header span, .member-card > header span { display: flex; gap: 7px; align-items: center; color: #397d59; }
.workflow-card header strong, .member-card header strong { font-size: 12px; color: #2d3a33; }
.workflow-card header small, .member-card header small { font-size: 8px; color: #89958f; }
.workflow-steps { display: grid; gap: 8px; margin-top: 12px; }
.workflow-steps article { position: relative; display: grid; grid-template-columns: 32px minmax(0, 1fr) 230px 20px; gap: 12px; align-items: center; padding: 13px; background: #f7f9f8; border: 1px solid #e5ebe7; border-radius: 6px; }
.step-index { display: grid; width: 28px; height: 28px; font-size: 11px; font-weight: 700; color: #fff; background: #397d59; border-radius: 50%; place-items: center; }
.step-main h3 { margin: 0; font-size: 11px; }
.step-main p { margin: 3px 0 6px; font-size: 9px; color: #6f7d75; }
.capability { display: inline-flex; gap: 5px; align-items: center; font-size: 8px; color: #397d59; }
.step-users { display: flex; flex-direction: column; gap: 4px; padding-left: 12px; border-left: 1px solid #dfe6e2; }
.step-users > small { font-size: 8px; color: #89958f; }
.step-users > span { display: grid; grid-template-columns: 14px auto 1fr; gap: 5px; align-items: center; font-size: 9px; }
.step-users em { overflow: hidden; font-size: 8px; font-style: normal; color: #89958f; text-overflow: ellipsis; white-space: nowrap; }
.step-ready { color: #45a273; }
.member-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 12px; }
.member-grid article { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 10px; align-items: center; padding: 11px 12px; background: #f7f9f8; border: 1px solid #e5ebe7; border-radius: 6px; }
.member-grid article > div { display: flex; flex-direction: column; }
.member-grid article strong { font-size: 10px; }
.member-grid article small, .member-grid article p { font-size: 8px; color: #89958f; }
.member-grid article p { grid-column: 1 / -1; margin: 0; }
@media (max-width: 820px) {
  .workflow-steps article { grid-template-columns: 32px 1fr 18px; }
  .step-users { grid-column: 2 / -1; padding: 8px 0 0; border-top: 1px solid #dfe6e2; border-left: 0; }
  .member-grid { grid-template-columns: 1fr; }
}
</style>
