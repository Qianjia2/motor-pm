<template>
  <div>
    <div class="change-desc">
      <el-icon style="margin-right:6px"><InfoFilled /></el-icon>
      产品设计、过程、材料/供应商变更全流程管理
    </div>

    <div class="stat-grid" style="margin-bottom:16px">
      <div class="stat-card stat-info">
        <div class="stat-value">{{ totalCount }}</div>
        <div class="stat-label">变更数</div>
      </div>
      <div class="stat-card stat-warning">
        <div class="stat-value">{{ inProgressCount }}</div>
        <div class="stat-label">进行中</div>
      </div>
      <div class="stat-card stat-success">
        <div class="stat-value">{{ approvedCount }}</div>
        <div class="stat-label">已批准</div>
      </div>
      <div class="stat-card stat-danger">
        <div class="stat-value">{{ urgentCount }}</div>
        <div class="stat-label">紧急变更</div>
      </div>
    </div>

    <div class="card-header mb-md">
      <span></span>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon> 新建变更
      </el-button>
    </div>

    <el-table :data="items" stripe @row-click="openDialog" row-style="cursor:pointer">
      <el-table-column label="等级" width="70">
        <template #default="{row}">
          <el-tag :type="row.change_level === 'A' ? 'danger' : row.change_level === 'B' ? 'warning' : 'info'" size="small">
            {{ row.change_level || 'C' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="变更标题" min-width="180" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{row}">
          <el-tag :type="changeStatusType(row.status)" size="small">
            {{ changeStatusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="requester?.name" label="申请人" width="80" />
      <el-table-column prop="submitted_date" label="提交日期" width="110" />
      <el-table-column prop="affected_lines" label="影响技术线" width="140" />
      <el-table-column label="两级签核" width="330">
        <template #default="{row}">
          <div v-if="row.signoffs && row.signoffs.length" class="sg-list">
            <div v-for="sg in row.signoffs" :key="sg.level" class="sg-row">
              <div class="sg-head">
                <el-tag :type="sg.level === 1 ? 'primary' : 'warning'" size="small" effect="plain">
                  {{ sg.level === 1 ? '一级' : '二级' }}·{{ sg.signer_name || '—' }}
                </el-tag>
                <el-tag :type="signoffStatusType(sg.status)" size="small">{{ signoffStatusLabel(sg.status) }}</el-tag>
                <span v-if="sg.signed_by_username" class="sg-actor" :title="sg.signed_by_username">{{ auth.displayName(sg.signed_by_username) }}</span>
                <span v-if="sg.signed_at" class="sg-time">{{ formatTime(sg.signed_at) }}</span>
                <template v-if="sg.status === 'pending' && canAct(sg)">
                  <el-button link size="small" type="success" @click.stop="openAction(sg, 'approve')">通过</el-button>
                  <el-button link size="small" type="danger" @click.stop="openAction(sg, 'reject')">驳回</el-button>
                </template>
              </div>
              <div v-if="sg.comment" class="sg-comment" :title="sg.comment">意见：{{ sg.comment }}</div>
            </div>
          </div>
          <span v-else class="t-muted" style="font-size:12px">未发起两级签核</span>
        </template>
      </el-table-column>
      <el-table-column label="附件" width="60" align="center">
        <template #default="{row}">
          <el-tooltip v-if="row.attachment" :content="(canPreview(row.attachment.name) ? '预览' : '下载') + `：${row.attachment.name}（${formatSize(row.attachment.size)}）`">
            <el-link type="primary" :underline="false" @click.stop="previewAttachment(row)">📎</el-link>
          </el-tooltip>
          <span v-else class="t-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" :width="isAdmin ? 240 : 195" fixed="right">
        <template #default="{row}">
          <el-button type="primary" link size="small" @click.stop="openDialog(row)">编辑</el-button>
          <el-button
            v-if="row.status === 'approved'"
            type="success"
            link
            size="small"
            @click.stop="markImplemented(row)"
          >实施</el-button>
          <el-button
            v-if="canWithdraw(row)"
            type="warning"
            link
            size="small"
            @click.stop="withdrawChange(row)"
          >撤回</el-button>
          <el-button
            v-if="row.status === 'withdrawn' && canWithdraw(row)"
            type="primary"
            link
            size="small"
            @click.stop="openResubmit(row)"
          >重新提交</el-button>
          <el-button
            v-if="isAdmin"
            type="danger"
            link
            size="small"
            @click.stop="removeChange(row)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 变更编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingChange ? '编辑变更' : '新建变更请求'"
      width="650px"
    >
      <el-form :model="form" label-width="110px">
        <el-form-item label="变更标题" required>
          <el-input v-model="form.title" placeholder="简述变更内容" />
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="变更等级">
              <el-select v-model="form.change_level" style="width:100%">
                <el-option label="A - 重大" value="A" />
                <el-option label="B - 一般" value="B" />
                <el-option label="C - 轻微" value="C" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="申请人">
              <el-select v-model="form.requester_id" filterable style="width:100%">
                <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="提交日期">
              <el-date-picker v-model="form.submitted_date" type="date" style="width:100%" value-format="YYYY-MM-DD" disabled />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="影响技术线">
          <el-select v-model="affectedLinesArr" multiple filterable collapse-tags style="width:100%" placeholder="选择影响的技术线">
            <el-option label="全部技术线" value="全部技术线" />
            <el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.name" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>

        <el-divider content-position="left">影响分析</el-divider>

        <el-form-item label="范围影响">
          <el-input v-model="form.impact_scope" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="进度影响">
          <el-input v-model="form.impact_schedule" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="成本影响">
          <el-input v-model="form.impact_cost" type="textarea" :rows="2" />
        </el-form-item>

        <el-divider content-position="left">审批信息（两级签核）</el-divider>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="一级签核人" required>
              <el-select v-model="form.level1_signer_id" filterable :disabled="signoffsInitiated" placeholder="项目负责人" style="width:100%">
                <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="二级签核人" required>
              <el-select v-model="form.level2_signer_id" filterable :disabled="signoffsInitiated" placeholder="管理层复核" style="width:100%">
                <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <div style="font-size:12px;color:#909399;padding-left:110px">
          {{ signoffsInitiated ? '该变更已发起签核，签核人不可修改' : '流程：一级通过后进入二级，两级通过后批准；任一级驳回即驳回' }}
        </div>

        <el-divider content-position="left">附件（变更申请表 / 证明文件）</el-divider>
        <el-form-item label="附件">
          <div style="width:100%">
            <div v-if="editingChange?.attachment" class="attach-row">
              <el-icon><Document /></el-icon>
              <el-link v-if="canPreview(editingChange.attachment.name)" type="primary" :underline="false" @click="previewAttachment(editingChange)">{{ editingChange.attachment.name }}</el-link>
              <span v-else>{{ editingChange.attachment.name }}</span>
              <span class="t-muted" style="font-size:12px">（{{ formatSize(editingChange.attachment.size) }}）</span>
              <el-link type="primary" :underline="false" style="font-size:12px" @click="downloadAttachment(editingChange)">下载</el-link>
              <el-button link type="danger" size="small" :loading="deletingAttach" @click="removeAttachment">删除</el-button>
            </div>
            <el-upload :auto-upload="false" :show-file-list="false" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.png,.jpg,.jpeg,.zip"
              :on-change="onAttachChange" style="display:inline-block">
              <el-button size="small" :type="attachFile || editingChange?.attachment ? 'warning' : 'default'">
                {{ editingChange?.attachment && !attachFile ? '更换附件' : '选择附件' }}
              </el-button>
            </el-upload>
            <span v-if="attachFile" style="margin-left:8px;font-size:12px;color:#3b82f6">已选择：{{ attachFile.name }}</span>
            <el-link v-if="attachFile && canPreviewLocal(attachFile.name)" type="primary" :underline="false" :loading="previewLoading" style="margin-left:8px;font-size:12px" @click="previewLocalFile">预览</el-link>
            <span v-if="!editingChange" style="margin-left:8px;font-size:12px;color:#909399">保存变更后自动上传</span>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div style="display:flex;justify-content:space-between;width:100%">
          <el-upload :action="ocrUrl" :headers="uploadHeaders" :show-file-list="false"
            accept=".png,.jpg,.jpeg,.gif,.bmp,.webp" :on-success="onOcrResult"
            style="display:inline-block">
            <el-button type="warning" size="small">📷 上传截图识别</el-button>
          </el-upload>
          <div>
            <el-button @click="dialogVisible = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 附件预览弹窗 -->
    <el-dialog v-model="previewVisible" title="附件预览" width="80%" top="4vh" destroy-on-close>
      <iframe v-if="previewSrcdoc" :srcdoc="previewSrcdoc" style="width:100%;height:70vh;border:1px solid #e0e0e0;border-radius:4px"></iframe>
      <iframe v-else-if="previewUrl" :src="previewUrl" style="width:100%;height:70vh;border:1px solid #e0e0e0;border-radius:4px"></iframe>
      <div v-else style="text-align:center;color:#909399;padding:30px">该格式不支持在线预览，请使用「下载」查看</div>
      <template #footer>
        <el-button size="small" @click="previewVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 签核动作弹窗 -->
    <el-dialog v-model="actionVisible" :title="actionType === 'approve' ? '签核通过' : '签核驳回'" width="420">
      <p class="dialog-desc">
        {{ actionType === 'approve' ? '通过后自动进入下一级签核，二级通过后该变更即批准。' : '驳回后该变更标记为已驳回。' }}
        <span v-if="actionRow?.signer_name" class="t-muted">（{{ actionRow.level === 1 ? '一级' : '二级' }}签核人：{{ actionRow.signer_name }}）</span>
      </p>
      <el-input v-model="comment" type="textarea" :rows="3" :placeholder="actionType === 'approve' ? '签核意见(可选)' : '驳回原因(必填)'" />
      <template #footer>
        <el-button size="small" @click="actionVisible = false">取消</el-button>
        <el-button size="small" :type="actionType === 'approve' ? 'primary' : 'danger'" :loading="acting" @click="submitAction">
          {{ actionType === 'approve' ? '确认通过' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 重新提交弹窗 -->
    <el-dialog v-model="resubmitVisible" title="重新提交变更" width="460">
      <p class="dialog-desc">该变更已撤回。已完成的签核级别将保留，仅需指定缺失级别的签核人。</p>
      <el-form :model="resubmitForm" label-width="100px">
        <el-form-item v-if="!resubmitL1Exists" label="一级签核人" required>
          <el-select v-model="resubmitForm.level1_signer_id" filterable placeholder="项目负责人" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="一级签核人">
          <el-tag type="primary" size="small" effect="plain">一级已通过，保留</el-tag>
        </el-form-item>
        <el-form-item v-if="!resubmitL2Exists" label="二级签核人" required>
          <el-select v-model="resubmitForm.level2_signer_id" filterable placeholder="管理层复核" style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="`${m.name}${m.department ? ' (' + m.department + ')' : ''}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-else label="二级签核人">
          <el-tag type="warning" size="small" effect="plain">二级已通过，保留</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="resubmitVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="resubmitting" @click="doResubmit">重新提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { InfoFilled, Document } from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'
import api, {
  getTeamMembers, getLines, createChange, updateChange,
  approveChangeSignoff, rejectChangeSignoff,
} from '../../api/index.js'

const auth = useAuthStore()

const props = defineProps({
  items: { type: Array, default: () => [] },
  projectId: { type: Number, default: null },
  currentMemberId: { type: Number, default: null },
  isAdmin: { type: Boolean, default: false },
})
const emit = defineEmits(['refresh'])

const totalCount = computed(() => props.items.length)
const inProgressCount = computed(() => props.items.filter(i => i.status === 'pending' || i.status === 'under_review').length)
const approvedCount = computed(() => props.items.filter(i => i.status === 'approved').length)
const urgentCount = computed(() => props.items.filter(i => i.change_level === 'A').length)

const dialogVisible = ref(false)
const editingChange = ref(null)
const members = ref([])
const lines = ref([])
const saving = ref(false)
const attachFile = ref(null)
const deletingAttach = ref(false)

const form = reactive({
  title: '', description: '', change_level: 'C',
  requester_id: null, submitted_date: null,
  affected_lines: '',
  impact_scope: '', impact_schedule: '', impact_cost: '',
  level1_signer_id: null, level2_signer_id: null,
})

const affectedLinesArr = computed({
  get: () => form.affected_lines ? form.affected_lines.split(/[,，、\s]+/).filter(Boolean) : [],
  set: (v) => {
    // 选了「全部技术线」则独占，不再与其他项并存
    if (v.includes('全部技术线')) v = ['全部技术线']
    form.affected_lines = v.join(',')
  },
})

const signoffsInitiated = computed(() => ['pending', 'under_review'].includes(editingChange.value?.status))

function canWithdraw(row) {
  return props.isAdmin || (props.currentMemberId && row.requester_id === props.currentMemberId)
}

onMounted(async () => {
  const m = await getTeamMembers()
  members.value = m.data
  try {
    const l = await getLines()
    lines.value = l.data || []
  } catch (e) {}
})

function todayStr() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function openDialog(row) {
  editingChange.value = row || null
  attachFile.value = null
  if (row) {
    const sg1 = (row.signoffs || []).find(s => s.level === 1)
    const sg2 = (row.signoffs || []).find(s => s.level === 2)
    Object.assign(form, {
      title: row.title || '', description: row.description || '',
      change_level: row.change_level || 'C',
      requester_id: row.requester_id || null,
      submitted_date: row.submitted_date || todayStr(),
      affected_lines: row.affected_lines || '',
      impact_scope: row.impact_scope || '',
      impact_schedule: row.impact_schedule || '',
      impact_cost: row.impact_cost || '',
      level1_signer_id: sg1?.signer_id ?? null,
      level2_signer_id: sg2?.signer_id ?? null,
    })
  } else {
    Object.assign(form, {
      title: '', description: '', change_level: 'C',
      requester_id: props.currentMemberId, submitted_date: todayStr(),
      affected_lines: '', impact_scope: '', impact_schedule: '', impact_cost: '',
      level1_signer_id: null, level2_signer_id: null,
    })
  }
  dialogVisible.value = true
}

async function uploadAttachment(changeId) {
  const fd = new FormData()
  fd.append('file', attachFile.value)
  await api.post(`/changes/${changeId}/attachment`, fd)
}

async function save() {
  if (!form.title) { ElMessage.warning('请输入变更标题'); return }
  if (!signoffsInitiated.value && (!form.level1_signer_id || !form.level2_signer_id)) {
    ElMessage.warning('请选择两级签核人'); return
  }
  saving.value = true
  try {
    const payload = {
      title: form.title, description: form.description,
      change_level: form.change_level, requester_id: form.requester_id,
      submitted_date: form.submitted_date, affected_lines: form.affected_lines,
      impact_scope: form.impact_scope, impact_schedule: form.impact_schedule,
      impact_cost: form.impact_cost,
    }
    let changeId = editingChange.value?.id
    if (changeId) {
      await updateChange(changeId, payload)
      ElMessage.success('已更新')
    } else {
      payload.level1_signer_id = form.level1_signer_id
      payload.level2_signer_id = form.level2_signer_id
      const created = await createChange(props.projectId, payload)
      changeId = created.data.id
      ElMessage.success('已创建并发起两级签核')
    }
    if (attachFile.value) {
      try {
        await uploadAttachment(changeId)
        ElMessage.success('附件已上传')
      } catch (e) {
        ElMessage.warning('变更已保存，但附件上传失败')
      }
    }
    dialogVisible.value = false
    emit('refresh')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '保存失败')
  } finally { saving.value = false }
}

function onAttachChange(file, fileList) {
  attachFile.value = file.raw || null
}

const PREVIEW_EXTS = ['pdf', 'png', 'jpg', 'jpeg', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx']

function canPreview(name) {
  if (!name) return false
  const ext = name.split('.').pop().toLowerCase()
  return PREVIEW_EXTS.includes(ext)
}

function attachmentUrl(row, view) {
  const token = localStorage.getItem('access_token') || ''
  return `/api/changes/${row.id}/attachment?token=${encodeURIComponent(token)}${view ? '&view=1' : ''}`
}

function previewAttachment(row) {
  if (canPreview(row.attachment?.name)) {
    previewUrl.value = attachmentUrl(row, true)
    previewVisible.value = true
  } else {
    downloadAttachment(row)
  }
}

function downloadAttachment(row) {
  window.open(attachmentUrl(row, false), '_blank')
}

const LOCAL_RAW_EXTS = ['pdf', 'png', 'jpg', 'jpeg']

function canPreviewLocal(name) {
  if (!name) return false
  const ext = name.split('.').pop().toLowerCase()
  return PREVIEW_EXTS.includes(ext)
}

// 选完附件立即预览(保存前自查):pdf/图片本地 objectURL,Office 服务端转 PDF 保持原排版
async function previewLocalFile() {
  const file = attachFile.value
  if (!file) return
  const ext = (file.name || '').split('.').pop().toLowerCase()
  previewSrcdoc.value = ''
  if (LOCAL_RAW_EXTS.includes(ext)) {
    previewUrl.value = URL.createObjectURL(file)
    previewVisible.value = true
    return
  }
  const fd = new FormData()
  fd.append('file', file)
  previewLoading.value = true
  try {
    const res = await api.post('/changes/preview-attachment', fd, { headers: { 'Content-Type': 'multipart/form-data' }, responseType: 'blob' })
    if (res.data.type === 'application/pdf') {
      previewUrl.value = URL.createObjectURL(res.data)
      previewVisible.value = true
      return
    }
    const d = JSON.parse(await res.data.text())
    if (d.kind === 'html') {
      previewSrcdoc.value = d.html
      previewVisible.value = true
    } else if (d.kind === 'unsupported') {
      ElMessage.warning('该格式暂不支持在线预览，保存后可通过📎下载查看')
    }
  } catch (e) {
    const b = e.response?.data
    if (b instanceof Blob) {
      try {
        const d = JSON.parse(await b.text())
        if (d?.detail) { ElMessage.error(typeof d.detail === 'string' ? d.detail : '预览失败，请重试'); return }
      } catch {}
    }
    ElMessage.error('预览失败，请重试')
  } finally { previewLoading.value = false }
}

async function removeAttachment() {
  if (!editingChange.value?.id) return
  deletingAttach.value = true
  try {
    await api.delete(`/changes/${editingChange.value.id}/attachment`)
    ElMessage.success('附件已删除')
    emit('refresh')
  } catch (e) { ElMessage.error('删除失败') }
  finally { deletingAttach.value = false }
}

function formatSize(n) {
  if (!n) return ''
  if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB'
  if (n > 1024) return (n / 1024).toFixed(0) + ' KB'
  return n + ' B'
}

function formatTime(v) {
  if (!v) return ''
  const d = new Date(v)
  if (isNaN(d.getTime())) return ''
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function markImplemented(row) {
  try {
    await updateChange(row.id, { status: 'implemented' })
    ElMessage.success('已标记为已实施')
    emit('refresh')
  } catch (e) { ElMessage.error('操作失败') }
}

async function removeChange(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除变更「${row.title}」吗？删除后不可恢复，签核记录与附件将一并删除。`,
      '删除变更',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonClass: 'el-button--danger' }
    )
  } catch { return }
  try {
    await api.delete(`/changes/${row.id}`)
    ElMessage.success('已删除')
    emit('refresh')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '删除失败')
  }
}

// ── 撤回 / 重新提交 ──
const resubmitVisible = ref(false)
const resubmitting = ref(false)
const resubmitRow = ref(null)
const resubmitForm = reactive({ level1_signer_id: null, level2_signer_id: null })

const resubmitL1Exists = computed(() => !!(resubmitRow.value?.signoffs || []).some(s => s.level === 1))
const resubmitL2Exists = computed(() => !!(resubmitRow.value?.signoffs || []).some(s => s.level === 2))

async function withdrawChange(row) {
  try {
    await ElMessageBox.confirm(
      `确定撤回变更「${row.title}」吗？撤回后待签核记录将取消，你可编辑内容后重新提交。`,
      '撤回变更',
      { type: 'warning', confirmButtonText: '撤回', cancelButtonText: '取消', confirmButtonClass: 'el-button--warning' }
    )
  } catch { return }
  try {
    await api.post(`/changes/${row.id}/withdraw`)
    ElMessage.success('已撤回，可编辑后重新提交')
    emit('refresh')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '撤回失败')
  }
}

function openResubmit(row) {
  resubmitRow.value = row
  const sg1 = (row.signoffs || []).find(s => s.level === 1)
  const sg2 = (row.signoffs || []).find(s => s.level === 2)
  resubmitForm.level1_signer_id = sg1?.signer_id ?? null
  resubmitForm.level2_signer_id = sg2?.signer_id ?? null
  resubmitVisible.value = true
}

async function doResubmit() {
  if (!resubmitL1Exists.value && !resubmitForm.level1_signer_id) { ElMessage.warning('请选择一级签核人'); return }
  if (!resubmitL2Exists.value && !resubmitForm.level2_signer_id) { ElMessage.warning('请选择二级签核人'); return }
  resubmitting.value = true
  try {
    await api.post(`/changes/${resubmitRow.value.id}/resubmit`, { ...resubmitForm })
    ElMessage.success('已重新提交，进入签核流程')
    resubmitVisible.value = false
    emit('refresh')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '提交失败')
  } finally { resubmitting.value = false }
}

// ── 附件预览 ──
const previewVisible = ref(false)
const previewUrl = ref('')
const previewSrcdoc = ref('')
const previewLoading = ref(false)

watch(previewVisible, (v) => {
  if (!v) {
    if (previewUrl.value?.startsWith('blob:')) URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = ''
    previewSrcdoc.value = ''
  }
})

// ── 两级签核动作 ──
const actionVisible = ref(false)
const acting = ref(false)
const actionType = ref('approve')
const actionRow = ref(null)
const comment = ref('')

function canAct(rec) {
  return props.isAdmin || (props.currentMemberId && rec.signer_id === props.currentMemberId)
}
function openAction(rec, type) {
  actionRow.value = rec
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
    if (actionType.value === 'approve') await approveChangeSignoff(actionRow.value.id, { comment: comment.value })
    else await rejectChangeSignoff(actionRow.value.id, { comment: comment.value })
    ElMessage.success(actionType.value === 'approve' ? '已签核通过' : '已驳回')
    actionVisible.value = false
    emit('refresh')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error(typeof d === 'string' ? d : '操作失败')
  } finally { acting.value = false }
}

// OCR upload
const ocrUrl = '/api/ocr/parse-chat'
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
function onOcrResult(res) {
  if (!res.ok) { ElMessage.warning(res.message); return }
  ElMessage.success(res.message)
  const p = res.parsed
  if (!p) return
  if (p.change_request) {
    const cr = p.change_request
    if (cr.title) form.title = form.title || cr.title
    if (cr.description) form.description = (form.description || '') + (form.description ? '\n' : '') + cr.description
    if (cr.reason) form.impact_scope = (form.impact_scope || '') + (form.impact_scope ? '\n原因: ' : '原因: ') + cr.reason
    if (cr.impact) form.impact_schedule = (form.impact_schedule || '') + (form.impact_schedule ? '\n' : '') + cr.impact
  }
  if (p.summary) form.description = (form.description || '') + (form.description ? '\n' : '') + p.summary
  ElMessage.success('已自动填入变更内容')
}

function changeStatusType(s) {
  return { pending: 'warning', under_review: '', approved: 'success', rejected: 'danger', implemented: 'primary', withdrawn: 'info' }[s] || 'info'
}
function changeStatusLabel(s) {
  return { pending: '待审批', under_review: '审批中', approved: '已批准', rejected: '已驳回', implemented: '已实施', withdrawn: '已撤回' }[s] || s
}
function signoffStatusType(s) {
  return { pending: 'warning', approved: 'success', rejected: 'danger' }[s] || 'info'
}
function signoffStatusLabel(s) {
  return { pending: '待签核', approved: '已通过', rejected: '已驳回' }[s] || s
}
</script>

<style scoped>
.change-desc {
  display: flex; align-items: center; padding: 10px 14px;
  background: #f0f7ff; border: 1px solid #d6e6ff; border-radius: var(--radius);
  font-size: 13px; color: #2563eb; margin-bottom: 16px;
}
.sg-list { display: flex; flex-direction: column; gap: 6px; }
.sg-row { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.sg-head { display: flex; align-items: center; gap: 6px; }
.sg-actor { color: #2563eb; font-weight: 600; white-space: nowrap; }
.sg-time { color: var(--text-muted); white-space: nowrap; }
.sg-comment { color: #606266; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attach-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; font-size: 13px; }
.dialog-desc { font-size: 12px; color: var(--text-secondary); margin: 0 0 12px; }
.t-muted { color: var(--text-muted); }
</style>
