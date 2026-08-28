<template>
  <div class="gtt-tab">
    <!-- 放行操作:按门分组 -->
    <el-collapse v-model="openGates" class="gate-collapse">
      <el-collapse-item v-for="g in gateGroups" :key="g.pgId" :name="g.pgId">
        <template #title>
          <div class="gate-title">
            <span class="gate-name">{{ g.gateLabel }}</span>
            <span class="gate-project">{{ g.projectName }}</span>
            <span class="gate-progress" :class="{ done: g.done }">{{ g.closedCount }}/{{ g.items.length }} 任务已完成</span>
            <el-tag :type="g.done ? 'success' : 'info'" size="small">{{ g.gateStatusLabel }}</el-tag>
            <el-button
              size="small" type="primary" style="margin-left:12px"
              :disabled="!g.done"
              :title="g.done ? '发起两级签核放行' : '需所有任务完成后才能发起放行'"
              @click.stop="openSignoffDialog(g)">发起放行</el-button>
          </div>
        </template>
        <div class="gate-body">
          <el-table :data="g.items" size="small">
            <el-table-column label="任务" min-width="200" prop="title" show-overflow-tooltip />
            <el-table-column label="负责人" width="100">
              <template #default="{ row }">{{ row.assignee_name || '—' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'closed' ? 'success' : row.status === 'in_progress' ? 'primary' : 'warning'" size="small">
                  {{ taskStatusLabel(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="截止日期" width="110">
              <template #default="{ row }">{{ row.due_date || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="90">
              <template #default="{ row }">
                <el-button v-if="row.status !== 'closed'" link size="small" type="success" @click="setTaskStatus(row, 'closed')">完成</el-button>
                <el-button v-else link size="small" @click="setTaskStatus(row, 'open')">重开</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-collapse-item>
    </el-collapse>
    <div v-if="!loading && !gateGroups.length" class="empty-hint">暂无门评审任务</div>

    <!-- 全部任务列表 -->
    <div class="task-section">
      <div class="task-head">
        <span class="section-title">全部任务</span>
        <el-select v-model="filters.project_id" placeholder="全部项目" clearable size="small" style="width:200px" @change="load">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="filters.phase_id" placeholder="全部阶段" clearable size="small" style="width:160px;margin-left:8px" @change="load">
          <el-option v-for="p in phases" :key="p.id" :label="`${p.code || ''} ${p.name}`" :value="p.id" />
        </el-select>
        <el-select v-model="filters.status" placeholder="全部状态" clearable size="small" style="width:120px;margin-left:8px" @change="load">
          <el-option label="待处理" value="open" />
          <el-option label="进行中" value="in_progress" />
          <el-option label="已完成" value="closed" />
        </el-select>
        <el-button size="small" style="margin-left:8px" @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="allTasks" size="small">
        <el-table-column label="项目" min-width="180" prop="project_name" show-overflow-tooltip />
        <el-table-column label="阶段/门" min-width="140">
          <template #default="{ row }">
            <span>{{ row.phase_name || '—' }}</span>
            <span v-if="row.gate_name" class="t-muted"> / {{ row.gate_name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="任务" min-width="200" prop="title" show-overflow-tooltip />
        <el-table-column label="负责人" width="100">
          <template #default="{ row }">{{ row.assignee_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'closed' ? 'success' : row.status === 'in_progress' ? 'primary' : 'warning'" size="small">
              {{ taskStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="截止日期" width="110">
          <template #default="{ row }">{{ row.due_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'closed'" link size="small" type="success" @click="setTaskStatus(row, 'closed')">完成</el-button>
            <el-button v-else link size="small" @click="setTaskStatus(row, 'open')">重开</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 发起放行弹窗 -->
    <el-dialog v-model="signoffVisible" title="发起阶段门放行签核" width="440">
      <p class="dialog-desc">项目「{{ signoffTarget?.projectName }}」{{ signoffTarget?.gateLabel }}：将创建两级签核，一级通过后由管理层复核，复核通过即放行该门。</p>
      <el-form label-width="110px" size="small">
        <el-form-item label="一级签核人" required>
          <el-select v-model="signoffForm.level1_signer_id" placeholder="选择签核人(项目负责人)" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="二级签核人" required>
          <el-select v-model="signoffForm.level2_signer_id" placeholder="选择签核人(管理层)" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="signoffVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="signoffSaving" @click="submitSignoff">发起签核</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getCrossProjectActionItems, initiateSignoff, updateActionItem } from '../../api/index.js'

const props = defineProps({
  projects: { type: Array, default: () => [] },
  phases: { type: Array, default: () => [] },
  members: { type: Array, default: () => [] },
})

const loading = ref(false)
const allTasks = ref([])
const filters = ref({ project_id: null, phase_id: null, status: null })
const openGates = ref([])
const signoffVisible = ref(false)
const signoffSaving = ref(false)
const signoffTarget = ref(null)
const signoffForm = ref({ level1_signer_id: null, level2_signer_id: null })

const gateGroups = computed(() => {
  const map = new Map()
  for (const t of allTasks.value) {
    if (!t.project_phase_gate_id) continue
    if (!map.has(t.project_phase_gate_id)) {
      map.set(t.project_phase_gate_id, {
        pgId: t.project_phase_gate_id, projectName: t.project_name,
        gateLabel: `${t.phase_name || ''}${t.gate_name ? ' · ' + t.gate_name : '门'}`,
        items: [], closedCount: 0,
        gateStatus: t.gate_status,
      })
    }
    map.get(t.project_phase_gate_id).items.push(t)
  }
  const groups = [...map.values()]
  for (const g of groups) {
    g.closedCount = g.items.filter(i => i.status === 'closed').length
    g.done = g.closedCount === g.items.length
    g.gateStatusLabel = { passed: '已放行', failed: '未通过', pending: '签核中' }[g.gateStatus] || '未放行'
  }
  return groups
})

function taskStatusLabel(s) {
  return { open: '待处理', in_progress: '进行中', closed: '已完成' }[s] || s
}

async function load() {
  loading.value = true
  try {
    const params = {}
    if (filters.value.project_id) params.project_id = filters.value.project_id
    if (filters.value.phase_id) params.phase_id = filters.value.phase_id
    if (filters.value.status) params.status = filters.value.status
    allTasks.value = (await getCrossProjectActionItems(params)).data || []
  } finally { loading.value = false }
}

async function setTaskStatus(row, status) {
  await updateActionItem(row.id, { status })
  ElMessage.success(status === 'closed' ? '任务已完成' : '任务已重开')
  await load()
}

function openSignoffDialog(g) {
  signoffTarget.value = g
  signoffForm.value = { level1_signer_id: null, level2_signer_id: null }
  signoffVisible.value = true
}

async function submitSignoff() {
  if (!signoffForm.value.level1_signer_id || !signoffForm.value.level2_signer_id) {
    ElMessage.warning('请选择两级签核人'); return
  }
  signoffSaving.value = true
  try {
    await initiateSignoff(signoffTarget.value.pgId, signoffForm.value)
    ElMessage.success('已发起放行签核,等待一级签核人处理')
    signoffVisible.value = false
    await load()
  } finally { signoffSaving.value = false }
}

onMounted(load)
</script>

<style scoped>
.gtt-tab { padding: 4px 0; }
.gate-collapse { margin-bottom: 12px; }
.gate-collapse :deep(.el-collapse-item__header) { background: var(--bg); border-radius: 6px; padding: 0 12px; }
.gate-title { display: flex; align-items: center; gap: 10px; width: 100%; }
.gate-name { font-weight: 600; font-size: 13px; }
.gate-project { font-size: 12px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 260px; }
.gate-progress { font-size: 12px; color: var(--text-secondary); }
.gate-progress.done { color: #10b981; font-weight: 600; }
.gate-body { padding: 4px 0; }
.task-section { margin-top: 4px; }
.task-head { display: flex; align-items: center; margin-bottom: 8px; }
.section-title { font-size: 13px; font-weight: 600; margin-right: 12px; }
.dialog-desc { font-size: 12px; color: var(--text-secondary); margin: 0 0 12px; }
.t-muted { color: var(--text-muted); }
.empty-hint { color: var(--text-muted); font-size: 12px; padding: 14px 4px; }
</style>
