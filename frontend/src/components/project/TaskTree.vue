<template>
  <div>
    <div class="card-header mb-md">
      <div style="display:flex;gap:8px">
        <el-select v-model="filterStatus" placeholder="状态筛选" clearable size="small" style="width:110px">
          <el-option label="待开始" value="pending" /><el-option label="进行中" value="in_progress" />
          <el-option label="已完成" value="completed" /><el-option label="阻塞" value="blocked" />
        </el-select>
        <el-select v-model="filterAssignee" placeholder="负责人筛选" clearable size="small" style="width:140px">
          <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </div>
      <div style="display:flex;gap:6px">
        <el-upload :action="importUrl" :headers="uploadHeaders" :show-file-list="false"
          accept=".xlsx,.xls" :on-success="onImportSuccess" :on-error="onImportError">
          <el-button size="small">📥 导入Excel</el-button>
        </el-upload>
        <el-button size="small" @click="downloadTemplate">📋 模板</el-button>
        <el-button type="primary" size="small" @click="openEdit()">
          <el-icon><Plus /></el-icon> 添加任务
        </el-button>
      </div>
    </div>

    <!-- Task tree -->
    <div v-if="flatTasks.length === 0" style="text-align:center;padding:40px;color:var(--text-muted)">
      暂无任务，点击"添加任务"创建WBS
    </div>

    <el-table v-else :data="displayTasks" stripe size="small" row-key="id" style="width:100%"
      :tree-props="{ children: 'children', hasChildren: 'hasChildren' }" default-expand-all>
      <el-table-column label="任务名称" min-width="260" show-overflow-tooltip>
        <template #default="{row}">
          <span :style="{ paddingLeft: (row._depth || 0) * 20 + 'px' }"></span>
          <span :class="{ 'task-done': row.status === 'completed' }">{{ row.name }}</span>
          <span v-if="row.children?.length" class="child-count">({{ row.children.length }})</span>
        </template>
      </el-table-column>
      <el-table-column label="负责人" width="95" show-overflow-tooltip>
        <template #default="{row}">{{ row.assignee?.name || '-' }}</template>
      </el-table-column>
      <el-table-column label="技术线" width="105" show-overflow-tooltip>
        <template #default="{row}">{{ row.line?.short_name || row.line?.name || '-' }}</template>
      </el-table-column>
      <el-table-column label="进度" width="150">
        <template #default="{row}">
          <div class="prog-cell">
            <el-progress :percentage="row.progress_pct || 0" :stroke-width="6" :show-text="false"
              :color="row.status==='blocked'?'#ef4444':row.progress_pct>=80?'#10b981':'#3b82f6'" />
            <span class="prog-text" :class="{ 'prog-red': row.status==='blocked' }">{{ row.progress_pct || 0 }}%</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="85" align="center">
        <template #default="{row}">
          <span class="tag" :class="statusCls(row.status)">{{ statusLabel(row.status) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="截止" width="110" show-overflow-tooltip>
        <template #default="{row}">{{ row.end_date || row.start_date || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150">
        <template #default="{row}">
          <el-button link size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" @click="openEdit({parent_id: row.id})">子任务</el-button>
          <el-popconfirm title="删除?" @confirm="delTask(row.id)">
            <template #reference><el-button link size="small" type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- Edit Dialog -->
    <el-dialog v-model="showDialog" :title="editing ? '编辑任务' : '添加任务'" width="620px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="任务名称" required>
          <el-input v-model="form.name" placeholder="如：定子铁芯电磁方案仿真" clearable />
        </el-form-item>
        <el-form-item label="父任务" v-if="!editing || form.parent_id">
          <el-select v-model="form.parent_id" clearable style="width:100%" placeholder="（顶级任务）">
            <el-option v-for="t in flatTasks" :key="t.id" :label="t.name" :value="t.id"
              :disabled="t.id === editing?.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="负责人">
              <el-select v-model="form.assignee_id" clearable style="width:100%">
                <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="技术线">
              <el-select v-model="form.line_id" clearable style="width:100%">
                <el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width:100%" @change="onStatusChange">
                <el-option label="待开始" value="pending" /><el-option label="进行中" value="in_progress" />
                <el-option label="已完成" value="completed" /><el-option label="阻塞" value="blocked" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="进度%">
              <el-input-number v-model="form.progress_pct" :min="0" :max="100" style="width:100%" size="small" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" style="width:100%">
                <el-option label="P1" value="P1" /><el-option label="P2" value="P2" /><el-option label="P3" value="P3" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="开始日期"><el-date-picker v-model="form.start_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="截止日期"><el-date-picker v-model="form.end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="showDialog=false">取消</el-button>
        <el-button type="primary" @click="saveTask" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })

const importUrl = computed(() => `/api/projects/${props.projectId}/tasks/import`)
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))

const tasks = ref([])
const members = ref([])
const lines = ref([])
const filterStatus = ref('')
const filterAssignee = ref('')
const showDialog = ref(false)
const editing = ref(null)
const saving = ref(false)

