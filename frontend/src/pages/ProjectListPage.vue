<template>
  <div class="ledger-page">
    <div class="page-head">
      <h2>{{ pageTitle }}</h2>
      <span class="head-sub">{{ typeFilter === 'software' ? '纯软件性能模块开发 · 不涉及硬件与样机试制' : '按阶段归类 · 项目列表 · 近期动态' }}</span>
    </div>

    <el-tabs v-model="tab" type="border-card">
      <!-- Tab 1: Project List -->
      <el-tab-pane label="项目列表" name="list">
        <!-- Stats overview -->
        <div class="stats-row">
          <div class="stat-card" @click="toggleStatusFilter('')">
            <div class="stat-num">{{ allProjects.length }}</div>
            <div class="stat-label">全部项目</div>
          </div>
          <div class="stat-card stat-normal" @click="toggleStatusFilter('normal')">
            <div class="stat-num">{{ countByStatus('normal') }}</div>
            <div class="stat-label">正常</div>
          </div>
          <div class="stat-card stat-risk" @click="toggleStatusFilter('at_risk')">
            <div class="stat-num">{{ countByStatus('at_risk') }}</div>
            <div class="stat-label">有风险</div>
          </div>
          <div class="stat-card stat-blocked" @click="toggleStatusFilter('blocked')">
            <div class="stat-num">{{ countByStatus('blocked') }}</div>
            <div class="stat-label">阻塞</div>
          </div>
          <div class="stat-card stat-avg">
            <div class="stat-num">{{ avgPct }}%</div>
            <div class="stat-label">平均完成率</div>
          </div>
        </div>

        <!-- Type filter -->
        <div class="phase-chips" style="margin-bottom:8px">
          <span class="chips-title">类型：</span>
          <span class="phase-chip" :class="{ active: typeFilter === '' }" @click="setType('')">全部项目</span>
          <span class="phase-chip" :class="{ active: typeFilter === 'hardware' }" @click="setType('hardware')">电机研发项目</span>
          <span class="phase-chip" :class="{ active: typeFilter === 'software' }" @click="setType('software')">软件研发项目</span>
        </div>

        <!-- Phase filter chips -->
        <div class="phase-chips">
          <span class="chips-title">阶段：</span>
          <span class="phase-chip" :class="{ active: phaseFilter === '' }" @click="phaseFilter = ''">全部</span>
          <span v-for="g in phaseGroups" :key="g.key" class="phase-chip" :class="{ active: phaseFilter === g.key }"
            @click="phaseFilter = g.key">
            {{ g.code }} {{ g.name }} <b>{{ g.projects.length }}</b>
          </span>
        </div>

        <!-- Toolbar -->
        <div class="page-toolbar">
          <div class="toolbar-left">
            <el-select v-model="searchField" size="default" style="width:110px">
              <el-option label="项目名称" value="name" />
              <el-option label="项目编号" value="code" />
              <el-option label="客户名称" value="client" />
            </el-select>
            <el-input v-model="search" placeholder="输入关键字..." size="default" style="width:200px" clearable :prefix-icon="Search" @input="filter" />
            <el-select v-model="sortBy" placeholder="排序" @change="filter" style="width:120px">
              <el-option label="默认" value="default" />
              <el-option label="完成率↓" value="pct_desc" />
              <el-option label="完成率↑" value="pct_asc" />
              <el-option label="截止日期" value="date" />
            </el-select>
          </div>
          <div class="toolbar-right">
            <span class="count-label">共 {{ filteredProjects.length }} 个项目</span>
            <el-button-group class="view-toggle">
              <el-button :type="viewMode === 'card' ? 'primary' : 'default'" size="default" title="平铺视图" @click="setView('card')">
                <el-icon><Grid /></el-icon>
              </el-button>
              <el-button :type="viewMode === 'table' ? 'primary' : 'default'" size="default" title="详细信息" @click="setView('table')">
                <el-icon><List /></el-icon>
              </el-button>
            </el-button-group>
            <el-button @click="exportProjects"><el-icon><Download /></el-icon>导出</el-button>
            <el-button type="primary" @click="$router.push('/projects/new')"><el-icon><Plus /></el-icon>新建项目</el-button>
          </div>
        </div>

        <div v-if="filteredProjects.length === 0" class="empty-state">
          <p style="font-size:15px;color:var(--text-secondary)">暂无项目</p>
        </div>

        <!-- 详细信息:按阶段分组表格 -->
        <div v-else-if="viewMode === 'table'">
          <div v-for="g in visibleGroups" :key="'t' + g.key" class="phase-group">
            <div class="phase-group-head" @click="toggleExpand(g.key)">
              <span class="group-arrow" :class="{ open: isExpanded(g.key) }">▶</span>
              <span class="group-name"><b v-if="g.code" class="group-code">{{ g.code }}</b>{{ g.name }}</span>
              <span class="group-count">{{ g.projects.length }} 个项目</span>
              <span v-if="g.projects.length" class="group-avg">平均进度 {{ g.avgPct }}%</span>
              <div class="group-progress">
                <el-progress :percentage="g.avgPct" :stroke-width="5" :show-text="false"
                  :color="g.avgPct >= 80 ? '#10b981' : g.avgPct >= 40 ? '#3b82f6' : '#f59e0b'" />
              </div>
            </div>
            <div v-show="isExpanded(g.key)" class="phase-group-body">
              <ProjectLedgerTable :projects="g.projects" @open="p => $router.push(`/projects/${p.id}`)"
                @clone="confirmClone" @delete="confirmDelete" />
            </div>
          </div>
        </div>

        <!-- 平铺视图:按阶段分组卡片 -->
        <div v-else>
          <div v-for="g in visibleGroups" :key="g.key" class="phase-group">
            <div class="phase-group-head" @click="toggleExpand(g.key)">
              <span class="group-arrow" :class="{ open: isExpanded(g.key) }">▶</span>
              <span class="group-name"><b v-if="g.code" class="group-code">{{ g.code }}</b>{{ g.name }}</span>
              <span class="group-count">{{ g.projects.length }} 个项目</span>
              <span v-if="g.projects.length" class="group-avg">平均进度 {{ g.avgPct }}%</span>
              <div class="group-progress">
                <el-progress :percentage="g.avgPct" :stroke-width="5" :show-text="false"
                  :color="g.avgPct >= 80 ? '#10b981' : g.avgPct >= 40 ? '#3b82f6' : '#f59e0b'" />
              </div>
            </div>
            <div v-show="isExpanded(g.key)" class="phase-group-body">
              <div v-if="g.projects.length === 0" class="group-empty">该阶段暂无项目</div>
              <div class="project-grid">
                <div v-for="proj in g.projects" :key="proj.id" class="proj-card" @click="$router.push(`/projects/${proj.id}`)">
                  <div class="proj-card-top">
                    <div class="proj-status-line">
                      <span class="dot" :class="'dot-' + res(proj.overall_status)"></span>
                      <span class="status-text">{{ statusLabel(proj.overall_status) }}</span>
                      <span v-if="proj.priority === 'P0'" class="tag tag-red" style="font-size:10px;margin-left:auto">P0</span>
                      <span v-else-if="proj.priority === 'P1'" class="tag tag-orange" style="font-size:10px;margin-left:auto">P1</span>
                    </div>
                    <div class="proj-name link" @click.stop="$router.push(`/projects/${proj.id}`)" title="进入项目详情">
                      {{ proj.name }}
                      <el-tag v-if="proj.project_type === 'software'" size="small" type="info" style="margin-left:6px">软件</el-tag>
                    </div>
                    <div class="proj-code">{{ proj.code }}</div>
                  </div>
                  <div class="proj-card-mid">
                    <div class="proj-meta">
                      <span style="font-size:12px;color:var(--text-muted)">{{ proj.planned_end_date || '无截止日期' }}</span>
                    </div>
                    <div class="pct-link" @click.stop="$router.push({ path: `/projects/${proj.id}`, query: { tab: 'milestones' } })" title="查看里程碑">
                      <el-progress :percentage="proj.completion_pct || 0" :stroke-width="6"
                        :color="proj.completion_pct >= 80 ? '#10b981' : proj.completion_pct >= 40 ? '#3b82f6' : '#f59e0b'" />
                    </div>
                  </div>
                  <div class="proj-card-bottom">
                    <div class="proj-owner">
                      <span v-if="proj.pm" class="pm-name link" title="团队成员" @click.stop="$router.push({ path: `/projects/${proj.id}`, query: { tab: 'team' } })">👤 {{ proj.pm }}</span>
                      <span v-if="proj.client?.name" class="client-name link" title="客户管理" @click.stop="$router.push('/clients')">{{ proj.client?.name }}</span>
                    </div>
                    <div class="proj-actions" @click.stop>
                      <el-button link size="small" @click="confirmClone(proj)" title="复制">📋</el-button>
                      <el-button link size="small" type="danger" @click="confirmDelete(proj)" title="删除">✕</el-button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 2: Activity Feed -->
      <el-tab-pane label="项目动态" name="activity">
        <div v-loading="actLoading" style="min-height:200px">
          <div v-if="activities.length === 0 && !actLoading" class="empty-state" style="padding:40px">
            <p style="color:var(--text-muted)">暂无最近动态</p>
          </div>
          <div v-for="(a, i) in activities" :key="i" class="act-item">
            <div class="act-dot" :class="'act-' + a.type"></div>
            <div class="act-body">
              <div class="act-title">
                <a :href="'#/projects/'+a.project_id" class="act-link">{{ a.project_name }}</a>
                <span class="act-type-tag">{{ a.type_label }}</span>
              </div>
              <div class="act-desc">{{ a.description }}</div>
              <div class="act-time">{{ a.time }}</div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProjects, deleteProject, copyProject } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Download, Grid, List } from '@element-plus/icons-vue'
