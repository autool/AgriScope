import { createRouter, createWebHistory } from 'vue-router'

import WorkbenchLayout from '@/layouts/WorkbenchLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: WorkbenchLayout,
      redirect: '/interpretation',
      children: [
        {
          path: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: {
            title: '项目总览',
            description: '全流程进度、质量风险与任务状态',
            keepAlive: true,
          },
        },
        {
          path: 'production',
          component: () => import('@/views/ProductionView.vue'),
          meta: {
            title: '生产调度',
            description: '多源数据、生产批次、县区分包与进度协调',
            keepAlive: true,
          },
        },
        {
          path: 'change-detection',
          component: () => import('@/views/ChangeDetectionView.vue'),
          meta: {
            title: '多时相变化检测',
            description: '前后时相影像、候选变化与人工判读闭环',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'imagery',
          component: () => import('@/views/ImageryView.vue'),
          meta: {
            title: '影像预处理',
            description: '定标、校正、裁剪与波段产品',
            keepAlive: true,
          },
        },
        {
          path: 'interpretation',
          component: () => import('@/views/InterpretationView.vue'),
          meta: {
            title: '地块解译工作台',
            description: '边界矢量化与种植属性录入',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'statistics',
          component: () => import('@/views/StatisticsView.vue'),
          meta: {
            title: '面积统计分析',
            description: '地类、作物、村级与年度趋势',
            keepAlive: true,
          },
        },
        {
          path: 'thematic-maps',
          component: () => import('@/views/ThematicMapView.vue'),
          meta: {
            title: '专题制图',
            description: '真实影像产品、版式模板、批量 PNG/PDF 与校验清单',
            keepAlive: true,
          },
        },
        {
          path: 'disaster',
          component: () => import('@/views/DisasterView.vue'),
          meta: {
            title: '灾害与长势监测',
            description: '受灾斑块识别、分级与复核',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'monitoring-network',
          component: () => import('@/views/MonitoringNetworkView.vue'),
          meta: {
            title: '田间监测与病虫害预警',
            description: '真实监测站、设备遥测、故障闭环、模型复核与告警送达',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'uav',
          component: () => import('@/views/UavView.vue'),
          meta: {
            title: '无人机任务',
            description: '航空器资质、飞行任务、实体成果、空间疑点与审核门禁',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'field',
          component: () => import('@/views/FieldVerificationView.vue'),
          meta: {
            title: '内外业联动核查',
            description: '点斑匹配、偏差判断与疑点闭环',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'review',
          component: () => import('@/views/ReviewView.vue'),
          meta: {
            title: '成果审核',
            description: '内业自检、质检审核与甲方复核',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'supervision',
          component: () => import('@/views/SupervisionView.vue'),
          meta: {
            title: '独立项目监理',
            description: '真实抽样、过程检查、整改复检、县区评价与不可变报告',
            fullWidth: true,
            keepAlive: true,
          },
        },
        {
          path: 'delivery',
          component: () => import('@/views/DeliveryView.vue'),
          meta: {
            title: '成果验收交付',
            description: '成果包生成、校验、下载与归档',
            keepAlive: true,
          },
        },
        {
          path: 'assets',
          component: () => import('@/views/AssetsView.vue'),
          meta: {
            title: '影像文件库',
            description: '已上传栅格实体、文件校验和影像元数据',
            keepAlive: true,
          },
        },
        {
          path: 'service-sharing',
          component: () => import('@/views/ServiceSharingView.vue'),
          meta: {
            title: '数据共享服务',
            description: '服务注册、甲方审批、访问凭证、健康检查、调用审计与撤销',
            keepAlive: true,
          },
        },
        {
          path: 'settings',
          component: () => import('@/views/SettingsView.vue'),
          meta: {
            title: '规则配置',
            description: '质量阈值、审核流程与权限规则',
            keepAlive: true,
          },
        },
      ],
    },
  ],
})

export default router
