<template>
  <div class="ms-page">
    <!-- KPI bar -->
    <div class="ms-kpi-bar">
      <div class="ms-kpi"><span class="ms-kpi-num">{{ milestones.length }}</span>全部</div>
      <div class="ms-kpi kpi-done"><span class="ms-kpi-num">{{ stats.completed }}</span>已完成</div>
      <div class="ms-kpi kpi-progress"><span class="ms-kpi-num">{{ stats.inProgress }}</span>进行中</div>
      <div class="ms-kpi kpi-overdue"><span class="ms-kpi-num">{{ stats.overdue }}</span>已逾期</div>
      <div class="ms-kpi kpi-upcoming"><span class="ms-kpi-num">{{ stats.upcoming }}</span>本月到期</div>
      <div class="ms-kpi"><span class="ms-kpi-num">{{ stats.key }}</span>关键节点</div>
    </div>

    <!-- Toolbar -->
    <div class="ms-toolbar">
      <el-radio-group v-model="filterTab" size="small">
        <el-radio-button label="all">全部</el-radio-button>
        <el-radio-button label="overdue">已逾期</el-radio-button>
        <el-radio-button label="upcoming">本月到期</el-radio-button>
        <el-radio-button label="key">关键节点</el-radio-button>
      </el-radio-group>
      <div style="display:flex;gap:8px">
        <el-select v-model="filterProject" placeholder="按项目" clearable size="small" style="width:200px">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-button size="small" type="primary" @click="openDialog()"><el-icon><Plus /></el-icon> 添加</el-button>
        <el-button size="small" @click="syncFromReport" :loading="syncing" :disabled="!filterProject">🤖 从周报同步</el-button>
      </div>
    </div>

    <!-- Milestones by project → phase -->
    <div v-if="grouped.length===0" class="ms-empty">暂无匹配的里程碑</div>
    <div v-for="proj in grouped" :key="proj.project_id" class="ms-group">
      <div class="ms-group-hdr" @click="toggleProject(proj.project_id)">
        <el-icon class="ms-arrow" :class="{open:openProjects.has(proj.project_id)}"><ArrowRight /></el-icon>
        <span class="ms-proj-name">{{ proj.project_name }}</span>
        <span class="ms-proj-code">{{ proj.project_code }}</span>
        <span class="ms-count">{{ proj.total }}个里程碑</span>
        <span class="ms-progress-bar"><span class="ms-progress-fill" :style="{width:proj.donePct+'%'}"></span></span>
        <span style="font-size:11px;color:var(--text-muted)">{{ proj.donePct }}%</span>
      </div>
      <div v-show="openProjects.has(proj.project_id)">
        <!-- Phase groups -->
        <div v-for="phase in proj.phaseList" :key="phase.name" class="ms-phase">
          <div class="ms-phase-hdr">{{ phase.name }} ({{ phase.count }}项)</div>
          <div v-for="ms in phase.items" :key="ms.id" class="ms-item" :class="{overdue: ms.status==='overdue' || isPast(ms.planned_date)}">
            <span class="ms-dot" :class="'dot-'+ms.status"></span>
            <span class="ms-name">{{ ms.name }}</span>
            <span v-if="ms.is_key" class="tag tag-red" style="font-size:9px">关键</span>
            <span class="ms-date" :class="{overdue: !ms.actual_date && isPast(ms.planned_date)}"
              :style="{color:ms.status==='completed'?'#10b981':''}">
              {{ ms.status==='completed'&&ms.actual_date ? ms.actual_date : ms.planned_date }}
            </span>
            <span v-if="ms.planned_end_date" class="ms-end">→ {{ ms.planned_end_date }}</span>
            <span class="tag ms-status-tag" :class="statusCls(ms.status)">{{ statusLabel(ms.status) }}</span>
            <el-button link size="small" @click.stop="openDialog(ms)">编辑</el-button>
            <el-button link size="small" type="danger" @click.stop="deleteMs(ms)">删除</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Dialog -->
    <el-dialog v-model="showDialog" :title="editing ? '编辑' : '添加里程碑'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="项目" required v-if="!filterProject">
          <el-select v-model="form.project_id" style="width:100%"><el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" /></el-select>
        </el-form-item>
        <el-form-item label="所属阶段">
          <el-select v-model="form.phase_id" style="width:100%" clearable placeholder="选择阶段">
            <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="计划日期"><el-date-picker v-model="form.planned_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="结束日期"><el-date-picker v-model="form.planned_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="实际开始"><el-date-picker v-model="form.actual_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="实际结束"><el-date-picker v-model="form.actual_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="待开始" value="pending" /><el-option label="进行中" value="in_progress" /><el-option label="已完成" value="completed" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="关键节点"><el-switch v-model="form.is_key" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="showDialog=false">取消</el-button><el-button type="primary" @click="save" :loading="saving">{{ editing?'更新':'创建' }}</el-button></template>
    </el-dialog>

    <!-- Sync from weekly report dialog -->
    <el-dialog v-model="showSyncDialog" title="🤖 从周报同步里程碑" width="650px">
      <div v-if="syncSuggestions.length === 0" style="text-align:center;padding:20px;color:var(--text-muted)">
        {{ syncing ? '分析中...' : '未检测到可同步的里程碑更新' }}
      </div>
      <el-table v-else :data="syncSuggestions" size="small">
        <el-table-column label="里程碑" prop="milestone_name" min-width="150" />
        <el-table-column label="匹配关键词" width="110">
          <template #default="{row}"><el-tag size="small" type="warning">{{ row.matched_keyword }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态建议" width="120">
          <template #default="{row}">
            <el-tag v-if="row.suggested_status!==row.current_status" size="small" type="success">
              {{ {pending:'待开始',in_progress:'进行中',completed:'已完成'}[row.suggested_status] || row.suggested_status }}
            </el-tag>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="建议日期" width="120">
          <template #default="{row}">
            <span v-if="row.suggested_actual_date" style="font-size:12px;color:#67c23a">
              完成日: {{ row.suggested_actual_date }}
            </span>
            <span v-else style="color:#c0c4cc">-</span>
          </template>
        </el-table-column>
        <el-table-column label="置信度" width="70">
          <template #default="{row}">
            <el-tag size="small" :type="row.confidence==='high'?'success':'info'">{{ row.confidence==='high'?'高':'中' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="showSyncDialog = false">取消</el-button>
        <el-button type="primary" @click="applySync" :loading="applying" :disabled="!syncSuggestions.length">应用所有建议</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import api, { getProjects, getAllMilestones, createMilestone, updateMilestone, deleteMilestone, getPhases } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, ArrowRight } from '@element-plus/icons-vue'

const projects = ref([]); const milestones = ref([]); const phases = ref([])
const showSyncDialog = ref(false)
const syncing = ref(false)
const applying = ref(false)
const syncSuggestions = ref([])
const filterProject = ref(null); const filterTab = ref('all')
const showDialog = ref(false); const editing = ref(null); const saving = ref(false)
const openProjects = ref(new Set())

const today = new Date(); today.setHours(0,0,0,0)
const thisMonthEnd = new Date(today.getFullYear(), today.getMonth()+1, 0)

const form = reactive({ name:'', project_id:null, phase_id:null, planned_date:'', planned_end_date:'', actual_date:'', actual_end_date:'', status:'pending', is_key:false })

const phaseOrder = ['概念需求阶段','方案设计阶段','样机试制阶段','验证阶段','设计定型阶段','售后维护阶段']

function toggleProject(id) {
  const s = new Set(openProjects.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  openProjects.value = s
}

const stats = computed(() => ({
  completed: milestones.value.filter(m=>m.status==='completed').length,
  inProgress: milestones.value.filter(m=>m.status==='in_progress').length,
  overdue: milestones.value.filter(m=>m.status!=='completed'&&new Date(m.planned_date)<today).length,
  upcoming: milestones.value.filter(m=>m.status!=='completed'&&new Date(m.planned_date)>=today&&new Date(m.planned_date)<=thisMonthEnd).length,
  key: milestones.value.filter(m=>m.is_key).length,
}))

const grouped = computed(() => {
  let list = milestones.value
  if (filterTab.value === 'overdue') list = list.filter(m => m.status!=='completed' && new Date(m.planned_date) < today)
  else if (filterTab.value === 'upcoming') list = list.filter(m => m.status!=='completed' && new Date(m.planned_date) >= today && new Date(m.planned_date) <= thisMonthEnd)
  else if (filterTab.value === 'key') list = list.filter(m => m.is_key)

  const phaseMap = {}
  for (const p of phases.value) { phaseMap[p.id] = p.name }

  const projMap = new Map()
  for (const ms of list) {
    const pid = ms.project_id || (ms.project && ms.project.id)
    if (!projMap.has(pid)) {
      projMap.set(pid, { project_id: pid, project_name: ms.project_name || (ms.project && ms.project.name) || 'Unknown', project_code: ms.project_code || (ms.project && ms.project.code) || '', phases: new Map(), total: 0, done: 0 })
    }
    const proj = projMap.get(pid)
    let pname = ms.phase_name || phaseMap[ms.phase_id] || '其他阶段'
    if (!proj.phases.has(pname)) proj.phases.set(pname, [])
    proj.phases.get(pname).push(ms)
    proj.total++
    if (ms.status === 'completed') proj.done++
  }

  const result = []
  for (const proj of projMap.values()) {
    proj.donePct = proj.total ? Math.round(proj.done / proj.total * 100) : 0
    const sortedPhases = [...proj.phases.entries()].sort((a,b) => {
      const ai = phaseOrder.indexOf(a[0]), bi = phaseOrder.indexOf(b[0])
      if (ai===-1 && bi===-1) return a[0].localeCompare(b[0])
      if (ai===-1) return 1; if (bi===-1) return -1
      return ai - bi
    })
    proj.phaseList = sortedPhases.map(([name,items]) => {
      items.sort((a,b) => (a.planned_date||'').localeCompare(b.planned_date||''))
      return { name, items, count: items.length }
    })
    result.push(proj)
  }
  return result.sort((a,b) => {
    const aOv = a.phaseList.reduce((s,ph)=>s+ph.items.filter(m=>m.status!=='completed'&&isPast(m.planned_date)).length,0)
    const bOv = b.phaseList.reduce((s,ph)=>s+ph.items.filter(m=>m.status!=='completed'&&isPast(m.planned_date)).length,0)
    return bOv - aOv
  })
})

function isPast(d) { if(!d) return false; return new Date(d) < today }
function statusLabel(s) { const m={completed:'已完成',in_progress:'进行中',pending:'待开始',overdue:'已逾期'}; return m[s]||s }
function statusCls(s) { return s==='completed'?'tag-green':s==='in_progress'?'tag-blue':s==='overdue'?'tag-red':'tag-gray' }

onMounted(async () => {
  try { const r=await getProjects({page_size:100}); projects.value=r.data?.data||r.data||[] } catch(e){}
  try { const r=await getPhases(); phases.value=r.data||[] } catch(e){}
  await load()
})

async function load() {
  try {
    const params = filterProject.value ? { project_id: filterProject.value } : {}
    const r = await getAllMilestones(params)
    milestones.value = r.data || []
    const ids = new Set(milestones.value.map(m => m.project_id || (m.project && m.project.id)))
    openProjects.value = ids
  } catch(e) { milestones.value = [] }
}
watch(filterProject, load)

function openDialog(row) {
  editing.value = row||null
  if (row) { form.name=row.name||''; form.project_id=row.project_id; form.phase_id=row.phase_id||null; form.planned_date=row.planned_date||''; form.planned_end_date=row.planned_end_date||''; form.actual_date=row.actual_date||''; form.actual_end_date=row.actual_end_date||''; form.status=row.status||'pending'; form.is_key=row.is_key }
  else { form.name=''; form.project_id=null; form.phase_id=null; form.planned_date=''; form.planned_end_date=''; form.actual_date=''; form.actual_end_date=''; form.status='pending'; form.is_key=false }
  showDialog.value = true
}

async function save() {
  if (!form.name) { ElMessage.warning('请输入名称'); return }
  saving.value = true
  try {
    const pid = filterProject.value || form.project_id
    if (!pid) { ElMessage.warning('请选择项目'); saving.value = false; return }
    const p = {}
    for (const [k,v] of Object.entries({ name:form.name, phase_id:form.phase_id, planned_date:form.planned_date||null, planned_end_date:form.planned_end_date||null, actual_date:form.actual_date||null, actual_end_date:form.actual_end_date||null, status:form.status, is_key:form.is_key })) {
      p[k] = v === undefined ? null : v
    }
    if (editing.value) { await updateMilestone(editing.value.id, p); ElMessage.success('已更新') }
    else { await createMilestone(pid, p); ElMessage.success('已创建') }
    showDialog.value = false; editing.value = null; await load()
  } catch(e) {
    const d = e?.response?.data?.detail
    ElMessage.error('保存失败: ' + (Array.isArray(d) ? d.map(x=>x.msg).join('; ') : (typeof d==='string'?d:'未知错误')))
  } finally { saving.value = false }
}

async function syncFromReport() {
  const pid = filterProject.value
  console.log('syncFromReport called, pid=', pid)
  if (!pid) {
    ElMessage.warning('请先在「按项目」下拉中选择一个项目')
    return
  }
  showSyncDialog.value = true
  syncing.value = true
  syncSuggestions.value = []
  try {
    const reportsRes = await api.get(`/projects/${pid}/reports`, { params: { limit: 1 } })
    const reports = Array.isArray(reportsRes.data) ? reportsRes.data : (reportsRes.data?.items || [])
    if (!reports.length) {
      ElMessage.warning('该项目暂无周报')
      showSyncDialog.value = false
      return
    }
    const reportId = reports[0].id
    const r = await api.get(`/projects/${pid}/reports/${reportId}/sync-milestones`)
    syncSuggestions.value = r.data?.suggestions || []
    if (!syncSuggestions.value.length) {
      ElMessage.info('未检测到可同步的里程碑更新')
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e.message || '未知错误'
    ElMessage.error('同步失败: ' + detail)
    showSyncDialog.value = false
  } finally { syncing.value = false }
}

async function applySync() {
  const pid = filterProject.value
  if (!pid || !syncSuggestions.value.length) return
  applying.value = true
  try {
    const updates = []
    const createNew = []
    for (const s of syncSuggestions.value) {
      if (s.milestone_id) {
        const upd = { milestone_id: s.milestone_id, status: s.suggested_status }
        if (s.suggested_actual_date) upd.actual_date = s.suggested_actual_date
        if (s.suggested_end_date) upd.end_date = s.suggested_end_date
        updates.push(upd)
      } else {
        createNew.push({ name: s.matched_keyword, status: s.suggested_status })
      }
    }
    const r = await api.post(`/projects/${pid}/milestones/sync-apply`, { updates, create_new: createNew })
    ElMessage.success(`已更新 ${r.data?.updated?.length || 0} 个，新建 ${r.data?.created?.length || 0} 个里程碑`)
    showSyncDialog.value = false
    await load()
  } catch (e) {
    ElMessage.error('应用失败: ' + (e?.response?.data?.detail || e.message))
  } finally { applying.value = false }
}

async function deleteMs(ms) {
  try {
    await ElMessageBox.confirm(`删除里程碑"${ms.name}"？`, '确认删除', { type: 'warning' })
    await deleteMilestone(ms.id)
    ElMessage.success('已删除')
    await load()
  } catch {}
}
</script>

<style scoped>
.ms-page { max-width:100%; }

.ms-kpi-bar { display:flex; gap:2px; margin-bottom:16px; }
.ms-kpi { flex:1; background:#fff; border-radius:8px; padding:12px 16px; text-align:center; box-shadow:var(--shadow-sm); font-size:12px; color:var(--text-secondary); }
.ms-kpi-num { display:block; font-size:22px; font-weight:700; color:var(--text); }
.kpi-done .ms-kpi-num { color:#10b981; }
.kpi-progress .ms-kpi-num { color:#3b82f6; }
.kpi-overdue .ms-kpi-num { color:#ef4444; }
.kpi-upcoming .ms-kpi-num { color:#f59e0b; }

.ms-toolbar { display:flex; justify-content:space-between; margin-bottom:16px; background:#fff; padding:10px 16px; border-radius:8px; box-shadow:var(--shadow-sm); }

.ms-group { background:#fff; border-radius:8px; box-shadow:var(--shadow-sm); margin-bottom:8px; overflow:hidden; }
.ms-group-hdr { display:flex; align-items:center; gap:10px; padding:12px 16px; cursor:pointer; font-size:13px; border-bottom:1px solid #f3f4f6; }
.ms-group-hdr:hover { background:#f9fafb; }
.ms-arrow { font-size:12px; color:var(--text-muted); transition:transform .2s; flex-shrink:0; }
.ms-arrow.open { transform:rotate(90deg); }
.ms-proj-name { font-weight:600; color:var(--text); }
.ms-proj-code { font-size:11px; color:var(--text-muted); font-family:monospace; }
.ms-count { margin-left:auto; font-size:11px; color:var(--text-muted); }
.ms-progress-bar { width:60px; height:4px; background:#f3f4f6; border-radius:2px; overflow:hidden; }
.ms-progress-fill { height:100%; background:#3b82f6; border-radius:2px; transition:width .3s; }

.ms-phase { margin:0; }
.ms-phase-hdr { font-size:11px; color:var(--text-muted); padding:6px 16px 4px 42px; background:#fafafa; border-bottom:1px solid #f0f0f0; font-weight:500; }
.ms-item { display:flex; align-items:center; gap:8px; padding:7px 16px 7px 56px; font-size:13px; border-bottom:1px solid #fafafa; }
.ms-item:hover { background:#f9fafb; }
.ms-item.overdue { background:#fef2f2; }
.ms-name { flex:1; color:var(--text); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ms-date { font-size:11px; color:var(--text-muted); white-space:nowrap; }
.ms-date.overdue { color:#ef4444; font-weight:600; }
.ms-end { font-size:11px; color:var(--text-muted); }
.ms-status-tag { font-size:10px; flex-shrink:0; }

.ms-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.dot-completed { background:#10b981; }
.dot-in_progress { background:#3b82f6; }
.dot-pending { background:#d1d5db; }
.dot-overdue { background:#ef4444; }

.ms-empty { text-align:center; padding:60px; color:var(--text-muted); background:#fff; border-radius:8px; }
</style>