import ProjectLedgerTable from '../components/project/ProjectLedgerTable.vue'
import api from '../api/index.js'

const route = useRoute()
const router = useRouter()

const tab = ref('list')
const viewMode = ref(localStorage.getItem('ledger_view_mode') || 'card')

function setView(mode) {
  viewMode.value = mode
  localStorage.setItem('ledger_view_mode', mode)
}
const allProjects = ref([])
const filteredProjects = ref([])
const search = ref('')
const searchField = ref('name')
const statusFilter = ref('')
const sortBy = ref('default')
const phaseFilter = ref('')
const expanded = ref(new Set())

const PHASE_ORDER = ['概念需求阶段', '方案设计阶段', '样机试制阶段', '验证阶段', '设计定型阶段', '售后维护阶段']
const PHASE_CODE = { '概念需求阶段': 'P0', '方案设计阶段': 'PP1', '样机试制阶段': 'PP2', '验证阶段': 'PP3', '设计定型阶段': 'PP4', '售后维护阶段': 'PP5' }
const SW_PHASE_ORDER = ['需求分析阶段', '架构设计阶段', '开发编码阶段', '测试验证阶段', '发布交付阶段']
const SW_PHASE_CODE = { '需求分析阶段': 'S0', '架构设计阶段': 'S1', '开发编码阶段': 'S2', '测试验证阶段': 'S3', '发布交付阶段': 'S4' }
// 全部视图:硬件阶段在前,软件阶段在后,均带 code
const PHASE_ORDER_ALL = [...PHASE_ORDER, ...SW_PHASE_ORDER]
const PHASE_CODE_ALL = { ...PHASE_CODE, ...SW_PHASE_CODE }

