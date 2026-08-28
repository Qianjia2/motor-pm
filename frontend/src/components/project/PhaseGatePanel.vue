<template>
  <div>
    <el-form :model="form" label-width="100px">
      <el-divider content-position="left">基本信息</el-divider>
      <el-form-item label="阶段状态">
        <el-select v-model="form.status" style="width:100%">
          <el-option label="未开始" value="not_started" />
          <el-option label="进行中" value="in_progress" />
          <el-option label="已完成" value="completed" :disabled="form.gate_status !== 'passed' && form.gate_status !== 'waived' && form.status !== 'completed'" />
          <el-option label="已跳过" value="skipped" />
        </el-select>
        <div class="field-hint" v-if="form.gate_status !== 'passed' && form.gate_status !== 'waived'">「已完成」需该门径评审通过（两级签核放行）后自动完成，不可直接勾选</div>
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="计划开始">
            <el-date-picker v-model="form.planned_start_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="计划结束">
            <el-date-picker v-model="form.planned_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="实际开始">
            <el-date-picker v-model="form.actual_start_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="实际结束">
            <el-date-picker v-model="form.actual_end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">门径评审</el-divider>
      <el-form-item label="评审状态">
        <el-select v-model="form.gate_status" style="width:100%">
          <el-option label="待评审" value="pending" />
          <el-option label="已豁免" value="waived" />
        </el-select>
        <div class="field-hint">已通过/未通过由两级签核流程自动更新，不可手动修改</div>
      </el-form-item>
      <el-form-item label="评审日期">
        <el-date-picker v-model="form.gate_review_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="评审备注">
        <el-input v-model="form.gate_review_notes" type="textarea" :rows="3" placeholder="评审意见、问题记录" />
      </el-form-item>

      <div style="text-align:right; margin-bottom:12px">
        <el-button @click="$emit('cancel')">取消</el-button>
        <el-button type="primary" @click="$emit('save', form)">保存</el-button>
        <el-button v-if="form.gate" @click="openSignoff">发起两级签核</el-button>
      </div>
    </el-form>

    <!-- 发起两级签核 -->
    <el-dialog v-model="signoffVisible" title="发起阶段门两级签核" width="520px">
      <el-form :model="signoffForm" label-width="110px">
        <el-form-item label="交付物审核">
          <GateDeliverableAudit :project-id="projectId" :phase-id="props.phaseGate.phase_id" @change="auditOk = $event" />
        </el-form-item>
        <el-form-item label="一级签核人" required>
          <el-select v-model="signoffForm.level1_signer_id" filterable placeholder="选择一级签核人" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="二级签核人" required>
          <el-select v-model="signoffForm.level2_signer_id" filterable placeholder="选择二级签核人" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <div style="font-size:12px;color:#909399;padding-left:110px">签核流程：一级通过后二级审批，二级通过后该门自动放行；发起前需该阶段必需交付物全部批准</div>
      </el-form>
      <template #footer>
        <el-button @click="signoffVisible = false">取消</el-button>
        <el-button type="primary" :loading="signoffLoading" :disabled="!auditOk" @click="doInitiateSignoff">发起</el-button>
      </template>
    </el-dialog>

    <!-- Action Items -->
    <el-divider content-position="left">
      评审待办 ({{ actionItems.length }})
      <el-button type="primary" size="small" link @click="showAddDialog = true" style="margin-left:8px">+ 新增</el-button>
    </el-divider>

    <div v-if="actionItems.length === 0" style="color:#909399;text-align:center;padding:16px">暂无评审待办</div>

    <div v-for="item in actionItems" :key="item.id" class="action-item-row">
      <el-tag :type="item.status === 'closed' ? 'success' : (item.status === 'in_progress' ? 'warning' : 'info')" size="small">
        {{ item.status === 'closed' ? '已关闭' : (item.status === 'in_progress' ? '处理中' : '待处理') }}
      </el-tag>
      <span style="flex:1;margin:0 8px;font-size:13px">{{ item.title }}</span>
      <span style="font-size:11px;color:#909399;margin-right:8px" v-if="item.assignee_name">{{ item.assignee_name }}</span>
      <span style="font-size:11px;color:#909399;margin-right:8px" v-if="item.due_date">{{ item.due_date }}</span>
      <el-button link size="small" @click="editItem(item)" v-if="item.status !== 'closed'">编辑</el-button>
      <el-button link size="small" type="success" @click="closeItem(item)" v-if="item.status !== 'closed'">关闭</el-button>
      <el-button link size="small" type="danger" @click="deleteItem(item)">删除</el-button>
    </div>

    <!-- Add / Edit Dialog -->
    <el-dialog v-model="showAddDialog" :title="editingItem ? '编辑评审待办' : '新增评审待办'" width="500px">
      <el-form :model="itemForm" label-width="80px">
        <el-form-item label="标题" required>
          <el-input v-model="itemForm.title" placeholder="待办事项描述" />
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="itemForm.assignee_id" clearable style="width:100%" placeholder="选择负责人">
            <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止日期">
          <el-date-picker v-model="itemForm.due_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="itemForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddDialog = false">取消</el-button>
        <el-button type="primary" @click="saveItem">保存</el-button>
      </template>
    </el-dialog>

    <!-- Close Dialog -->
    <el-dialog v-model="showCloseDialog" title="关闭待办 — 填写验证结果" width="500px">
      <el-form-item label="解决说明">
        <el-input v-model="closeForm.resolution" type="textarea" :rows="3" placeholder="描述如何解决的" />
      </el-form-item>
      <template #footer>
        <el-button @click="showCloseDialog = false">取消</el-button>
        <el-button type="primary" @click="doCloseItem">确认关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, watch, ref } from 'vue'
