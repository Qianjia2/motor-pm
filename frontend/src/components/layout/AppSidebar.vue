<template>
  <div class="sidebar-logo">
    <div class="logo-icon">
      <img src="/logo.png" alt="麦科斯韦" style="width:32px;height:32px;border-radius:6px" />
    </div>
    <div class="logo-text">
      <div class="logo-title">麦科斯韦研发项目管理平台</div>
      <div class="logo-sub">Maxwell R&D Project Management</div>
    </div>
  </div>

  <nav class="sidebar-nav">
    <div class="nav-section-label">主菜单</div>
    <a v-for="item in mainNav" :key="item.path" :href="'#'+item.path" class="nav-item"
       :class="{active: isActive(item)}" @click.prevent="navigate(item)">
      <el-icon><component :is="item.icon" /></el-icon>
      <span>{{ item.label }}</span>
      <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
    </a>

    <template v-for="group in adminGroups" :key="group.label">
      <template v-if="group.items.length > 0">
      <div class="nav-section-label" style="margin-top:16px">{{ group.label }}</div>
      <a v-for="item in group.items" :key="item.path + (item.matchQuery?.type || '')" :href="'#'+item.path" class="nav-item"
         v-show="!item.adminOnly || auth.isAdmin"
         :class="{active: isActive(item)}" @click.prevent="navigate(item)">
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </a>
    </template>
    </template>
  </nav>

  <div class="sidebar-footer">
    <div class="footer-version">v2.0 · 麦科斯韦研发项目管理平台</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth.js'
import { currentProjectType } from '../../stores/projectType.js'
import {
  HomeFilled, DataAnalysis, List, Plus, Timer, User, Setting,
  DocumentChecked, ChatDotRound, Document, FolderOpened, Stamp, Reading, Monitor,
  Connection
} from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const alertCount = computed(() => auth.alerts || 0)

const mainNav = [
  { path: '/my-work', label: '我的工作台', icon: HomeFilled, match: '/my-work', module: 'my_work' },
  // 复用「项目管理」的权限:工作流本来就是项目的东西,单独开一个权限键
  // 会让它默认对所有人不可见(缺失模块会被补成全 false),还得迁移一遍权限矩阵
  { path: '/project-workflow', label: '项目工作流', icon: Connection, match: '/project-workflow', module: 'projects' },
  { path: '/', label: '项目驾驶舱', icon: DataAnalysis, match: '/', module: 'dashboard' },
  { path: '/management-weekly', label: '管理层周报', icon: Document, match: '/management-weekly', module: 'mgmt_weekly' },
  { path: '/training', label: '培训学习', icon: Reading, match: '/training' },
].filter(it => !it.module || auth.canView(it.module))

const adminGroups = [
  {
    label: '产品技术库',
    items: [
      { path: '/product-tech', label: '产品技术库', icon: FolderOpened, match: '/product-tech', module: 'product_tech' },
      { path: '/bom', label: 'BOM管理', icon: FolderOpened, match: '/bom', module: 'bom' },
    ].filter(it => !it.module || auth.canView(it.module)),
  },
  {
    label: '项目管理',
    items: [
      { path: '/projects', label: '系统集成开发项目台账', icon: List, match: '/projects', matchQuery: { type: undefined }, module: 'projects' },
      { path: '/projects', label: '软件研发项目台账', icon: Monitor, match: '/projects', matchQuery: { type: 'software' }, query: { type: 'software' }, module: 'projects' },
      { path: '/tasks-milestones', label: '任务与里程碑', icon: Timer, match: '/tasks-milestones', module: 'tasks_milestones' },
      { path: '/issue-risks', label: '问题风险管理', icon: DocumentChecked, match: '/issue-risks', module: 'issue_risks' },
      { path: '/phase-gate-review', label: '阶段门评审', icon: Stamp, match: '/phase-gate-review', module: 'phase_gate' },
    ].filter(it => !it.module || auth.canView(it.module)),
  },
  {
    label: '报告与AI',
    items: [
      { path: '/reports', label: '报告中心', icon: Document, match: '/reports', module: 'reports' },
      { path: '/ai', label: 'AI 助手', icon: ChatDotRound, match: '/ai', module: 'ai' },
    ].filter(it => !it.module || auth.canView(it.module)),
  },
  {
    label: '系统管理',
    items: [
      { path: '/knowledge', label: '知识库', icon: FolderOpened, match: '/knowledge', module: 'knowledge' },
      { path: '/clients', label: '客户管理', icon: User, match: '/clients', module: 'clients' },
      { path: '/resources', label: '资源管理', icon: User, match: '/resources', module: 'users' },
      { path: '/audit-logs', label: '操作审计', icon: DocumentChecked, match: '/audit-logs', module: 'audit_logs', adminOnly: true },
      { path: '/settings', label: '系统设置', icon: Setting, match: '/settings', module: 'settings', adminOnly: true },
    ].filter(it => !it.module || auth.canView(it.module)),
  },
]

function isActive(item) {
  const pattern = item.match || item.path
  if (pattern === '/') return route.path === '/'
  if (!route.path.startsWith(pattern)) return false
  // 同一路径按 query 区分高亮(系统集成开发项目台账 vs 软件研发项目)
  if (item.matchQuery !== undefined) {
    // 详情/编辑页(/projects/:id, /projects/:id/edit)无 query:按当前项目类型高亮
    if (route.path.startsWith('/projects/') && route.params.id) {
      const have = currentProjectType.value || 'hardware'
      const want = item.matchQuery.type || 'hardware'
      return have === want
    }
    const have = route.query.type || undefined
    const want = item.matchQuery.type
    return have === want
  }
  return true
}

function navigate(item) {
  router.push(item.query ? { path: item.path, query: item.query } : item.path)
}
</script>

<style scoped>
.sidebar-logo {
  display:flex; align-items:center; gap:10px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--border);
}
.logo-icon { flex-shrink:0; }
.logo-title { font-size:12px; font-weight:700; color:var(--text); line-height:1.4; white-space:nowrap; }
.logo-sub { font-size:10px; color:var(--text-muted); letter-spacing:.5px; }

.sidebar-nav { flex:1; overflow-y:auto; padding:12px 12px; }

.nav-section-label {
  font-size:11px; color:var(--text-muted);
  padding: 8px 12px 6px; font-weight:600; letter-spacing:.5px;
  text-transform: uppercase;
}

.nav-item {
  display:flex; align-items:center; gap:10px;
  padding: 9px 12px; margin:1px 0;
  border-radius: var(--radius-sm);
  font-size:13px; color:var(--text-secondary);
  text-decoration:none; cursor:pointer;
  transition: all .15s; position:relative;
}
.nav-item:hover {
  background: var(--bg);
  color: var(--text);
}
.nav-item.active {
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 600;
}
.nav-item .el-icon { font-size:18px; flex-shrink:0; }

.nav-badge {
  margin-left:auto;
  background: var(--danger); color:#fff;
  font-size:10px; padding:1px 6px; border-radius:8px;
  font-weight:600; min-width:18px; text-align:center;
}

.sidebar-footer {
  padding:12px 20px; border-top:1px solid var(--border);
}
.footer-version {
  font-size:11px; color:var(--text-muted); text-align:center;
}
</style>