// 类型过滤:route query type=software 时只显示软件项目(侧边栏专属入口)
const typeFilter = ref(route.query.type === 'software' ? 'software' : (route.query.type === 'hardware' ? 'hardware' : ''))
const pageTitle = computed(() => typeFilter.value === 'software' ? '软件研发项目台账' : typeFilter.value === 'hardware' ? '电机研发项目台账' : '系统集成开发项目台账')

function setType(t) {
  typeFilter.value = t
  phaseFilter.value = ''
  filter()
  router.replace({ query: { ...route.query, type: t || undefined } })
}

// 组件复用(侧边栏菜单 query 切换)时同步类型过滤
watch(() => route.query.type, (t) => {
  const v = t === 'software' ? 'software' : t === 'hardware' ? 'hardware' : ''
  if (v !== typeFilter.value) {
    typeFilter.value = v
    phaseFilter.value = ''
    filter()
  }
})

function phaseOrderOf() {
  if (typeFilter.value === 'software') return SW_PHASE_ORDER
  if (typeFilter.value === 'hardware') return PHASE_ORDER
  return PHASE_ORDER_ALL
}
function phaseCodeOf() {
  if (typeFilter.value === 'software') return SW_PHASE_CODE
  if (typeFilter.value === 'hardware') return PHASE_CODE
  return PHASE_CODE_ALL
}