import api from '../../api/index.js'
import { ElMessage } from 'element-plus'
import GateDeliverableAudit from '../gate-review/GateDeliverableAudit.vue'

const props = defineProps({
  phaseGate: { type: Object, default: () => ({}) },
  projectId: { type: [Number, String], default: null },
  members: { type: Array, default: () => [] },
})

defineEmits(['save', 'cancel', 'actionItemChanged'])

const form = reactive({
  status: '', planned_start_date: null, planned_end_date: null,
  actual_start_date: null, actual_end_date: null,
  gate_status: '', gate_review_date: null, gate_review_notes: '', gate: null,
})

watch(() => props.phaseGate, (pg) => {
  Object.assign(form, {
    status: pg.status || 'not_started',
    planned_start_date: pg.planned_start_date || null,
    planned_end_date: pg.planned_end_date || null,
    actual_start_date: pg.actual_start_date || null,
    actual_end_date: pg.actual_end_date || null,
    gate_status: pg.gate_status || '',
    gate_review_date: pg.gate_review_date || null,
    gate_review_notes: pg.gate_review_notes || '',
    gate: pg.gate || null,
  })
  if (pg.phase_id) loadActionItems()
}, { immediate: true })

// ── Action Items ──
const actionItems = ref([])
const showAddDialog = ref(false)
const showCloseDialog = ref(false)
const editingItem = ref(null)
const closingItem = ref(null)
const itemForm = reactive({ title: '', assignee_id: null, due_date: null, description: '' })
const closeForm = reactive({ resolution: '' })

async function loadActionItems() {
  if (!props.projectId || !props.phaseGate.phase_id) return
  try {
    // Get the phase_gate record ID for this phase
    const pgId = props.phaseGate.id
    if (!pgId) return
    const res = await api.get(`/phase-gates/${pgId}/action-items`)
    actionItems.value = res.data
  } catch (e) { /* ignore */ }
}

function editItem(item) {
  editingItem.value = item
  Object.assign(itemForm, {
    title: item.title, assignee_id: item.assignee_id,
    due_date: item.due_date, description: item.description || '',
  })
  showAddDialog.value = true
}

async function saveItem() {
  try {
    if (editingItem.value) {
      await api.put(`/action-items/${editingItem.value.id}`, { ...itemForm })
      ElMessage.success('待办已更新')
    } else {
      await api.post(`/phase-gates/${props.phaseGate.id}/action-items`, { ...itemForm })
      ElMessage.success('待办已创建')
    }
    showAddDialog.value = false
    editingItem.value = null
    Object.assign(itemForm, { title: '', assignee_id: null, due_date: null, description: '' })
    loadActionItems()
  } catch (e) { ElMessage.error('保存失败') }
}

function closeItem(item) {
  closingItem.value = item
  closeForm.resolution = ''
  showCloseDialog.value = true
}

async function doCloseItem() {
  try {
    await api.put(`/action-items/${closingItem.value.id}`, {
      status: 'closed', resolution: closeForm.resolution,
    })
    ElMessage.success('待办已关闭')
    showCloseDialog.value = false
    closingItem.value = null
    loadActionItems()
  } catch (e) { ElMessage.error('操作失败') }
}

async function deleteItem(item) {
  try {
    await api.delete(`/action-items/${item.id}`)
    ElMessage.success('已删除')
    loadActionItems()
  } catch (e) { ElMessage.error('删除失败') }
}

// ── 发起两级签核 ──
const signoffVisible = ref(false)
const signoffLoading = ref(false)
const signoffForm = reactive({ level1_signer_id: null, level2_signer_id: null })
const auditOk = ref(false)

function openSignoff() {
  auditOk.value = false
  Object.assign(signoffForm, { level1_signer_id: null, level2_signer_id: null })
  signoffVisible.value = true
}

async function doInitiateSignoff() {
  if (!signoffForm.level1_signer_id || !signoffForm.level2_signer_id) { ElMessage.warning('请选择两级签核人'); return }
  if (!auditOk.value) { ElMessage.warning('该门必需交付物未全部批准，暂不能发起签核'); return }
  signoffLoading.value = true
  try {
    await api.post(`/gate-reviews/${props.phaseGate.id}/initiate-signoff`, { ...signoffForm })
    ElMessage.success('已发起两级签核,请签核人到「阶段门评审 → 签核审批」处理')
    signoffVisible.value = false
    Object.assign(signoffForm, { level1_signer_id: null, level2_signer_id: null })
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '发起失败')
  } finally { signoffLoading.value = false }
}
</script>

<style scoped>
.action-item-row {
  display: flex; align-items: center; padding: 8px 0;
  border-bottom: 1px solid #f0f0f0; font-size: 13px;
}
.action-item-row:last-child { border-bottom: none; }
.field-hint { font-size: 11px; color: #909399; line-height: 1.5; padding-top: 4px; }
</style>
