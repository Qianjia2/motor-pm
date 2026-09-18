<template>
  <div class="dashboard">
    <!-- ═══════ Row 1: KPI Cards ═══════ -->
    <div class="kpi-row">
      <div class="kpi-card">
        <div class="kpi-value" style="color:#3b82f6">{{ overview.total }}</div>
        <div class="kpi-label">项目总数</div>
        <div class="kpi-sub">{{ overview.normal }} 正常 · {{ overview.atRisk + overview.blocked }} 异常</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:#10b981">{{ overview.normal }}</div>
        <div class="kpi-label">正常项目</div>
        <div class="kpi-bar"><div class="kpi-fill" style="width:100%;background:#10b981"></div></div>
      </div>
      <div class="kpi-card has-alert">
        <div class="kpi-value" style="color:#ef4444">{{ overview.blocked }}</div>
        <div class="kpi-label">阻塞项目</div>
        <div v-if="blockedProjects.length" class="kpi-detail">
          <span v-for="p in blockedProjects.slice(0,2)" :key="p.id" class="kpi-link" @click="goProject(p, 'risks')">{{ p.name.slice(0,12) }}</span>
        </div>
      </div>
      <div class="kpi-card has-alert">
        <div class="kpi-value" style="color:#f59e0b">{{ overview.atRisk }}</div>
        <div class="kpi-label">有风险</div>
        <div v-if="riskProjects.length" class="kpi-detail">
          <span v-for="p in riskProjects.slice(0,2)" :key="p.id" class="kpi-link" @click="goProject(p, 'risks')">{{ p.name.slice(0,12) }}</span>
        </div>
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:#8b5cf6">{{ overview.avgCompletion }}%</div>
        <div class="kpi-label">平均完成率</div>
        <el-progress :percentage="overview.avgCompletion" :stroke-width="4" :color="'#8b5cf6'" style="margin-top:8px" />
      </div>
      <div class="kpi-card">
        <div class="kpi-value" style="color:#ef4444">{{ overview.overdueMilestones }}</div>
        <div class="kpi-label">逾期里程碑</div>
        <div class="kpi-sub">共 {{ overview.totalMilestones }} 个里程碑</div>
      </div>
    </div>

    <!-- ═══════ Row 2: Overdue Milestones + Exception Projects ═══════ -->
    <div class="mid-row">
      <div class="card" style="flex:1">
        <div class="card-header">
          <div class="card-title">逾期里程碑</div>
          <a href="#" class="card-link" @click.prevent="$router.push('/milestones')">全景 →</a>
        </div>
        <div v-if="overdueMilestoneList.length === 0" class="empty-state" style="color:#10b981;padding:24px">暂无逾期里程碑 ✓</div>
        <div v-for="ms in overdueMilestoneList" :key="ms.id" class="todo-row" @click="goProject({id:ms.project_id})">
          <span class="todo-icon">📅</span>
          <div style="flex:1;min-width:0">
            <div class="todo-title">{{ ms.name }}</div>
            <div class="todo-meta">{{ ms.project_name }} · 计划 {{ ms.planned_date }}</div>
          </div>
          <span class="tag tag-red" style="font-size:10px">逾期</span>
        </div>
      </div>

      <div class="card" style="flex:1">
        <div class="card-header">
          <div class="card-title">异常项目</div>
          <a href="#" class="card-link" @click.prevent="$router.push('/projects')">项目列表 →</a>
        </div>
        <div v-if="exceptionProjects.length === 0" class="empty-state" style="color:#10b981;padding:24px">所有项目运行正常 ✓</div>
        <div v-for="p in exceptionProjects" :key="p.id" class="todo-row" @click="goProject(p, 'risks')">
          <span class="todo-icon">{{ p.overall_status==='blocked' ? '🚫' : '⚠️' }}</span>
          <div style="flex:1;min-width:0">
            <div class="todo-title">{{ p.name }}</div>
            <div class="todo-meta">{{ p.code }} · {{ p.current_phase?.name || '-' }}</div>
            <!-- 异常原因:直接来自后端的健康推导分量,与上面那个状态标签同源 -->
            <div v-if="p.health_reason" class="todo-reason">{{ p.health_reason }}</div>
          </div>
          <span class="tag" :class="p.overall_status==='blocked'?'tag-red':'tag-orange'" style="font-size:10px">
            {{ p.overall_status==='blocked' ? '阻塞' : '有风险' }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══════ Row 3: Project Portfolio Table ═══════ -->
    <div class="card" style="margin-top:16px">
      <div class="card-header">
        <div class="card-title">项目组合一览</div>
        <div class="card-actions">
          <el-radio-group v-model="tableFilter" size="small" @change="onTableFilter">
            <el-radio-button label="all">全部({{ healthGrid.length }})</el-radio-button>
            <el-radio-button label="active">进行中</el-radio-button>
            <el-radio-button label="blocked">阻塞</el-radio-button>
          </el-radio-group>
          <el-input v-model="search" placeholder="搜索..." size="small" style="width:160px" clearable :prefix-icon="Search" />
          <el-button type="primary" size="small" @click="$router.push('/projects/new')">
            <el-icon><Plus /></el-icon> 新建
          </el-button>
        </div>
      </div>

      <el-table :data="tableProjects" stripe size="medium" highlight-current-row
        @row-click="goProject" style="cursor:pointer">
        <el-table-column type="index" label="#" width="40" />
        <el-table-column label="健康" width="45" align="center">
          <template #default="{row}">
            <span class="dot" :class="'dot-' + statusKey(row.overall_status)"></span>
          </template>
        </el-table-column>
        <el-table-column prop="code" label="项目编号" width="130">
          <template #default="{row}">
            <span style="font-family:monospace;font-size:12px;color:var(--text-secondary)">{{ row.code }}</span>
          </template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="200" show-overflow-tooltip>
          <template #default="{row}">
            <span class="project-name">{{ row.name }}</span>
            <span v-if="row.priority==='P0'" class="tag tag-red" style="font-size:10px;margin-left:4px">P0</span>
          </template>
        </el-table-column>
        <el-table-column label="客户" width="110" show-overflow-tooltip>
          <template #default="{row}">{{ row.client?.name || '-' }}</template>
        </el-table-column>
        <el-table-column label="当前阶段" width="105">
          <template #default="{row}">
            <span class="tag tag-blue">{{ row.current_phase?.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完成率" width="150">
          <template #default="{row}">
            <div style="display:flex;align-items:center;gap:8px">
              <el-progress :percentage="row.completion_pct||0" :stroke-width="6" style="flex:1"
                :color="row.completion_pct>=80?'#10b981':row.completion_pct>=40?'#3b82f6':'#f59e0b'" />
              <span style="font-size:12px;font-weight:600;color:var(--text-secondary);width:36px">{{ row.completion_pct||0 }}%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="合同额" width="90" align="right">
          <template #default="{row}">
            <span v-if="row.contract_amount" style="font-weight:600;font-size:13px">{{ row.contract_amount }}万</span>
            <span v-else style="color:var(--text-muted)">-</span>
          </template>
        </el-table-column>
        <el-table-column label="截止日期" width="105">
          <template #default="{row}">
            <span :class="{overdue: isOverdue(row.planned_end_date)}">{{ row.planned_end_date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险" width="55" align="center">
          <template #default="{row}">
            <span v-if="row.open_risks > 0" class="tag tag-red">{{ row.open_risks }}</span>
            <span v-else style="color:var(--text-muted)">0</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══════ Row 4: Charts + Milestones ═══════ -->
    <div class="bottom-grid">
      <!-- Phase Distribution -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">阶段分布</div>
        </div>
        <div class="phase-chart">
          <div v-for="ph in phaseStats" :key="ph.name" class="phase-bar-row">
            <span class="phase-bar-label">{{ ph.name }}</span>
            <div class="phase-bar-bg">
              <div class="phase-bar-fill" :style="{width:ph.pct+'%',background:ph.color}"></div>
            </div>
            <span class="phase-bar-num">{{ ph.count }}</span>
          </div>
        </div>
      </div>

      <!-- Milestones -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">近期里程碑</div>
          <a href="#" class="card-link" @click.prevent="$router.push('/milestones')">全景 →</a>
        </div>
        <div v-if="upcomingMilestones.length===0" class="empty-state">暂无近期里程碑</div>
        <div v-for="ms in upcomingMilestones.slice(0,6)" :key="ms.id" class="ms-row" @click="goProject({id:ms.project_id})">
          <span class="ms-dot" :class="ms.status||'pending'"></span>
          <span class="ms-name">{{ ms.name }}</span>
          <span class="ms-date" :class="{overdue:!ms.actual_date && isOverdue(ms.planned_date)}">
            {{ ms.status === 'completed' && ms.actual_date ? ms.actual_date : ms.planned_date }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { getDashboard, getAllMilestones, getProjects, getResourceMatrix } from '../api/index.js'
import { Search, Plus } from '@element-plus/icons-vue'

const router = useRouter()
const auth = useAuthStore()
const search = ref('')
const tableFilter = ref('all')

const overview = ref({ total: 0, normal: 0, atRisk: 0, blocked: 0, avgCompletion: 0, overdueMilestones: 0, totalMilestones: 0 })
const healthGrid = ref([])
const allMilestones = ref([])
const resourceData = ref([])

// ── Computed ──

const blockedProjects = computed(() => healthGrid.value.filter(p => p.overall_status === 'blocked'))
const riskProjects = computed(() => healthGrid.value.filter(p => p.overall_status === 'at_risk'))

const tableProjects = computed(() => {
  let list = healthGrid.value
  if (tableFilter.value === 'active') list = list.filter(p => p.overall_status !== 'completed')
  if (tableFilter.value === 'blocked') list = list.filter(p => p.overall_status === 'blocked')
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(p => p.name.toLowerCase().includes(q) || (p.code||'').toLowerCase().includes(q))
  }
  // Sort: blocked > at_risk > normal > completed
  const order = { blocked: 0, at_risk: 1, normal: 2, completed: 3 }
  return [...list].sort((a,b) => (order[a.overall_status]??2) - (order[b.overall_status]??2))
})

// Overdue milestones (global view)
const overdueMilestoneList = computed(() => {
  const today = new Date(); today.setHours(0,0,0,0)
  return allMilestones.value
    .filter(ms => ms.planned_date && ms.status !== 'completed' && new Date(ms.planned_date) < today)
    .sort((a,b) => (a.planned_date||'').localeCompare(b.planned_date||''))
    .slice(0, 6)
})

// Exception projects: blocked first, then at-risk
const exceptionProjects = computed(() => {
  const order = { blocked: 0, at_risk: 1 }
  return [...blockedProjects.value, ...riskProjects.value]
    .sort((a,b) => (order[a.overall_status] ?? 2) - (order[b.overall_status] ?? 2))
    .slice(0, 6)
})

const upcomingMilestones = computed(() => {
  const today = new Date(); today.setHours(0,0,0,0)
  const end = new Date(today); end.setDate(end.getDate()+30)
  return allMilestones.value
    .filter(ms => ms.planned_date && new Date(ms.planned_date) <= end)
    .sort((a,b) => (a.planned_date||'').localeCompare(b.planned_date||''))
    .slice(0, 10)
})

const phaseStats = computed(() => {
  const colors = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ef4444','#06b6d4']
  const map = new Map()
  healthGrid.value.forEach(p => {
    const ph = p.current_phase?.name || '未分配'
    map.set(ph, (map.get(ph)||0)+1)
  })
  const total = healthGrid.value.length || 1
  return Array.from(map.entries()).map(([name, count], i) => ({
    name, count, pct: Math.round(count/total*100), color: colors[i%colors.length],
  })).sort((a,b) => b.count - a.count)
})

// ── Helpers ──

function statusKey(s) { return s==='blocked'?'blocked':s==='at_risk'?'risk':'normal' }
function isOverdue(d) { if(!d) return false; const t=new Date(); t.setHours(0,0,0,0); return new Date(d)<t }
// tab 可选:不传就落在项目详情页默认概览页签。
// 非字符串一律当没传——本函数也直接挂在 el-table 的 row-click 上,那个事件会
// 把列对象塞进第二个参数,不挡一下会拼出 ?tab=[object Object]。
function goProject(row, tab) {
  const t = typeof tab === 'string' ? tab : null
  router.push(t ? `/projects/${row.id}?tab=${t}` : '/projects/'+row.id)
}
function onTableFilter() {}

// ── Load ──

onMounted(async () => {
  const [dash, timeline, projects, resMatrix] = await Promise.all([
    getDashboard(),
    getAllMilestones().catch(()=>({data:[]})),
    getProjects({page_size:100}).catch(()=>({data:{data:[]}})),
    getResourceMatrix().catch(()=>({data:[]})),
  ])
  const s = dash.data?.summary || {}
  healthGrid.value = (projects.data?.data||[]).map(p=>({...p, open_risks:p.open_risks??0, completion_pct:p.completion_pct||0}))
  const _ps = healthGrid.value
  overview.value = {
    total: s.total||0, normal: s.normal||0, atRisk: s.at_risk||0, blocked: s.blocked||0,
    // 平均完成率 = 各项目完成率的均值（而非正常项目占比）
    avgCompletion: _ps.length ? Math.round(_ps.reduce((acc,p)=>acc+(p.completion_pct||0),0)/_ps.length) : 0,
    overdueMilestones: s.overdue_milestones||0,
    totalMilestones: s.total_milestones||(timeline.data||[]).length,
  }
  allMilestones.value = (timeline.data||[]).map(m=>({...m, project_name:m.project_name||(m.project?m.project.name:'')}))
  resourceData.value = resMatrix.data||[]
})
</script>

<style scoped>
.dashboard { max-width:1400px; }

/* KPI Row */
.kpi-row { display:grid; grid-template-columns:repeat(6,1fr); gap:16px; margin-bottom:16px; }
.kpi-card {
  background:var(--bg-white); border:1px solid var(--border);
  border-radius:var(--radius); padding:16px 20px;
  box-shadow:var(--shadow-sm); transition:box-shadow .2s;
}
.kpi-card:hover { box-shadow:var(--shadow-md); }
.kpi-value { font-size:30px; font-weight:700; line-height:1.1; }
.kpi-label { font-size:12px; color:var(--text-secondary); margin-top:4px; font-weight:500; }
.kpi-sub { font-size:11px; color:var(--text-muted); margin-top:4px; }
.kpi-detail { margin-top:6px; display:flex; flex-wrap:wrap; gap:4px; }
.kpi-link { font-size:11px; color:var(--text-secondary); cursor:pointer; background:#f3f4f6; padding:1px 6px; border-radius:4px; }
.kpi-link:hover { background:#e5e7eb; }
.kpi-bar { height:4px; background:#f3f4f6; border-radius:2px; margin-top:8px; overflow:hidden; }
.kpi-fill { height:100%; border-radius:2px; transition:width .5s; }

/* Mid row */
.mid-row { display:flex; gap:16px; }

/* Todo rows */
.todo-row {
  display:flex; align-items:center; gap:10px; padding:10px 0;
  border-bottom:1px solid #f3f4f6; cursor:pointer; transition:background .15s;
}
.todo-row:hover { background:#fafafa; }
.todo-icon { font-size:16px; flex-shrink:0; }
.todo-title { font-size:13px; font-weight:500; color:var(--text); }
.todo-meta { font-size:11px; color:var(--text-muted); margin-top:1px; }
.todo-reason { font-size:11px; color:#b45309; margin-top:2px; }

/* Table */
.project-name { font-weight:600; color:var(--text); }
.dot { display:inline-block; width:9px; height:9px; border-radius:50%; }
.dot-blocked { background:#ef4444; box-shadow:0 0 5px rgba(239,68,68,.5); animation:pulse 2s infinite; }
.dot-risk { background:#f59e0b; box-shadow:0 0 4px rgba(245,158,11,.4); }
.dot-normal { background:#10b981; box-shadow:0 0 4px rgba(16,185,129,.4); }
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.overdue { color:#ef4444; font-weight:600; }
.card-actions { display:flex; gap:8px; align-items:center; }

/* Bottom grid */
.bottom-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:16px; }

/* Phase chart */
.phase-chart { display:flex; flex-direction:column; gap:10px; }
.phase-bar-row { display:flex; align-items:center; gap:10px; font-size:12px; }
.phase-bar-label { width:70px; text-align:right; color:var(--text-secondary); font-weight:500; }
.phase-bar-bg { flex:1; height:18px; background:#f3f4f6; border-radius:4px; overflow:hidden; }
.phase-bar-fill { height:100%; border-radius:4px; transition:width .5s; min-width:2px; }
.phase-bar-num { width:24px; font-weight:600; color:var(--text); }

/* Milestones */
.ms-row {
  display:flex; align-items:center; gap:8px; padding:9px 0;
  border-bottom:1px solid #f3f4f6; cursor:pointer; transition:background .15s;
}
.ms-row:hover { background:#fafafa; }
.ms-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.ms-dot.completed { background:#10b981; }
.ms-dot.in_progress { background:#3b82f6; }
.ms-dot.pending { background:#d1d5db; }
.ms-dot.overdue { background:#ef4444; }
.ms-name { flex:1; font-size:13px; font-weight:500; }
.ms-date { font-size:12px; color:var(--text-secondary); white-space:nowrap; }

.card-link { color:var(--primary); font-size:12px; text-decoration:none; font-weight:500; }
.card-link:hover { text-decoration:underline; }
.empty-state { text-align:center; padding:30px; color:var(--text-muted); font-size:13px; }
</style>
