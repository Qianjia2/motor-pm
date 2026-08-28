<template>
  <div class="issue-risk-page">
    <div class="page-header">
      <h1>问题风险管理</h1>
      <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon> 新增问题</el-button>
      <el-button type="success" @click="extractFromReports" :loading="extracting">
        <el-icon><MagicStick /></el-icon> 🤖 从周报提取
      </el-button>
    </div>

    <!-- Stats cards -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-num">{{ summary.total }}</div>
        <div class="stat-label">问题总数</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-num">{{ summary.high }}</div>
        <div class="stat-label">高严重度</div>
      </div>
      <div class="stat-card warning">
        <div class="stat-num">{{ summary.open }}</div>
        <div class="stat-label">待处理</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ topProjects.length }}</div>
        <div class="stat-label">涉及项目</div>
      </div>
    </div>

    <!-- view tabs -->
    <div class="view-tabs">
      <button :class="['tab-btn', {active: viewMode==='list'}]" @click="viewMode='list'">列表视图</button>
      <button :class="['tab-btn', {active: viewMode==='matrix'}]" @click="switchToMatrix">风险矩阵</button>
    </div>

    <!-- LIST VIEW -->
    <template v-if="viewMode==='list'">
    <!-- filters bar -->
    <div class="filters-bar">
      <el-input v-model="searchText" placeholder="搜索标题/描述..." clearable style="width:220px" @keyup.enter="fetchList" />
      <el-select v-model="filterSeverity" placeholder="严重度" clearable style="width:120px" @change="fetchList">
        <el-option label="🔴 高" value="高" />
        <el-option label="🟡 中" value="中" />
        <el-option label="⚪ 低" value="低" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable style="width:130px" @change="fetchList">
        <el-option label="未处理" value="open" />
        <el-option label="处理中" value="in_progress" />
        <el-option label="已解决" value="resolved" />
        <el-option label="已关闭" value="closed" />
      </el-select>
      <el-select v-model="filterType" placeholder="类型" clearable style="width:100px" @change="fetchList">
        <el-option label="问题" value="issue" />
        <el-option label="风险" value="risk" />
      </el-select>
      <el-select v-model="filterProjectId" placeholder="关联项目" clearable filterable style="width:200px" @change="fetchList">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-model="sortBy" style="width:130px" @change="fetchList">
        <el-option label="严重度优先" value="severity_desc" />
        <el-option label="最新优先" value="created_desc" />
        <el-option label="按项目" value="project" />
      </el-select>
      <el-button @click="fetchList">搜索</el-button>
    </div>

    <!-- table -->
    <el-table :data="items" stripe v-loading="loading" style="flex:1" @sort-change="onSortChange">
      <el-table-column label="严重度" width="80">
        <template #default="{row}">
          <el-tag :type="sevType(row.severity)" size="small" effect="dark">{{ row.severity || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="问题标题" min-width="220" show-overflow-tooltip />
      <el-table-column label="关联项目" width="170">
        <template #default="{row}">
          <span v-if="row.project_name" style="font-size:13px">{{ row.project_name }}</span>
          <span v-else style="color:var(--text-muted)">-</span>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="70">
        <template #default="{row}">
          <el-tag :type="row.type==='risk'?'warning':''" size="small" effect="plain">
            {{ row.type==='risk'?'风险':'问题' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{row}">
          <el-popover placement="bottom" :width="140" trigger="click">
            <template #reference>
              <el-tag :type="statusType(row.status)" size="small" style="cursor:pointer" @click.stop>
                {{ statusLabel(row.status) }} ▾
              </el-tag>
            </template>
            <div class="status-menu">
              <div v-for="s in statusOptions" :key="s.value" class="status-item"
                   :class="{active: row.status===s.value}"
                   @click.stop="changeStatus(row, s.value)">
                <span class="status-dot" :style="{background: s.color}"></span>
                {{ s.label }}
              </div>
            </div>
          </el-popover>
        </template>
      </el-table-column>
      <el-table-column prop="owner" label="责任人" width="90" />
      <el-table-column prop="risk_level" label="风险等级" width="90" />
      <el-table-column prop="created_at" label="创建日期" width="110" sortable="custom">
        <template #default="{row}">{{ row.created_at?.slice(0,10) }}</template>
      </el-table-column>
      <el-table-column label="来源" width="95">
        <template #default="{row}">
          <el-tag v-if="row.status==='pending_review'" type="warning" size="small" effect="dark">🤖 待审核</el-tag>
          <el-tag v-else-if="row.confidence && row.confidence>0" type="success" size="small" effect="plain">🤖 AI</el-tag>
          <span v-else-if="row.source==='project'" style="color:var(--primary);font-size:12px">项目</span>
          <span v-else style="color:var(--text-muted);font-size:12px">手动</span>
        </template>
      </el-table-column>
      <el-table-column label="置信度" width="75" sortable="custom" prop="confidence">
        <template #default="{row}">
          <span v-if="row.confidence" :style="{color: row.confidence>=80?'#16a34a':row.confidence>=60?'#d97706':'#94a3b8',fontWeight:600}">{{ row.confidence }}%</span>
          <span v-else style="color:var(--text-muted)">-</span>
        </template>
      </el-table-column>
      <el-table-column label="原文引用" width="60">
        <template #default="{row}">
          <el-popover v-if="row.source_quote" placement="left" :width="320" trigger="hover">
            <template #reference>
              <el-button link type="info" size="small">📄</el-button>
            </template>
            <div style="font-size:13px;line-height:1.7;color:#475569;white-space:pre-wrap">{{ row.source_quote }}</div>
          </el-popover>
          <span v-else style="color:var(--text-muted)">-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{row}">
          <el-button v-if="row.status==='pending_review'" link type="success" size="small" @click="approveRisk(row)">审核</el-button>
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    </template>

    <!-- MATRIX VIEW -->
    <div v-if="viewMode==='matrix'" class="matrix-container">
      <div class="matrix-header">
        <span>影响（横轴）→ 可能性（纵轴）</span>
        <span class="matrix-legend">
          <span class="leg-dot" style="background:#dc2626"></span> 高风险
          <span class="leg-dot" style="background:#f59e0b"></span> 中风险
          <span class="leg-dot" style="background:#22c55e"></span> 低风险
        </span>
      </div>
      <div class="matrix-grid">
        <div class="matrix-corner"></div>
        <div v-for="il in impactLevels" :key="il" class="matrix-col-hdr">{{ il }}</div>
        <template v-for="pl in probLevels" :key="pl">
          <div class="matrix-row-hdr">{{ pl }}</div>
          <div v-for="il in impactLevels" :key="il"
               :class="['matrix-cell', cellClass(pl, il)]"
               @click="showCellDetail(pl, il)">
            <span class="cell-count">{{ cellCount(pl, il) }}</span>
          </div>
        </template>
      </div>
      <div class="matrix-axis-label" style="text-align:center;margin-top:4px">影响 →</div>
      <div class="matrix-y-axis">
        <div class="matrix-axis-label">可<br>能<br>性</div>
        <div style="flex:1"></div>
      </div>

      <!-- cell detail popover -->
      <el-dialog v-model="cellDialog" :title="`${cellProb} × ${cellImp} (${cellCount(cellProb,cellImp)}项)`" width="520px">
        <div v-for="item in cellItems" :key="item.id" class="cell-item">
          <div class="cell-item-title">{{ item.title }}</div>
          <div class="cell-item-meta">
            <el-tag :type="sevType(item.severity)" size="small">{{ item.severity }}</el-tag>
            <span>{{ item.project_name }}</span>
            <span>{{ item.owner }}</span>
            <el-tag :type="statusType(item.status)" size="small">{{ statusLabel(item.status) }}</el-tag>
          </div>
        </div>
        <div v-if="cellItems.length===0" style="color:var(--text-muted);text-align:center">该区域暂无问题</div>
      </el-dialog>
    </div>

    <!-- create/edit dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑问题' : '新增问题'" width="560px" destroy-on-close>
      <el-form :model="form" label-width="90px">
        <el-form-item label="问题标题" required>
          <el-input v-model="form.title" placeholder="请输入问题标题" />
        </el-form-item>
        <el-form-item label="问题描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="详细描述问题..." />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.type">
            <el-radio value="issue">问题</el-radio>
            <el-radio value="risk">风险</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="严重度" required>
          <el-select v-model="form.severity" style="width:100%">
            <el-option label="🔴 高 — 需立即处理" value="高" />
            <el-option label="🟡 中 — 本周内处理" value="中" />
            <el-option label="⚪ 低 — 持续关注" value="低" />
          </el-select>
        </el-form-item>
        <el-form-item label="概率">
          <el-select v-model="form.probability" style="width:100%">
            <el-option label="很低" value="很低" />
            <el-option label="低" value="低" />
            <el-option label="中" value="中" />
            <el-option label="高" value="高" />
            <el-option label="很高" value="很高" />
          </el-select>
        </el-form-item>
        <el-form-item label="影响">
          <el-select v-model="form.impact" style="width:100%">
            <el-option label="很低" value="很低" />
            <el-option label="低" value="低" />
            <el-option label="中" value="中" />
            <el-option label="高" value="高" />
            <el-option label="很高" value="很高" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联项目" required>
          <el-select v-model="form.project_id" filterable placeholder="选择项目..." style="width:100%" @change="onProjectChange">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="负责人">
          <el-input v-model="form.owner" placeholder="负责人姓名" />
        </el-form-item>
        <el-form-item label="风险等级">
          <el-select v-model="form.risk_level" style="width:100%" clearable>
            <el-option label="P0 — 致命" value="P0" />
            <el-option label="P1 — 严重" value="P1" />
            <el-option label="P2 — 一般" value="P2" />
            <el-option label="P3 — 轻微" value="P3" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="未处理" value="open" />
            <el-option label="处理中" value="in_progress" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已关闭" value="closed" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible=false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">{{ isEdit ? '保存' : '创建' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, MagicStick } from '@element-plus/icons-vue'
import api from '../api/index.js'

const items = ref([])
const projects = ref([])
const summary = reactive({ total: 0, high: 0, open: 0 })
const loading = ref(false)
const saving = ref(false)
const extracting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref('')

const searchText = ref('')
const filterSeverity = ref('')
const filterStatus = ref('')
const filterProjectId = ref(null)
const filterType = ref('')
const sortBy = ref('severity_desc')
const viewMode = ref('list')

// Matrix
const matrixItems = ref([])
const cellDialog = ref(false)
const cellProb = ref('')
const cellImp = ref('')
const probLevels = ['很高', '高', '中', '低', '很低']
const impactLevels = ['很低', '低', '中', '高', '很高']

const statusOptions = [
  { label: '未处理', value: 'open', color: '#f56c6c' },
  { label: '处理中', value: 'in_progress', color: '#e6a23c' },
  { label: '已解决', value: 'resolved', color: '#67c23a' },
  { label: '已关闭', value: 'closed', color: '#909399' },
]

const form = reactive({
  title: '', description: '', type: 'issue', severity: '中',
  probability: '中', impact: '中',
  project_id: null, project_name: '', owner: '', risk_level: '', status: 'open'
})

const topProjects = computed(() => {
  const map = {}
  const arr = Array.isArray(items.value) ? items.value : []
  arr.forEach(i => {
    if (i.project_name) map[i.project_name] = (map[i.project_name] || 0) + 1
  })
  return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 5)
})

onMounted(() => { fetchList(); loadProjects(); fetchSummary() })

async function loadProjects() {
  try { const r = await api.get('/issue-risks-projects'); projects.value = r.data } catch (e) {}
}

async function fetchSummary() {
  try {
    const r = await api.get('/issue-risks/summary')
    Object.assign(summary, r.data)
  } catch (e) {}
}

async function fetchList() {
  loading.value = true
  try {
    const params = { sort: sortBy.value }
    if (filterSeverity.value) params.severity = filterSeverity.value
    if (filterStatus.value) params.status = filterStatus.value
    if (filterProjectId.value) params.project_id = filterProjectId.value
    if (filterType.value) params.type = filterType.value
    if (searchText.value) params.search = searchText.value
    const r = await api.get('/issue-risks', { params })
    items.value = Array.isArray(r.data) ? r.data : []
    fetchSummary()
  } catch (e) { items.value = []; ElMessage.error('加载失败') }
  finally { loading.value = false }
}

function onSortChange({ prop, order }) {
  if (prop === 'created_at') sortBy.value = order === 'descending' ? 'created_desc' : 'created_desc'
  fetchList()
}

function onProjectChange(val) {
  const p = projects.value.find(x => x.id === val)
  form.project_name = p ? p.name : ''
}

function resetForm() {
  form.title = ''; form.description = ''; form.type = 'issue'; form.severity = '中'
  form.probability = '中'; form.impact = '中'
  form.project_id = null; form.project_name = ''; form.owner = ''; form.risk_level = ''; form.status = 'open'
}

function openCreate() { isEdit.value = false; editId.value = ''; resetForm(); dialogVisible.value = true }

function openEdit(row) {
  isEdit.value = true; editId.value = row.id
  form.title = row.title; form.description = row.description || ''
  form.type = row.type || 'issue'; form.severity = row.severity || '中'
  form.probability = row.probability || '中'; form.impact = row.impact || '中'
  form.project_id = row.project_id; form.project_name = row.project_name || ''
  form.owner = row.owner || ''; form.risk_level = row.risk_level || ''; form.status = row.status || 'open'
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.title.trim()) { ElMessage.warning('请输入问题标题'); return }
  if (!form.project_id) { ElMessage.warning('请选择关联项目'); return }
  saving.value = true
  try {
    if (isEdit.value) {
      await api.put(`/issue-risks/${editId.value}`, form)
      ElMessage.success('已更新')
    } else {
      await api.post('/issue-risks', form)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    fetchList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally { saving.value = false }
}

async function extractFromReports() {
  try {
    await ElMessageBox.confirm(
      'AI将分析所有项目的周报内容（阻塞项、进展描述等），自动提取潜在风险和问题。确认？',
      '从周报提取风险', { confirmButtonText: '开始提取', type: 'info' }
    )
    extracting.value = true
    const r = await api.post('/risks/extract-from-reports', {}, { timeout: 180000 })
    ElMessage.success(r.data.message || `已提取 ${r.data.extracted} 条`)
    fetchList()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('提取失败: ' + (e.response?.data?.detail || e.message))
  } finally { extracting.value = false }
}

async function changeStatus(row, newStatus) {
  if (row.status === newStatus) return
  try {
    await api.put(`/issue-risks/${row.id}`, { status: newStatus })
    row.status = newStatus
    ElMessage.success(`状态已更新为「${statusLabel(newStatus)}」`)
    fetchSummary()
  } catch (e) {
    ElMessage.error('更新失败: ' + (e.response?.data?.detail || e.message))
  }
}

// ── Matrix functions ──

const probScore = p => ({'很低':1,'低':2,'中':3,'高':4,'很高':5}[p]||3)
const impactScore = i => ({'很低':1,'低':2,'中':3,'高':4,'很高':5}[i]||3)

function cellCount(prob, imp) {
  const arr = Array.isArray(matrixItems.value) ? matrixItems.value : []
  return arr.filter(item => item.probability===prob && item.impact===imp).length
}

function cellClass(prob, imp) {
  const s = probScore(prob) * impactScore(imp)
  if (s >= 20) return 'cell-critical'
  if (s >= 12) return 'cell-high'
  if (s >= 6) return 'cell-medium'
  return 'cell-low'
}

const cellItems = computed(() => {
  const arr = Array.isArray(matrixItems.value) ? matrixItems.value : []
  return arr.filter(item => item.probability===cellProb.value && item.impact===cellImp.value)
})

async function switchToMatrix() {
  viewMode.value = 'matrix'
  try {
    const r = await api.get('/issue-risks/matrix')
    matrixItems.value = Array.isArray(r.data) ? r.data : []
  } catch (e) { matrixItems.value = Array.isArray(items.value) ? items.value : [] }
}

function showCellDetail(prob, imp) {
  cellProb.value = prob; cellImp.value = imp
  cellDialog.value = true
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.title}」？`, '确认', { type: 'warning' })
    await api.delete(`/issue-risks/${row.id}`)
    ElMessage.success('已删除')
    fetchList()
  } catch (e) {}
}

async function approveRisk(row) {
  try {
    await api.put(`/issue-risks/${row.id}`, { status: 'open' })
    ElMessage.success('已审核通过，状态改为未处理')
    fetchList()
  } catch (e) {}
}

function sevType(v) { return { '高': 'danger', '中': 'warning', '低': 'info' }[v] || '' }
function statusType(v) { return { 'open': 'danger', 'in_progress': 'warning', 'resolved': 'success', 'closed': 'info', 'pending_review': 'warning' }[v] || '' }
function statusLabel(v) { return { 'open': '未处理', 'in_progress': '处理中', 'resolved': '已解决', 'closed': '已关闭', 'pending_review': '待审核' }[v] || v }
</script>

<style scoped>
.issue-risk-page { display:flex; flex-direction:column; height:100%; padding:24px; gap:16px; }
.page-header { display:flex; justify-content:space-between; align-items:center; }
.page-header h1 { font-size:20px; font-weight:700; margin:0; }

.stats-row { display:flex; gap:16px; }
.stat-card { flex:1; background:#fff; border-radius:8px; padding:16px 20px; border:1px solid var(--border); }
.stat-card.danger { border-left:4px solid var(--danger); }
.stat-card.warning { border-left:4px solid var(--warning); }
.stat-num { font-size:28px; font-weight:700; color:var(--text); line-height:1.2; }
.stat-label { font-size:13px; color:var(--text-muted); margin-top:4px; }

.filters-bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }

.status-menu { display:flex; flex-direction:column; }
.status-item { padding:8px 12px; cursor:pointer; border-radius:4px; display:flex; align-items:center; gap:8px; font-size:13px; }
.status-item:hover { background:var(--bg); }
.status-item.active { background:var(--primary-light); color:var(--primary); font-weight:600; }
.status-dot { width:8px; height:8px; border-radius:50%; flex-shrink:0; }

/* tabs */
.view-tabs { display:flex; gap:0; }
.tab-btn { padding:8px 20px; border:1px solid var(--border); background:#fff; cursor:pointer; font-size:13px; color:var(--text-secondary); }
.tab-btn:first-child { border-radius:6px 0 0 6px; }
.tab-btn:last-child { border-radius:0 6px 6px 0; }
.tab-btn.active { background:var(--primary); color:#fff; border-color:var(--primary); }

/* matrix */
.matrix-container { flex:1; display:flex; flex-direction:column; align-items:center; }
.matrix-header { display:flex; justify-content:space-between; width:100%; max-width:600px; margin-bottom:12px; font-size:13px; color:var(--text-muted); }
.matrix-legend { display:flex; gap:12px; align-items:center; }
.leg-dot { width:10px; height:10px; border-radius:2px; display:inline-block; }
.matrix-grid { display:grid; grid-template-columns:80px repeat(5, 1fr); gap:3px; max-width:600px; width:100%; }
.matrix-corner { background:transparent; }
.matrix-col-hdr, .matrix-row-hdr { font-size:12px; font-weight:600; color:var(--text-muted); display:flex; align-items:center; justify-content:center; padding:4px; }
.matrix-row-hdr { justify-content:flex-end; padding-right:8px; }
.matrix-cell { aspect-ratio:1; border-radius:6px; display:flex; align-items:center; justify-content:center; cursor:pointer; transition:all .15s; min-height:56px; }
.matrix-cell:hover { transform:scale(1.05); box-shadow:0 2px 8px rgba(0,0,0,.15); }
.cell-critical { background:#fecaca; color:#991b1b; }
.cell-high { background:#fed7aa; color:#9a3412; }
.cell-medium { background:#fef08a; color:#854d0e; }
.cell-low { background:#dcfce7; color:#166534; }
.cell-count { font-size:18px; font-weight:700; }

.cell-item { padding:10px 0; border-bottom:1px solid var(--border); }
.cell-item:last-child { border-bottom:none; }
.cell-item-title { font-size:14px; font-weight:600; margin-bottom:4px; }
.cell-item-meta { display:flex; gap:8px; align-items:center; font-size:12px; color:var(--text-muted); }

.matrix-axis-label { font-size:11px; color:var(--text-muted); writing-mode:vertical-rl; }
.matrix-y-axis { position:absolute; left:0; top:50%; display:flex; flex-direction:column; align-items:center; }
</style>
