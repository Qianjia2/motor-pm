import { createRouter, createWebHistory } from 'vue-router'
import api from './api'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('./pages/LoginPage.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('./pages/DashboardPage.vue'),
    meta: { title: '项目驾驶舱' }
  },
  {
    path: '/projects',
    name: 'ProjectList',
    component: () => import('./pages/ProjectListPage.vue'),
    meta: { title: '项目列表' }
  },
  {
    path: '/projects/new',
    name: 'ProjectCreate',
    component: () => import('./pages/ProjectCreatePage.vue'),
    meta: { title: '新建项目', parent: '项目列表' }
  },
  {
    path: '/projects/:id',
    name: 'ProjectDetail',
    component: () => import('./pages/ProjectDetailPage.vue'),
    meta: { title: '项目详情', parent: '项目列表' }
  },
  {
    path: '/projects/:id/edit',
    name: 'ProjectEdit',
    component: () => import('./pages/ProjectCreatePage.vue'),
    meta: { title: '编辑项目', parent: '项目列表' }
  },
  {
    path: '/management-weekly',
    name: 'ManagementWeekly',
    component: () => import('./pages/ManagementWeeklyPage.vue'),
    meta: { title: '管理层周报' }
  },
  {
    path: '/tasks-milestones',
    name: 'TaskMilestones',
    component: () => import('./pages/TaskMilestonePage.vue'),
    meta: { title: '任务与里程碑' }
  },
  {
    path: '/gantt',
    name: 'Gantt',
    component: () => import('./pages/GanttPage.vue'),
    meta: { title: '甘特图' }
  },
  {
    path: '/milestones',
    name: 'Milestones',
    component: () => import('./pages/MilestonePage.vue'),
    meta: { title: '里程碑全景' }
  },
  {
    path: '/clients',
    name: 'Clients',
    component: () => import('./pages/ClientPage.vue'),
    meta: { title: '客户管理' }
  },
  {
    path: '/bom',
    name: 'BOM',
    component: () => import('./pages/BOMPage.vue'),
    meta: { title: 'BOM管理' }
  },
  {
    path: '/issue-risks',
    name: 'IssueRisks',
    component: () => import('./pages/IssueRiskPage.vue'),
    meta: { title: '问题风险管理' }
  },
  {
    path: '/phase-gate-review',
    name: 'PhaseGateReview',
    component: () => import('./pages/PhaseGateReviewPage.vue'),
    meta: { title: '阶段门评审' }
  },
  {
    path: '/product-tech',
    name: 'ProductTech',
    component: () => import('./pages/ProductTechPage.vue'),
  },
  {
    path: '/product-tech/:id',
    name: 'ProductDetail',
    component: () => import('./pages/ProductDetailPage.vue'),
    meta: { title: '产品技术库' }
  },
  {
    path: '/knowledge',
    name: 'Knowledge',
    component: () => import('./pages/KnowledgePage.vue'),
    meta: { title: '知识库' }
  },
  {
    path: '/resources',
    name: 'Resources',
    component: () => import('./pages/ResourcePage.vue'),
    meta: { title: '资源管理', adminOnly: true, module: 'users' }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('./pages/SettingsPage.vue'),
    meta: { title: '系统设置', adminOnly: true, module: 'settings' }
  },
  {
    path: '/audit-logs',
    name: 'AuditLogs',
    component: () => import('./pages/AuditLogPage.vue'),
    meta: { title: '操作审计', adminOnly: true, module: 'audit_logs' }
  },
  {
    path: '/my-work',
    name: 'MyWork',
    component: () => import('./pages/MyWorkPage.vue'),
    meta: { title: '我的工作台' }
  },
  {
    // 跨项目的项目工作流。别叫「我的工作台」——/my-work 已经占了这个名字,
    // 两个同名入口会让人分不清哪个是哪个。
    path: '/project-workflow',
    name: 'ProjectWorkflowPage',
    component: () => import('./pages/WorkflowPage.vue'),
    meta: { title: '项目工作流' }
  },
  {
    path: '/training',
    name: 'Training',
    component: () => import('./pages/TrainingPage.vue'),
    meta: { title: '培训学习' }
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('./pages/ReportsPage.vue'),
    meta: { title: '报表中心' }
  },
  {
    path: '/ai',
    name: 'AI',
    component: () => import('./pages/AIPage.vue'),
    meta: { title: 'AI 助手' }
  },
  {
    path: '/portal/:code',
    name: 'Portal',
    component: () => import('./pages/PortalPage.vue'),
    meta: { title: '客户门户', public: true }
  },
  {
    path: '/kb/chat/:token',
    name: 'PublicChat',
    component: () => import('./pages/PublicChatPage.vue'),
    meta: { title: '智能问答', public: true }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// Auth guard (v2 JWT)
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('access_token')
  if (to.meta.public) {
    return next()  // Always allow public pages (kb chat, portal, etc.)
  }
  if (!token) {
    return next('/login')
  }
  if (to.meta.adminOnly) {
    let user = null
    try { user = JSON.parse(localStorage.getItem('user') || 'null') } catch {}
    if (user && user.role === 'admin') return next()
    // 非 admin：按 meta.module 的查看权限判断（默认 users）
    try {
      const mp = JSON.parse(localStorage.getItem('my_permissions') || 'null') || {}
      const perms = (mp && mp.permissions) || mp || {}
      const v = perms[to.meta.module || 'users']
      const ok = v && typeof v === 'object' ? v.view === true
        : ['view', 'edit', 'admin'].includes(typeof v === 'string' ? v : 'none')
      if (ok) return next()
    } catch {}
    return next('/my-work')
  }
  next()
})

// 培训实操痕迹:登录用户进入模块页面时静默上报一次访问(防抖 5 分钟,失败忽略)。
// 用于校验培训任务提交前是否确实进入过关联模块。
let lastVisit = { path: '', at: 0 }
router.afterEach((to) => {
  const token = localStorage.getItem('access_token')
  if (!token || to.meta.public) return
  const path = to.matched[0]?.path || to.path
  if (path === '/') return
  const now = Date.now()
  if (lastVisit.path === path && now - lastVisit.at < 5 * 60 * 1000) return
  lastVisit = { path, at: now }
  api.post('/training/tasks/visit', { module_path: path }).catch(() => {})
})

export default router
