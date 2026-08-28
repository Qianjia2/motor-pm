<template>
  <div class="gst-tab">
    <div class="toolbar">
      <el-radio-group v-model="scope" size="small">
        <el-radio-button value="mine">待我签核</el-radio-button>
        <el-radio-button value="all">全部记录</el-radio-button>
      </el-radio-group>
      <el-select v-if="scope === 'all'" v-model="filters.project_id" placeholder="全部项目" clearable size="small" style="width:200px;margin-left:12px" @change="loadAll">
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-if="scope === 'all'" v-model="filters.status" placeholder="全部状态" clearable size="small" style="width:120px;margin-left:8px" @change="loadAll">
        <el-option label="待签核" value="pending" />
        <el-option label="已通过" value="approved" />
        <el-option label="已驳回" value="rejected" />
      </el-select>
      <el-button v-if="isAdmin" type="primary" size="small" style="margin-left:auto" @click="openInit">+ 发起签核</el-button>
      <el-button size="small" style="margin-left:8px" @click="scope === 'mine' ? loadMine() : loadAll()">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" size="small">
      <el-table-column label="项目" min-width="180" prop="project_name" show-overflow-tooltip />
      <el-table-column label="阶段门" min-width="150">
        <template #default="{ row }">
          <span>{{ row.phase_name || '—' }}</span>
          <span v-if="row.gate_name" class="t-muted"> / {{ row.gate_name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="签核级别" width="100">
        <template #default="{ row }">
          <el-tag :type="row.level === 1 ? 'primary' : 'warning'" size="small">
            {{ row.level === 1 ? '一级·负责人' : '二级·管理层' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="签核人" width="100">
        <template #default="{ row }">{{ row.signer_name || '—' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === 'approved' ? 'success' : row.status === 'rejected' ? 'danger' : 'warning'" size="small">
            {{ { pending: '待签核', approved: '已通过', rejected: '已驳回' }[row.status] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="签核时间" width="150">
        <template #default="{ row }">{{ fmtTime(row.signed_at) }}</template>
      </el-table-column>
      <el-table-column label="意见" min-width="140" prop="comment" show-overflow-tooltip />
      <el-table-column label="操作" width="205" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending' && canAct(row)">
            <el-button link size="small" type="success" @click="openAction(row, 'approve')">通过</el-button>
            <el-button link size="small" type="danger" @click="openAction(row, 'reject')">驳回</el-button>
          </template>
          <span v-else-if="!isAdmin && !(row.status === 'pending' && canWithdraw(row))" class="t-muted">—</span>
          <el-button v-if="row.status === 'pending' && canWithdraw(row)" link size="small" type="warning" @click="withdrawSignoff(row)">撤回</el-button>
          <el-button v-if="isAdmin" link size="small" type="danger" @click="removeSignoff(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!loading && !rows.length" class="empty-hint">
      {{ scope === 'mine' ? '暂无待你签核的记录' : '暂无签核记录' }}
    </div>

    <el-dialog v-model="actionVisible" :title="actionType === 'approve' ? '签核通过' : '签核驳回'" width="460">
      <p class="dialog-desc">项目「{{ actionRow?.project_name }}」{{ actionRow?.phase_name }}{{ actionRow?.gate_name ? ' · ' + actionRow.gate_name : '' }}，{{ actionType === 'approve' ? '通过后自动进入下一级签核；二级通过即放行该门。通过前系统会校验该阶段必需交付物均已批准，未达标将无法通过。' : '驳回后该门标记为未通过。' }}</p>
      <div v-if="actionRow?.project_id" class="audit-wrap">
        <GateDeliverableAudit :project-id="actionRow.project_id" :phase-id="actionRow.phase_id" />
      </div>
      <el-input v-model="comment" type="textarea" :rows="3" :placeholder="actionType === 'approve' ? '签核意见(可选)' : '驳回原因(必填)'" />
      <template #footer>
        <el-button size="small" @click="actionVisible = false">取消</el-button>
        <el-button size="small" :type="actionType === 'approve' ? 'primary' : 'danger'" :loading="acting" @click="submitAction">
          {{ actionType === 'approve' ? '确认通过' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 发起两级签核 -->
    <el-dialog v-model="initVisible" title="发起阶段门两级签核" width="500px">
      <el-form :model="initForm" label-width="100px">
        <el-form-item label="项目" required>
          <el-select v-model="initForm.project_id" filterable placeholder="选择项目" style="width:100%" @change="onInitProjectChange">
            <el-option v-for="p in projects" :key="p.id" :label="`${p.code || ''} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="阶段门" required>
          <el-select v-model="initForm.pg_id" placeholder="选择进行中且未放行的门" style="width:100%">
            <el-option v-for="pg in initGates" :key="pg.id" :label="`${pg.phase?.code || ''} ${pg.phase?.name || ''} · ${pg.gate?.name || ''}`" :value="pg.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="交付物审核" v-if="initForm.pg_id">
          <GateDeliverableAudit :project-id="initForm.project_id" :phase-id="initPgPhaseId" @change="auditOk = $event" />
        </el-form-item>
        <el-form-item label="一级签核人" required>
          <el-select v-model="initForm.level1_signer_id" filterable placeholder="选择一级签核人" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="二级签核人" required>
          <el-select v-model="initForm.level2_signer_id" filterable placeholder="选择二级签核人" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <div style="font-size:12px;color:#909399;padding-left:100px">流程：一级通过后进入二级，二级通过后该门自动放行</div>
      </el-form>
      <template #footer>
        <el-button size="small" @click="initVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="initLoading" @click="doInitiate">发起</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api/index.js'
import { getMySignoffs, getSignoffs, approveSignoff, rejectSignoff, deleteSignoff, initiateSignoff } from '../../api/index.js'
import { useAuthStore } from '../../stores/auth.js'
import GateDeliverableAudit from './GateDeliverableAudit.vue'

const auth = useAuthStore()

const props = defineProps({
  projects: { type: Array, default: () => [] },
  members: { type: Array, default: () => [] },
  currentMemberId: { type: Number, default: null },
  isAdmin: { type: Boolean, default: false },
})

const scope = ref('mine')
const loading = ref(false)
const rows = ref([])
const filters = ref({ project_id: null, status: null })
const actionVisible = ref(false)
const acting = ref(false)
const actionType = ref('approve')
const actionRow = ref(null)
const comment = ref('')

function canAct(row) {
  return props.isAdmin || (props.currentMemberId && row.signer_id === props.currentMemberId)
}
function fmtTime(t) { return t ? t.replace('T', ' ').slice(0, 16) : '—' }

async function loadMine() {
  loading.value = true
  try { rows.value = (await getMySignoffs()).data || [] } finally { loading.value = false }
}
async function loadAll() {
  loading.value = true
  try {
    const params = {}
    if (filters.value.project_id) params.project_id = filters.value.project_id
    if (filters.value.status) params.status = filters.value.status
    rows.value = (await getSignoffs(params)).data || []
  } finally { loading.value = false }
}

function openAction(row, type) {
  actionRow.value = row
  actionType.value = type
  comment.value = ''
  actionVisible.value = true
}
async function submitAction() {
  if (actionType.value === 'reject' && !comment.value.trim()) {
    ElMessage.warning('请填写驳回原因'); return
  }
  acting.value = true
  try {
    if (actionType.value === 'approve') await approveSignoff(actionRow.value.id, { comment: comment.value })
    else await rejectSignoff(actionRow.value.id, { comment: comment.value })
    ElMessage.success(actionType.value === 'approve' ? '已签核通过' : '已驳回')
    actionVisible.value = false
    await Promise.all([loadMine(), loadAll()])
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败，请重试')
  } finally { acting.value = false }
}

function canWithdraw(row) {
  return props.isAdmin || (row.initiated_by && row.initiated_by === auth.username)
}

async function withdrawSignoff(row) {
  try {
    await ElMessageBox.confirm(
      `确定撤回项目「${row.project_name}」${row.phase_name || ''}${row.gate_name ? ' · ' + row.gate_name : ''} 的签核流程？撤回后该门全部签核记录将删除并重置为未放行，可重新发起。`,
      '撤回签核流程', { type: 'warning', confirmButtonText: '撤回', cancelButtonText: '取消', confirmButtonClass: 'el-button--warning' })
  } catch { return }
  try {
    await api.post(`/gate-reviews/${row.project_phase_gate_id}/withdraw`)
    ElMessage.success('已撤回签核流程，可重新发起')
    await Promise.all([loadMine(), loadAll()])
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '撤回失败，请重试')
  }
}

async function removeSignoff(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除项目「${row.project_name}」${row.phase_name || ''}${row.gate_name ? ' · ' + row.gate_name : ''} 发起的签核流程？将删除该门全部签核记录，已放行/未通过的门将重置为未放行。`,
      '删除签核记录', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    await deleteSignoff(row.id)
    ElMessage.success('已删除签核记录')
    await Promise.all([loadMine(), loadAll()])
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败，请重试')
  }
}

watch(scope, (v) => { v === 'mine' ? loadMine() : loadAll() }, { immediate: true })

// ── 发起两级签核 ──
const initVisible = ref(false)
const initLoading = ref(false)
const initGates = ref([])
const initForm = reactive({ project_id: null, pg_id: null, level1_signer_id: null, level2_signer_id: null })
const auditOk = ref(false)

const initPgPhaseId = computed(() => initGates.value.find(g => g.id === initForm.pg_id)?.phase_id || null)

function openInit() {
  Object.assign(initForm, { project_id: null, pg_id: null, level1_signer_id: null, level2_signer_id: null })
  initGates.value = []
  auditOk.value = false
  initVisible.value = true
}
async function onInitProjectChange() {
  initForm.pg_id = null
  initGates.value = []
  auditOk.value = false
  if (!initForm.project_id) return
  try {
    const res = await api.get(`/projects/${initForm.project_id}`)
    const pgs = res.data.phase_gates || []
    initGates.value = pgs.filter(pg => pg.status === 'in_progress' && pg.gate_status !== 'passed' && pg.gate)
  } catch (e) {}
}
async function doInitiate() {
  if (!initForm.project_id || !initForm.pg_id) { ElMessage.warning('请选择项目和阶段门'); return }
  if (!initForm.level1_signer_id || !initForm.level2_signer_id) { ElMessage.warning('请选择两级签核人'); return }
  if (!auditOk.value) { ElMessage.warning('该门必需交付物未全部批准，暂不能发起签核'); return }
  initLoading.value = true
  try {
    await initiateSignoff(initForm.pg_id, { level1_signer_id: initForm.level1_signer_id, level2_signer_id: initForm.level2_signer_id })
    ElMessage.success('已发起两级签核')
    initVisible.value = false
    await loadAll()
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '发起失败')
  } finally { initLoading.value = false }
}
</script>

<style scoped>
.gst-tab { padding: 4px 0; }
.toolbar { display: flex; align-items: center; margin-bottom: 10px; }
.dialog-desc { font-size: 12px; color: var(--text-secondary); margin: 0 0 10px; }
.audit-wrap { margin-bottom: 10px; }
.t-muted { color: var(--text-muted); }
.empty-hint { color: var(--text-muted); font-size: 12px; padding: 14px 4px; }
</style>
