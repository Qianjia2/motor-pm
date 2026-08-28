<template>
  <div class="gantt-page">
    <div class="gantt-toolbar">
      <div style="display:flex;gap:8px;align-items:center">
        <el-select v-model="filterProject" placeholder="全部项目" clearable size="small" style="width:220px" @change="load">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-radio-group v-model="scale" size="small">
          <el-radio-button label="month">月</el-radio-button>
          <el-radio-button label="week">周</el-radio-button>
        </el-radio-group>
        <span style="font-size:12px;color:var(--text-muted);margin-left:8px">共 {{ filtered.length }} 条里程碑</span>
      </div>
      <div style="display:flex;gap:8px">
        <span class="legend"><span class="l-dot" style="background:#10b981"></span> 已完成(实际日期)</span>
        <span class="legend"><span class="l-dot" style="background:#3b82f6"></span> 进行中</span>
        <span class="legend"><span class="l-dot" style="background:#f59e0b"></span> 待开始</span>
        <span class="legend"><span class="l-dot" style="background:#ef4444"></span> 已逾期</span>
      </div>
    </div>

    <div v-if="filtered.length === 0" style="text-align:center;padding:60px;color:var(--text-muted)">暂无里程碑数据</div>

    <div v-else class="gantt-body" ref="bodyRef">
      <!-- Header: time axis -->
      <div class="gantt-header">
        <div class="gantt-label-col">里程碑</div>
        <div class="gantt-time-header" ref="timeHeader">
          <div v-for="col in timeColumns" :key="col.key"
            class="time-col" :style="{width:colWidth+'px',minWidth:colWidth+'px'}">
            {{ col.label }}
          </div>
        </div>
      </div>

      <!-- Rows: project groups → phase groups -->
      <template v-for="proj in projectGroups" :key="proj.key">
        <div class="gantt-proj-hdr" @click="toggleProject(proj.key)">
          <span class="proj-arrow" :class="{open:openProjects.has(proj.key)}">▶</span>
          <span class="proj-name">{{ proj.name }}</span>
          <span class="proj-code">{{ proj.code }}</span>
          <span class="proj-count">{{ proj.total }}条</span>
          <span class="proj-bar"><span class="proj-fill" :style="{width:proj.donePct+'%'}"></span></span>
          <span style="font-size:11px;color:var(--text-muted)">{{ proj.donePct }}%</span>
        </div>
        <template v-if="openProjects.has(proj.key)">
          <template v-for="grp in proj.phases" :key="grp.key">
            <div class="gantt-phase-hdr">{{ grp.label }} ({{ grp.items.length }}条)</div>
            <div v-for="ms in grp.items" :key="ms.id" class="gantt-row">
              <div class="gantt-label-col">
                <span class="row-dot" :style="{background:statusColor(ms)}"></span>
                <span class="row-name" :title="ms.name">{{ ms.name }}</span>
                <span class="row-line" v-if="ms.line_name">{{ ms.line_name }}</span>
              </div>
              <div class="gantt-bar-area">
                <div v-if="ms.planned_date" class="gantt-bar planned"
                  :style="barStyle(ms, 'planned')"
                  :title="`${ms.planned_date} ~ ${ms.planned_end_date||ms.planned_date}`">
                </div>
                <div v-if="ms.actual_date && ms.actual_date !== ms.planned_date" class="gantt-bar actual"
                  :style="barStyle(ms, 'actual')"
                  :title="`${ms.actual_date} ~ ${ms.actual_end_date||ms.actual_date}`">
                </div>
              </div>
            </div>
          </template>
        </template>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getProjects, getAllMilestones } from '../api/index.js'

const projects = ref([])
const allMilestones = ref([])
const openProjects = ref(new Set())  // Track which project groups are expanded
const filterProject = ref(null)
const scale = ref('month')

const colWidth = computed(() => scale.value === 'week' ? 32 : 72)

const filtered = computed(() => {
  if (filterProject.value) return allMilestones.value.filter(m => m.project_id === filterProject.value)
  return allMilestones.value
})

const timeRange = computed(() => {
  let min = null, max = null
  filtered.value.forEach(m => {
    const dates = [m.planned_date, m.planned_end_date, m.actual_date, m.actual_end_date].filter(Boolean)
    dates.forEach(d => {
      const dt = new Date(d)
      if (!min || dt < min) min = dt
      if (!max || dt > max) max = dt
    })
  })
  if (!min) min = new Date()
  if (!max) max = new Date()
  min = new Date(min); min.setDate(1); min.setMonth(min.getMonth() - 1)
  max = new Date(max); max.setMonth(max.getMonth() + 1)
  return { min, max }
})

const timeColumns = computed(() => {
  const cols = []
  const cur = new Date(timeRange.value.min)
  while (cur <= timeRange.value.max) {
    const y = cur.getFullYear(), m = cur.getMonth() + 1
    if (scale.value === 'week') {
      const wn = weekNum(cur)
      cols.push({ key: `${y}-W${wn}`, label: `${m}/${cur.getDate()}`, year: y, month: m })
      cur.setDate(cur.getDate() + 7)
    } else {
      cols.push({ key: `${y}-${m}`, label: `${y}/${m}`, year: y, month: m })
      cur.setMonth(cur.getMonth() + 1)
    }
  }
  return cols
})

const totalCols = computed(() => timeColumns.value.length)