const form = reactive({ name: '', parent_id: null, assignee_id: null, line_id: null, phase_id: null,
  start_date: null, end_date: null, progress_pct: 0, status: 'pending', priority: 'P2' })

// Flatten tree for filtering
const flatTasks = computed(() => {
  const result = []
  function walk(list) { for (const t of list) { result.push(t); if (t.children) walk(t.children) } }
  walk(tasks.value)
  return result
})

// Filtered tree display
const displayTasks = computed(() => {
  if (!filterStatus.value && !filterAssignee.value) return tasks.value
  const filtered = flatTasks.value.filter(t => {
    if (filterStatus.value && t.status !== filterStatus.value) return false
    if (filterAssignee.value && t.assignee?.id !== filterAssignee.value) return false
    return true
  })
  // Rebuild tree for filtered items
  return rebuildTree(filtered)
})

function rebuildTree(list) {
  const map = new Map(list.map(t => [t.id, { ...t, children: [], _depth: 0 }]))
  const roots = []
  for (const t of map.values()) {
    if (t.parent_id && map.has(t.parent_id)) {
      map.get(t.parent_id).children.push(t)
      t._depth = (map.get(t.parent_id)._depth || 0) + 1
    } else {
      roots.push(t)
    }
  }
  return roots
}

let lastProgressBeforeCompleted = null

function onStatusChange(s) {
  if (s === 'completed') {
    lastProgressBeforeCompleted = form.progress_pct
    form.progress_pct = 100
  } else if (lastProgressBeforeCompleted !== null && form.progress_pct === 100) {
    form.progress_pct = lastProgressBeforeCompleted
    lastProgressBeforeCompleted = null
  }
}

function statusLabel(s) {
  const m = { pending: '待开始', in_progress: '进行中', completed: '已完成', blocked: '阻塞', cancelled: '已取消' }
  return m[s] || s
}
function statusCls(s) {
  return s === 'completed' ? 'tag-green' : s === 'in_progress' ? 'tag-blue' : s === 'blocked' ? 'tag-red' : 'tag-gray'
}

function onImportSuccess(res) { ElMessage.success(res.message || `导入成功`); load() }
function onImportError() { ElMessage.error('导入失败，请检查Excel格式') }
function downloadTemplate() {
  // Generate a simple template Excel
  const csv = '任务名称,父任务,负责人,技术线,阶段,开始日期,结束日期,进度%,状态\n系统设计,,张三,控制算法,方案设计阶段,2026-01-01,2026-03-01,50,进行中\n需求分析,系统设计,李四,测试验证,概念需求阶段,2026-01-01,2026-02-01,100,已完成'
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url; a.download = 'WBS任务导入模板.csv'; a.click()
  URL.revokeObjectURL(url)
}
onMounted(load)

async function load() {
  try {
    const [tRes, mRes, lRes] = await Promise.all([
      api.get(`/projects/${props.projectId}/tasks`),
      api.get('/team-members').catch(() => ({ data: [] })),
      api.get('/lookups/technical-lines').catch(() => ({ data: [] })),
    ])
    tasks.value = tRes.data || []
    members.value = mRes.data || []
    lines.value = lRes.data || []
  } catch (e) { tasks.value = [] }
}

function openEdit(row) {
  const isRealRow = row && row.id  // actual task row vs {parent_id: X} for subtask
  editing.value = isRealRow ? row : null
  form.name = isRealRow ? (row.name || '') : ''
  form.parent_id = row ? (row.parent_id || null) : null
  form.assignee_id = isRealRow ? (row.assignee_id || null) : null
  form.line_id = isRealRow ? (row.line_id || null) : null
  form.start_date = isRealRow ? (row.start_date || null) : null
  form.end_date = isRealRow ? (row.end_date || null) : null
  form.progress_pct = isRealRow ? (row.progress_pct || 0) : 0
  form.status = isRealRow ? (row.status || 'pending') : 'pending'
  lastProgressBeforeCompleted = null
  form.priority = isRealRow ? (row.priority || 'P2') : 'P2'
  showDialog.value = true
}

async function saveTask() {
  if (!form.name) { ElMessage.warning('请输入名称'); return }
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/tasks/${editing.value.id}`, { ...form })
    } else {
      await api.post(`/projects/${props.projectId}/tasks`, { ...form })
    }
    ElMessage.success('已保存'); showDialog.value = false; editing.value = null
    await load()
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}

async function delTask(id) {
  await api.delete(`/tasks/${id}`)
  ElMessage.success('已删除'); await load()
}
</script>

<style scoped>
.task-done { text-decoration: line-through; color: var(--text-muted); }
.child-count { color: var(--text-muted); font-size: 11px; margin-left: 4px; }
.prog-cell { display: flex; align-items: center; gap: 8px; }
.prog-cell .el-progress { flex: 1; }
.prog-text { font-size: 12px; color: var(--text-muted); white-space: nowrap; min-width: 34px; text-align: right; }
.prog-red { color: #ef4444; }
</style>