// Activity feed
const activities = ref([])
const actLoading = ref(false)

onMounted(async () => {
  try {
    const res = await getProjects()
    allProjects.value = res.data.data || res.data
    for (const g of buildGroups(allProjects.value)) expanded.value.add(g.key)
    filter()
  } catch (e) {
    ElMessage.error('项目加载失败: ' + (e?.message || ''))
    allProjects.value = []
  }
  loadActivities()
})

function buildGroups(list) {
  const order = phaseOrderOf()
  const codes = phaseCodeOf()
  const map = {}
  for (const p of list) {
    const name = p.current_phase?.name || '未开始'
    if (!map[name]) map[name] = []
    map[name].push(p)
  }
  const keys = Object.keys(map)
  keys.sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b)
    const ra = ia === -1 ? 99 : ia, rb = ib === -1 ? 99 : ib
    return ra - rb
  })
  return keys.map(k => {
    const ps = map[k]
    const avg = ps.length ? Math.round(ps.reduce((s, p) => s + (p.completion_pct || 0), 0) / ps.length) : 0
    return { key: k, name: k, code: codes[k] || '', projects: ps, avgPct: avg }
  })
}

// 阶段 chips 跟随类型筛选/搜索,与列表分组保持一致
const phaseGroups = computed(() => buildGroups(filteredProjects.value))

const visibleGroups = computed(() => buildGroups(filteredProjects.value).filter(g => !phaseFilter.value || g.key === phaseFilter.value))

function isExpanded(key) { return expanded.value.has(key) }
function toggleExpand(key) {
  if (expanded.value.has(key)) expanded.value.delete(key)
  else expanded.value.add(key)
}

function countByStatus(s) { return allProjects.value.filter(p => p.overall_status === s).length }
const avgPct = computed(() => {
  const ps = allProjects.value
  if (!ps.length) return 0
  return Math.round(ps.reduce((s, p) => s + (p.completion_pct || 0), 0) / ps.length)
})

function toggleStatusFilter(s) {
  statusFilter.value = statusFilter.value === s ? '' : s
  filter()
}

async function loadActivities() {
  actLoading.value = true
  try {
    // Get all projects for name mapping
    const projMap = {}
    for (const p of allProjects.value) projMap[p.id] = p.name

    // Gather recent risks and changes
    const [risksRes, changesRes, reportRes] = await Promise.allSettled([
      api.get('/risks', { params: { limit: 20, sort: 'created_at_desc' } }),
      api.get('/changes', { params: { limit: 20, sort: 'created_at_desc' } }),
      api.get('/reports', { params: { limit: 10 } }),
    ])

    const items = []

    // Risks
    if (risksRes.status === 'fulfilled') {
      const risks = Array.isArray(risksRes.value.data) ? risksRes.value.data : (risksRes.value.data?.data || [])
      for (const r of risks.slice(0, 8)) {
        items.push({
          type: r.type === 'issue' ? 'issue' : 'risk',
          type_label: r.type === 'issue' ? '问题' : '风险',
          project_id: r.project_id,
          project_name: projMap[r.project_id] || `项目#${r.project_id}`,
          description: r.title || r.description || '',
          time: r.created_at?.slice(0, 10) || '',
        })
      }
    }

    // Changes
    if (changesRes.status === 'fulfilled') {
      const changes = Array.isArray(changesRes.value.data) ? changesRes.value.data : (changesRes.value.data?.data || [])
      for (const c of changes.slice(0, 8)) {
        items.push({
          type: 'change',
          type_label: '变更',
          project_id: c.project_id,
          project_name: projMap[c.project_id] || `项目#${c.project_id}`,
          description: `${c.title || c.description || '项目变更'}${c.status ? ' ['+c.status+']' : ''}`,
          time: c.created_at?.slice(0, 10) || '',
        })
      }
    }

    // Weekly reports
    if (reportRes.status === 'fulfilled') {
      const reports = Array.isArray(reportRes.value.data) ? reportRes.value.data : (reportRes.value.data?.data || [])
      for (const r of reports.slice(0, 6)) {
        items.push({
          type: 'report',
          type_label: '周报',
          project_id: r.project_id,
          project_name: projMap[r.project_id] || `项目#${r.project_id}`,
          description: `W${r.year}-${r.week_number} 周报已提交${r.reporter?.name ? ' ('+r.reporter.name+')' : ''}`,
          time: r.report_date || r.created_at?.slice(0, 10) || '',
        })
      }
    }

    // Sort by time desc
    items.sort((a, b) => (b.time || '').localeCompare(a.time || ''))
    activities.value = items.slice(0, 30)
  } catch (e) {
    activities.value = []
  }
  actLoading.value = false
}