const projectGroups = computed(() => {
  const projMap = new Map()
  filtered.value.forEach(m => {
    const pid = m.project_id || 0
    const projName = m.project_name || m.project?.name || '未分类'
    const projCode = m.project_code || m.project?.code || ''
    if (!projMap.has(pid)) {
      projMap.set(pid, { key: pid, name: projName, code: projCode, phases: new Map(), _open: true })
    }
    const proj = projMap.get(pid)
    const phaseId = m.phase_id || 0
    const phaseName = m.phase_name || m.phase?.name || '未分配阶段'
    if (!proj.phases.has(phaseId)) {
      proj.phases.set(phaseId, { key: phaseId, label: phaseName, items: [] })
    }
    proj.phases.get(phaseId).items.push({
      ...m,
      line_name: m.line?.short_name || m.line?.name || '',
    })
  })
  return [...projMap.values()].map(proj => {
    const phases = [...proj.phases.values()].sort((a, b) => a.key - b.key)
    const all = phases.flatMap(p => p.items)
    const done = all.filter(m => m.status === 'completed').length
    return {
      ...proj,
      phases,
      total: all.length,
      donePct: all.length ? Math.round(done / all.length * 100) : 0,
    }
  })
})

function barStyle(ms, type) {
  const startD = type === 'actual' ? (ms.actual_date || ms.planned_date) : ms.planned_date
  const endD = type === 'actual' ? (ms.actual_end_date || ms.actual_date || ms.planned_end_date)
    : (ms.planned_end_date || ms.planned_date)

  if (!startD) return { display: 'none' }

  const totalDays = Math.max(1, (timeRange.value.max - timeRange.value.min) / 86400000)
  const offsetDays = (new Date(startD) - timeRange.value.min) / 86400000
  const durationDays = Math.max(2, (new Date(endD) - new Date(startD)) / 86400000)

  const leftPct = (offsetDays / totalDays) * 100
  const widthPct = (durationDays / totalDays) * 100

  if (type === 'actual') {
    return { left: leftPct + '%', width: Math.max(widthPct, 0.3) + '%', background: '#10b981', opacity: 0.8 }
  }
  return { left: leftPct + '%', width: Math.max(widthPct, 0.3) + '%', background: statusColor(ms) }
}

function statusColor(ms) {
  const today = new Date(); today.setHours(0,0,0,0)
  if (ms.status === 'completed') return '#10b981'
  if (ms.status === 'in_progress') return '#3b82f6'
  if (ms.planned_end_date && new Date(ms.planned_end_date) < today) return '#ef4444'
  return '#f59e0b'
}

function toggleProject(key) {
  const s = new Set(openProjects.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  openProjects.value = s
}

function weekNum(d) {
  const start = new Date(d.getFullYear(), 0, 1)
  return Math.ceil(((d - start) / 86400000 + start.getDay() + 1) / 7)
}

onMounted(async () => {
  try {
    const [projRes, msRes] = await Promise.all([
      getProjects({ page_size: 100 }),
      getAllMilestones(),
    ])
    projects.value = projRes.data?.data || projRes.data || []
    allMilestones.value = (msRes.data || []).map(m => ({
      ...m,
      project_name: m.project_name || m.project?.name || '',
      phase_name: m.phase_name || m.phase?.name || '',
    }))
    // All projects open by default
    const ids = new Set(allMilestones.value.map(m => m.project_id))
    openProjects.value = ids
  } catch (e) {
    console.error(e)
  }
})
</script>

<style scoped>
.gantt-page { background: #fff; border-radius: 8px; box-shadow: var(--shadow-sm); overflow: hidden; }
.gantt-toolbar { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #f0f0f0; flex-wrap:wrap; gap:8px; }
.legend { font-size:11px; color: var(--text-muted); display:flex; align-items:center; gap:4px; }
.l-dot { width:10px; height:10px; border-radius:2px; }
.gantt-body { overflow-x: auto; }
.gantt-header { display:flex; border-bottom:2px solid #e5e7eb; }
.gantt-label-col { width:240px; min-width:240px; padding:8px 12px; font-weight:600; font-size:12px; border-right:1px solid #f0f0f0; }
.gantt-time-header { display:flex; flex:1; overflow:hidden; }
.time-col { text-align:center; font-size:11px; color:#6b7280; padding:8px 0; border-right:1px solid #f5f5f5; }
.gantt-proj-hdr { display:flex; align-items:center; gap:10px; padding:10px 14px; font-size:14px; font-weight:700; color:#1f2937; background:#eef2ff; border-bottom:2px solid #c7d2fe; cursor:pointer; user-select:none; }
.gantt-proj-hdr:hover { background:#e0e7ff; }
.proj-arrow { font-size:10px; transition:transform .2s; color:#6366f1; flex-shrink:0; }
.proj-arrow.open { transform:rotate(90deg); }
.proj-name { color:#1e3a5f; }
.proj-code { font-size:11px; color:#6b7280; font-family:monospace; }
.proj-count { font-size:11px; color:#9ca3af; margin-left:auto; }
.proj-bar { width:80px; height:6px; background:#e5e7eb; border-radius:3px; overflow:hidden; }
.proj-fill { height:100%; background:#6366f1; border-radius:3px; transition:width .3s; display:block; }
.gantt-phase-hdr { padding:6px 16px 6px 32px; font-size:12px; font-weight:600; color:#6b7280; background:#f9fafb; border-bottom:1px solid #f0f0f0; }
.gantt-row { display:flex; border-bottom:1px solid #fafafa; position:relative; min-height:32px; align-items:center; }
.gantt-row:hover { background:#f9fafb; }
.row-dot { width:8px; height:8px; border-radius:50%; min-width:8px; }
.row-name { font-size:12px; color:#1f2937; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.row-line { font-size:10px; color:#9ca3af; margin-left:4px; background:#f3f4f6; padding:0 4px; border-radius:2px; }
.gantt-bar-area { flex:1; position:relative; height:22px; }
.gantt-bar { position:absolute; top:2px; height:18px; border-radius:3px; min-width:4px; }
.gantt-bar.planned { opacity:0.9; }
.gantt-bar.actual { top:11px; height:7px; }
</style>