function filter() {
  let list = [...allProjects.value]
  if (typeFilter.value) list = list.filter(p => (p.project_type || 'hardware') === typeFilter.value)
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => {
      if (searchField.value === 'code') return (p.code || '').toLowerCase().includes(q)
      if (searchField.value === 'client') return (p.client?.name || '').toLowerCase().includes(q)
      return p.name.toLowerCase().includes(q)
    })
  }
  if (statusFilter.value) list = list.filter(p => p.overall_status === statusFilter.value)
  if (sortBy.value === 'pct_desc') list.sort((a, b) => (b.completion_pct || 0) - (a.completion_pct || 0))
  else if (sortBy.value === 'pct_asc') list.sort((a, b) => (a.completion_pct || 0) - (b.completion_pct || 0))
  else if (sortBy.value === 'date') list.sort((a, b) => (a.planned_end_date || '').localeCompare(b.planned_end_date || ''))
  filteredProjects.value = list
}

function res(s) { return s === 'blocked' ? 'blocked' : s === 'at_risk' ? 'risk' : 'normal' }
function statusLabel(s) { if (s === 'blocked') return '阻塞'; if (s === 'at_risk') return '有风险'; return '正常' }

async function confirmClone(proj) {
  try {
    const { value: code } = await ElMessageBox.prompt(
      `将从「${proj.name}」复制创建新项目。\n请输入新项目编号：`, '复制项目',
      { confirmButtonText: '确认', cancelButtonText: '取消', inputValue: `${proj.code}-COPY`,
        inputPattern: /^[A-Z]{2,5}-\d{4}-\d{3}(-COPY)?$/, inputErrorMessage: '格式：客户端写-年份-序号' }
    )
    await copyProject(proj.id, { new_code: code }); ElMessage.success('复制成功')
    const res = await getProjects(); allProjects.value = res.data.data || res.data; filter()
  } catch (e) { if (e !== 'cancel' && e !== 'close') ElMessage.error('复制失败') }
}

async function confirmDelete(proj) {
  try {
    await ElMessageBox.confirm(`确认删除项目「${proj.name}」？`, '删除项目', { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' })
    await deleteProject(proj.id); ElMessage.success('已删除')
    allProjects.value = allProjects.value.filter(p => p.id !== proj.id); filter()
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

async function exportProjects() {
  try {
    const res = await api.get('/export/projects', { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url; a.download = `项目总表_${new Date().toISOString().slice(0,10)}.xlsx`
    a.click(); URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
  }
}
</script>

<style scoped>
.ledger-page { max-width: 1400px; }
.page-head { margin-bottom: 16px; }
.page-head h2 { font-size: 18px; font-weight: 700; margin: 0 0 2px; }
.head-sub { font-size: 13px; color: var(--text-muted); }

/* Stats row */
.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 14px; }
.stat-card { background: var(--bg-white); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; cursor: pointer; transition: all .2s; }
.stat-card:hover { border-color: var(--primary); transform: translateY(-1px); box-shadow: var(--shadow-sm); }
.stat-num { font-size: 24px; font-weight: 700; line-height: 1.2; }
.stat-card.stat-normal .stat-num { color: #10b981; }
.stat-card.stat-risk .stat-num { color: #f59e0b; }
.stat-card.stat-blocked .stat-num { color: #ef4444; }
.stat-card.stat-avg .stat-num { color: #3b82f6; }
.stat-label { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

/* Phase chips */
.phase-chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 14px; }
.chips-title { font-size: 13px; color: var(--text-muted); }
.phase-chip { font-size: 12px; padding: 4px 12px; border-radius: 14px; border: 1px solid var(--border); background: var(--bg-white); color: var(--text-secondary); cursor: pointer; transition: all .15s; user-select: none; }
.phase-chip b { margin-left: 3px; font-weight: 600; }
.phase-chip:hover { border-color: var(--primary); color: var(--primary); }
.phase-chip.active { background: var(--primary); border-color: var(--primary); color: #fff; }

.page-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; gap: 12px; flex-wrap: wrap; }
.toolbar-left { display: flex; gap: 10px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.count-label { font-size: 13px; color: var(--text-muted); }

/* Phase group */
.phase-group { margin-bottom: 14px; background: var(--bg-white); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.phase-group-head { display: flex; align-items: center; gap: 12px; padding: 12px 16px; cursor: pointer; transition: background .15s; }
.phase-group-head:hover { background: var(--bg); }
.group-arrow { font-size: 11px; color: var(--text-muted); transition: transform .2s; }
.group-arrow.open { transform: rotate(90deg); }
.group-name { font-size: 14px; font-weight: 600; color: var(--text); }
.group-code { font-size: 12px; font-weight: 700; color: var(--primary); background: rgba(59,130,246,.1); border-radius: 4px; padding: 1px 6px; margin-right: 6px; font-family: monospace; }
.group-count { font-size: 12px; color: var(--text-muted); background: var(--bg); padding: 2px 10px; border-radius: 10px; }
.group-avg { font-size: 12px; color: var(--text-muted); }
.group-progress { flex: 1; max-width: 220px; margin-left: auto; }
.group-empty { padding: 20px; text-align: center; font-size: 13px; color: var(--text-muted); }
.phase-group-body { padding: 0 16px 16px; }

.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; padding-top: 14px; }

.proj-card { background: var(--bg-white); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px; cursor: pointer; transition: all .2s; display: flex; flex-direction: column; gap: 12px; }
.proj-card:hover { box-shadow: var(--shadow-md); border-color: var(--primary); transform: translateY(-1px); }
.proj-status-line { display: flex; align-items: center; gap: 6px; }
.status-text { font-size: 12px; color: var(--text-secondary); font-weight: 500; }
.proj-name { font-size: 15px; font-weight: 600; color: var(--text); line-height: 1.4; }
.proj-code { font-size: 12px; color: var(--text-muted); font-family: monospace; }
.proj-meta { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.proj-card-bottom { display: flex; justify-content: space-between; align-items: center; }
.proj-owner { display: flex; align-items: center; gap: 10px; min-width: 0; }
.pm-name { font-size: 12px; color: var(--primary); font-weight: 500; }
.client-name { font-size: 12px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.link { cursor: pointer; }
.link:hover { text-decoration: underline; }
.proj-name.link:hover { color: var(--primary); }
.pct-link { cursor: pointer; border-radius: 4px; padding: 2px; }
.pct-link:hover { background: rgba(59, 130, 246, .08); }
.proj-actions { display: flex; gap: 4px; opacity: 0; transition: opacity .15s; }
.proj-card:hover .proj-actions { opacity: 1; }

.dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.dot-blocked { background: #ef4444; box-shadow: 0 0 6px rgba(239,68,68,.5); animation: pulse 2s infinite; }
.dot-risk { background: #f59e0b; box-shadow: 0 0 4px rgba(245,158,11,.4); }
.dot-normal { background: #10b981; box-shadow: 0 0 4px rgba(16,185,129,.4); }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

.empty-state { text-align: center; padding: 60px 20px; background: var(--bg-white); border-radius: var(--radius); border: 1px solid var(--border); }

/* View toggle */
.view-toggle { margin-right: 2px; }

/* Activity feed */
.act-item { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.act-dot { width: 10px; height: 10px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.act-dot.act-risk { background: #ef4444; }
.act-dot.act-issue { background: #f59e0b; }
.act-dot.act-change { background: #3b82f6; }
.act-dot.act-report { background: #8b5cf6; }
.act-body { flex: 1; }
.act-title { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.act-link { font-weight: 600; font-size: 13px; color: var(--primary); text-decoration: none; }
.act-link:hover { text-decoration: underline; }
.act-type-tag { font-size: 10px; padding: 1px 6px; border-radius: 4px; background: var(--bg); color: var(--text-muted); }
.act-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.5; }
.act-time { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
</style>
