<template>
  <div class="pdc-tab">
    <div class="toolbar">
      <el-radio-group v-if="!phaseCode" v-model="phaseFilter" size="small">
        <el-radio-button value="all">全部阶段</el-radio-button>
        <el-radio-button v-for="p in phases" :key="p.id" :value="p.id">{{ p.code || '' }} {{ p.name }}</el-radio-button>
      </el-radio-group>
      <span v-else class="locked-phase">{{ lockedPhaseName }}</span>
      <el-button size="small" style="margin-left:auto" @click="load">刷新</el-button>
    </div>

    <!-- 全部阶段:按阶段分组 -->
    <template v-if="!displayPhase">
      <div v-for="p in phases" :key="p.id" class="pdc-group">
        <div class="pdc-group-head">
          <span class="pdc-phase">{{ p.code || '' }} {{ p.name }}</span>
          <span class="pdc-count">{{ doneCount(p) }}/{{ stdsOf(p).length }} 已添加</span>
        </div>
        <el-table :data="withMatch(stdsOf(p))" size="small" v-loading="loading">
          <el-table-column label="交付物标准" min-width="220">
            <template #default="{ row }">
              <div>
                <span class="std-name">{{ row.name }}</span>
                <el-tag v-if="row.required" type="danger" size="small" style="margin-left:6px">必需</el-tag>
                <el-tag v-else type="info" size="small" style="margin-left:6px">可选</el-tag>
                <div v-if="row.description" class="std-desc">{{ row.description }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">{{ catLabel(row.category) }}</template>
          </el-table-column>
          <el-table-column label="通过标准" min-width="220">
            <template #default="{ row }">
              <span v-if="row.acceptance_criteria" class="std-criteria">{{ row.acceptance_criteria }}</span>
              <span v-else class="t-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="责任角色" width="110">
            <template #default="{ row }">{{ row.responsible_role || '—' }}</template>
          </el-table-column>
          <el-table-column label="交付物状态" width="300">
            <template #default="{ row }">
              <template v-if="row.deliverables.length">
                <div v-for="dv in row.deliverables" :key="dv.id" style="margin-bottom:4px">
                  <div style="display:flex;align-items:center;gap:6px">
                    <el-tag :type="statusType(dv.status)" size="small">{{ statusLabel(dv.status) }}</el-tag>
                    <span v-if="dv.submitted_date" class="t-muted">{{ dv.submitted_date }}</span>
                    <el-button link size="small" @click="openDialog(row, dv)">编辑</el-button>
                    <el-button v-if="dv.status==='not_submitted'" link size="small" type="success" @click="quickSubmit(dv)">提交</el-button>
                    <el-button v-if="dv.status==='not_submitted'" link size="small" type="danger" @click="delDeliverable(dv)">删除</el-button>
                  </div>
                  <div v-if="dv.file_path" style="display:flex;align-items:center;gap:4px;font-size:12px">
                    <el-link type="primary" @click="previewFile(dv)">📄 {{ fileName(dv.file_path) }}</el-link>
                    <el-button link size="small" type="danger" @click="deleteFile(dv)">删除</el-button>
                  </div>
                  <div v-if="dv.attachments && dv.attachments.length" style="display:flex;flex-wrap:wrap;gap:4px;font-size:12px;margin-top:2px">
                    <el-tag v-for="att in dv.attachments" :key="att.id" size="small" type="success" style="cursor:pointer" @click="openAtt(att)">
                      📎 {{ fileName(att.file_path) }}
                    </el-tag>
                  </div>
                </div>
              </template>
              <span v-else class="t-muted">未添加</span>
            </template>
          </el-table-column>
          <el-table-column label="模板" width="90" fixed="right">
            <template #default="{ row }">
              <el-dropdown trigger="click" size="small" @command="cmd => tplCmd(cmd, row)">
                <el-button type="warning" link size="small">📄 模板<el-icon style="margin-left:2px"><ArrowDown /></el-icon></el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="preview">预览模板</el-dropdown-item>
                    <el-dropdown-item command="download">下载模板</el-dropdown-item>
                    <el-dropdown-item v-if="isAdmin" command="upload">{{ row.template_path ? '更换模板' : '上传模板' }}</el-dropdown-item>
                    <el-dropdown-item v-if="isAdmin && row.template_path" command="remove" divided>删除模板</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button type="success" link size="small" @click="openAiReport(row)">🤖 AI报告</el-button>
              <el-button type="primary" link size="small" @click="openDialog(row)">+ 添加交付物</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>

    <!-- 单阶段筛选 -->
    <el-table v-else :data="withMatch(stdsOf(displayPhase))" size="small" v-loading="loading">
      <el-table-column label="交付物标准" min-width="220">
        <template #default="{ row }">
          <div>
            <span class="std-name">{{ row.name }}</span>
            <el-tag v-if="row.required" type="danger" size="small" style="margin-left:6px">必需</el-tag>
            <el-tag v-else type="info" size="small" style="margin-left:6px">可选</el-tag>
            <div v-if="row.description" class="std-desc">{{ row.description }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="90">
        <template #default="{ row }">{{ catLabel(row.category) }}</template>
      </el-table-column>
      <el-table-column label="通过标准" min-width="220">
        <template #default="{ row }">
          <span v-if="row.acceptance_criteria" class="std-criteria">{{ row.acceptance_criteria }}</span>
          <span v-else class="t-muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="责任角色" width="110">
        <template #default="{ row }">{{ row.responsible_role || '—' }}</template>
      </el-table-column>
      <el-table-column label="交付物状态" width="300">
        <template #default="{ row }">
          <template v-if="row.deliverables.length">
            <div v-for="dv in row.deliverables" :key="dv.id" style="margin-bottom:4px">
              <div style="display:flex;align-items:center;gap:6px">
                <el-tag :type="statusType(dv.status)" size="small">{{ statusLabel(dv.status) }}</el-tag>
                <span v-if="dv.submitted_date" class="t-muted">{{ dv.submitted_date }}</span>
                <el-button link size="small" @click="openDialog(row, dv)">编辑</el-button>
                <el-button v-if="dv.status==='not_submitted'" link size="small" type="success" @click="quickSubmit(dv)">提交</el-button>
                <el-button v-if="dv.status==='not_submitted'" link size="small" type="danger" @click="delDeliverable(dv)">删除</el-button>
              </div>
              <div v-if="dv.file_path" style="display:flex;align-items:center;gap:4px;font-size:12px">
                <el-link type="primary" @click="previewFile(dv)">📄 {{ fileName(dv.file_path) }}</el-link>
                <el-button link size="small" type="danger" @click="deleteFile(dv)">删除</el-button>
              </div>
              <div v-if="dv.attachments && dv.attachments.length" style="display:flex;flex-wrap:wrap;gap:4px;font-size:12px;margin-top:2px">
                <el-tag v-for="att in dv.attachments" :key="att.id" size="small" type="success" style="cursor:pointer" @click="openAtt(att)">
                  📎 {{ fileName(att.file_path) }}
                </el-tag>
              </div>
            </div>
          </template>
          <span v-else class="t-muted">未添加</span>
        </template>
      </el-table-column>
      <el-table-column label="模板" width="90" fixed="right">
        <template #default="{ row }">
          <el-dropdown trigger="click" size="small" @command="cmd => tplCmd(cmd, row)">
            <el-button type="warning" link size="small">📄 模板<el-icon style="margin-left:2px"><ArrowDown /></el-icon></el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="preview">预览模板</el-dropdown-item>
                <el-dropdown-item command="download">下载模板</el-dropdown-item>
                <el-dropdown-item v-if="isAdmin" command="upload">{{ row.template_path ? '更换模板' : '上传模板' }}</el-dropdown-item>
                <el-dropdown-item v-if="isAdmin && row.template_path" command="remove" divided>删除模板</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button type="success" link size="small" @click="openAiReport(row)">🤖 AI报告</el-button>
          <el-button type="primary" link size="small" @click="openDialog(row)">+ 添加交付物</el-button>
        </template>
      </el-table-column>
    </el-table>

    <input ref="tplInput" type="file" style="display:none" accept=".doc,.docx,.xls,.xlsx,.ppt,.pptx,.pdf,.zip" @change="onTplFile">

    <div v-if="!loading && !standards.length" class="empty-hint">暂无交付物标准，请先到「阶段门评审 → 标准维护」配置</div>

    <!-- 添加/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingItem ? '编辑交付物' : '添加交付物'" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="阶段">
          <el-select v-model="form.phase_id" style="width:100%" :disabled="!!stdSource">
            <el-option v-for="p in phases" :key="p.id" :label="`${p.code || ''} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width:100%">
                <el-option label="未提交" value="not_submitted" />
                <el-option label="已提交" value="submitted" />
                <el-option label="已评审" value="reviewed" />
                <el-option label="已批准" value="approved" />
                <el-option label="已驳回" value="rejected" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="提交日期">
              <el-date-picker v-model="form.submitted_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="文件路径">
          <div style="width:100%">
            <div v-if="form.file_path" style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <a :href="fileUrl(form.file_path)" target="_blank" style="font-size:12px;color:var(--primary)">📄 {{ fileName(form.file_path) }}</a>
              <el-button link size="small" type="danger" @click="clearFile">清除</el-button>
            </div>
            <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onFileRemove" :on-exceed="onFileExceed"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.zip,.dwg,.step,.stp,.stl,.igs,.iges,.dxf,.mp4,.avi,.mov,.mkv">
              <el-button size="small">📎 选择文件</el-button>
            </el-upload>
            <div v-if="pendingFile" style="font-size:12px;color:#67c23a;margin-top:4px">已选择：{{ pendingFile.name }}</div>
            <div style="font-size:11px;color:#8f959e;margin-top:2px">保存交付物时自动上传（不超过 200MB）</div>
          </div>
        </el-form-item>
        <el-form-item label="负责人">
          <el-select v-model="form.owner_id" filterable clearable style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI 报告弹窗 -->
    <el-dialog v-model="aiDialogVisible" :title="'AI 报告 — ' + aiReportName" width="860px" top="4vh">
      <div v-if="aiLoading" class="ai-loading">
        <el-icon class="is-loading" style="font-size:24px"><Loading /></el-icon>
        <div style="margin-top:10px;color:var(--text-muted)">AI 正在结合标准模板与项目历史数据生成报告，约需 20~60 秒...</div>
      </div>
      <template v-else>
        <div v-if="aiMeta" style="margin-bottom:8px;font-size:12px;color:#8f959e">{{ aiMeta }}</div>
        <el-input v-model="aiReportContent" type="textarea" :rows="20"
          style="font-family:Consolas,monospace;font-size:13px;line-height:1.7" />
        <div style="margin-top:12px;text-align:right">
          <el-button type="primary" @click="exportAiDocx">导出 Word</el-button>
          <el-button @click="exportAiPptx">导出 PPT</el-button>
          <el-button type="warning" plain :loading="aiFillLoading" :disabled="!aiFillReady" @click="fillTemplateFile">下载填好的模板文件</el-button>
          <el-button @click="aiDialogVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- 文件预览弹窗 -->
    <FilePreviewDialog ref="previewRef" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getStandards, getDeliverables, createDeliverable, updateDeliverable, deleteDeliverable, getTeamMembers, uploadStandardTemplate, deleteStandardTemplate, deleteDeliverableFile } from '../../api/index.js'
import { useAuthStore } from '../../stores/auth.js'
import api from '../../api/index.js'
import FilePreviewDialog from '../common/FilePreviewDialog.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  phases: { type: Array, default: () => [] },
  phaseCode: { type: String, default: null }, // 锁定单个阶段(如 P0),null=全部阶段
})

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)
const tplTarget = ref(null)
const tplInput = ref(null)

const loading = ref(false)
const aiDialogVisible = ref(false)
const aiLoading = ref(false)
const aiReportContent = ref('')
const aiReportName = ref('')
const aiMeta = ref('')
const aiFillUrl = ref('')
const aiFillReady = ref(false)
const aiFillLoading = ref(false)
const phaseFilter = ref('all')
const standards = ref([])
const deliverableList = ref([])
const members = ref([])
const dialogVisible = ref(false)
const saving = ref(false)
const editingItem = ref(null)
const stdSource = ref(null)
const pendingFile = ref(null)
const uploadRef = ref(null)
const form = ref({ name: '', description: '', phase_id: null, status: 'not_submitted', submitted_date: '', file_path: '', owner_id: null })
const previewRef = ref(null)

const displayPhase = computed(() => props.phases.find(p => p.id === phaseFilter.value) || null)
const lockedPhaseName = computed(() => {
  const p = props.phases.find(x => x.code === props.phaseCode)
  return p ? `${p.code || ''} ${p.name}` : props.phaseCode
})

// phaseCode 锁定:找到对应阶段并切换过滤器(阶段数据加载前可能为空,需等待)
function applyPhaseLock() {
  if (!props.phaseCode) { phaseFilter.value = 'all'; return }
  const p = props.phases.find(x => x.code === props.phaseCode)
  if (p) phaseFilter.value = p.id
}
watch(() => props.phaseCode, applyPhaseLock, { immediate: true })
watch(() => props.phases, applyPhaseLock)

// 标准按阶段分组
function stdsOf(p) {
  if (!p) return []
  return standards.value.filter(s => s.phase_id === p.id)
}

// 标准与该项目交付物匹配(名称双向包含,多匹配取状态优先)
function matchAny(st) {
  return matchAll(st)[0] || null
}
function matchAll(st) {
  const cands = deliverableList.value.filter(d => d.phase_id === st.phase_id && d.name && st.name && (d.name.includes(st.name) || st.name.includes(d.name)))
  const prio = { approved: 0, submitted: 1, reviewed: 2, rejected: 3, not_submitted: 4 }
  return cands.sort((a, b) => (prio[a.status] ?? 5) - (prio[b.status] ?? 5))
}
function withMatch(stds) {
  return (stds || []).map(st => ({ ...st, deliverable: matchAny(st), deliverables: matchAll(st) }))
}
function doneCount(p) {
  return withMatch(stdsOf(p)).filter(s => s.deliverable).length
}

function catLabel(c) {
  return { document: '文档', report: '报告', approval: '审批', other: '其他' }[c] || c || '—'
}
function statusType(s) {
  return { not_submitted: 'info', submitted: 'warning', reviewed: '', approved: 'success', rejected: 'danger' }[s] || 'info'
}
function statusLabel(s) {
  return { not_submitted: '未提交', submitted: '已提交', reviewed: '已评审', approved: '已批准', rejected: '已驳回' }[s] || s
}

async function load() {
  loading.value = true
  try {
    const [s, d] = await Promise.all([getStandards(), getDeliverables(props.projectId)])
    standards.value = (s.data || []).filter(x => x.is_active !== false)
    deliverableList.value = d.data || []
  } finally { loading.value = false }
}

function openDialog(std, dv) {
  stdSource.value = std || null
  editingItem.value = dv || null
  pendingFile.value = null
  uploadRef.value?.clearFiles()
  if (dv) {
    form.value = { name: dv.name, description: dv.description || '', phase_id: dv.phase_id, status: dv.status, submitted_date: dv.submitted_date || '', file_path: dv.file_path || '', owner_id: dv.owner_id }
  } else {
    form.value = { name: std.name, description: std.description || '', phase_id: std.phase_id, status: 'not_submitted', submitted_date: '', file_path: '', owner_id: null }
  }
  dialogVisible.value = true
}

function onFileChange(file) { pendingFile.value = file.raw }
function onFileRemove() { pendingFile.value = null }
function onFileExceed() { ElMessage.warning('只能选择一个文件') }
function fileName(p) {
  const n = String(p || '').split(/[\\/]/).pop() || p
  return n.replace(/^[0-9a-f]{8}_/, '') || n
}
function fileUrl(p) { return '/uploads/' + String(p || '').replace(/^[\\/]+/, '') }
function openAtt(att) { window.open(fileUrl(att.file_path), '_blank') }
async function clearFile() {
  if (!editingItem.value) { form.value.file_path = ''; return }
  try {
    await deleteDeliverableFile(editingItem.value.id)
    form.value.file_path = ''
    ElMessage.success('已清除')
    await load()
  } catch (e) { ElMessage.error('清除失败') }
}

async function previewFile(dv) {
  if (!dv.file_path) return
  if (previewRef.value.previewable(dv.file_path)) {
    const blob = await (await fetch(fileUrl(dv.file_path))).blob()
    await previewRef.value.openBlob(blob, fileName(dv.file_path))
  } else {
    window.open(fileUrl(dv.file_path), '_blank') // pdf/图片浏览器原生预览,其余下载
  }
}

async function previewTpl(std) {
  try {
    const res = await api.get(`/gate-deliverable-standards/${std.id}/template`, { responseType: 'blob' })
    const ext = std.template_path ? (std.template_path.split('.').pop() || 'docx') : 'docx'
    await previewRef.value.openBlob(res.data, `模板-${std.name}.${ext}`)
  } catch (e) { ElMessage.error('模板获取失败: ' + (e?.response?.data?.detail || e.message)) }
}

async function deleteFile(dv) {
  try {
    await ElMessageBox.confirm(`确认删除文件「${fileName(dv.file_path)}」?删除后不可恢复`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await deleteDeliverableFile(dv.id)
    ElMessage.success('文件已删除')
    await load()
  } catch (e) { ElMessage.error('删除失败: ' + (e?.response?.data?.detail || e.message)) }
}

async function delDeliverable(dv) {
  const msg = dv.file_path
    ? `确认删除交付物「${dv.name}」?其上传的文件将一并删除，不可恢复`
    : `确认删除交付物「${dv.name}」?删除后不再显示`
  try {
    await ElMessageBox.confirm(msg, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await deleteDeliverable(dv.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) { ElMessage.error('删除失败: ' + (e?.response?.data?.detail || e.message)) }
}

async function save() {
  if (!form.value.name.trim()) { ElMessage.warning('请输入名称'); return }
  if (!form.value.phase_id) { ElMessage.warning('请选择阶段'); return }
  saving.value = true
  try {
    let id = editingItem.value ? editingItem.value.id : null
    if (editingItem.value) await updateDeliverable(editingItem.value.id, form.value)
    else {
      const res = await createDeliverable(props.projectId, form.value)
      id = res.data?.id || id
    }
    if (pendingFile.value && id) {
      const fd = new FormData()
      fd.append('file', pendingFile.value)
      const up = await api.post(`/deliverables/${id}/upload-file`, fd)
      form.value.file_path = up.data.file_path
      pendingFile.value = null
    }
    ElMessage.success(editingItem.value ? '已更新' : '已添加')
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e?.response?.data?.detail || e.message))
  } finally { saving.value = false }
}

async function quickSubmit(dv) {
  await updateDeliverable(dv.id, { status: 'submitted', submitted_date: new Date().toISOString().slice(0, 10) })
  ElMessage.success('已提交')
  await load()
}

function tplCmd(cmd, std) {
  if (cmd === 'preview') previewTpl(std)
  else if (cmd === 'download') downloadTpl(std)
  else if (cmd === 'upload') { tplTarget.value = std; tplInput.value?.click() }
  else if (cmd === 'remove') removeTpl(std)
}

async function downloadTpl(std) {
  try {
    const res = await api.get(`/gate-deliverable-standards/${std.id}/template`, { responseType: 'blob' })
    const ext = std.template_path ? (std.template_path.split('.').pop() || 'docx') : 'docx'
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url
    a.download = `模板-${std.name}.${ext}`
    a.click(); URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('下载失败: ' + (e?.response?.data?.detail || e.message)) }
}

async function onTplFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f || !tplTarget.value) return
  try {
    const fd = new FormData()
    fd.append('file', f)
    await uploadStandardTemplate(tplTarget.value.id, fd)
    ElMessage.success('模板已上传')
    await load()
  } catch (err) { ElMessage.error('上传失败: ' + (err?.response?.data?.detail || err.message)) }
}

async function openAiReport(std) {
  // 已有交付物 → 按交付物生成; 未添加 → 按标准模板 + 项目数据生成
  const dv = std.deliverable
  const url = dv
    ? `/report-gen/deliverable/${dv.id}`
    : `/report-gen/standard-report/${std.id}?project_id=${props.projectId}`
  aiReportName.value = (dv ? dv.name : std.name) || '报告'
  aiReportContent.value = ''
  aiMeta.value = ''
  aiFillUrl.value = dv
    ? `/report-gen/fill-deliverable/${dv.id}`
    : `/report-gen/fill-standard/${std.id}?project_id=${props.projectId}`
  aiFillReady.value = !!(std.template_path)
  aiDialogVisible.value = true
  aiLoading.value = true
  try {
    const r = await api.get(url, { timeout: 180000 })
    aiReportContent.value = r.data.content || ''
    const parts = []
    if (r.data.template_used) parts.push('模板: ' + r.data.template_used)
    if (r.data.std_name) parts.push('标准: ' + r.data.std_name)
    if (r.data.generated_at) parts.push('生成时间: ' + String(r.data.generated_at).replace('T', ' ').slice(0, 16))
    aiMeta.value = parts.join(' | ')
  } catch (e) {
    ElMessage.error('生成失败: ' + (e?.response?.data?.detail || e.message))
  } finally {
    aiLoading.value = false
  }
}

async function exportAiDocx() {
  try {
    const r = await api.post('/report-gen/export/docx', { content: aiReportContent.value, title: `${aiReportName.value} - AI报告` }, { responseType: 'blob', timeout: 60000 })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url
    a.download = `${aiReportName.value}_AI报告.docx`
    a.click(); URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('Word 导出失败') }
}

async function exportAiPptx() {
  try {
    const r = await api.post('/report-gen/export/pptx', { content: aiReportContent.value, title: `${aiReportName.value} - AI报告` }, { responseType: 'blob', timeout: 60000 })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url
    a.download = `${aiReportName.value}_AI报告.pptx`
    a.click(); URL.revokeObjectURL(url)
  } catch (e) { ElMessage.error('PPT 导出失败') }
}

async function fillTemplateFile() {
  if (!aiFillReady.value) { ElMessage.warning('该标准没有模板，请先在「标准维护」上传 .docx 模板'); return }
  aiFillLoading.value = true
  try {
    const r = await api.get(aiFillUrl.value, { responseType: 'blob', timeout: 180000 })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url
    a.download = `${aiReportName.value}_模板填充版.docx`
    a.click(); URL.revokeObjectURL(url)
    ElMessage.success('已生成填好的模板文件')
  } catch (e) {
    let msg = e?.message || '请检查模板关联'
    const data = e?.response?.data
    if (data instanceof Blob) {
      try {
        const j = JSON.parse(await data.text())
        if (j?.detail) msg = j.detail
      } catch (_) {}
    } else if (data?.detail) {
      msg = data.detail
    }
    ElMessage.error('填充失败: ' + msg)
  } finally {
    aiFillLoading.value = false
  }
}

async function removeTpl(std) {
  try {
    await ElMessageBox.confirm(`确认删除「${std.name}」的模板?删除后恢复为自动生成骨架`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await deleteStandardTemplate(std.id)
    ElMessage.success('已删除模板')
    await load()
  } catch (err) { ElMessage.error('删除失败: ' + (err?.response?.data?.detail || err.message)) }
}

onMounted(async () => {
  try { members.value = (await getTeamMembers()).data || [] } catch (e) {}
  await load()
})
</script>

<style scoped>
.pdc-tab { padding: 4px 0; }
.toolbar { display: flex; align-items: center; margin-bottom: 12px; }
.locked-phase { font-size: 13px; font-weight: 600; color: var(--text); }
.pdc-group { background: #fff; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.pdc-group-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.pdc-phase { font-weight: 600; font-size: 14px; }
.pdc-count { font-size: 12px; color: var(--text-muted); margin-left: auto; }
.std-name { font-weight: 600; }
.std-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; line-height: 1.5; }
.std-criteria { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.t-muted { color: var(--text-muted); font-size: 12px; }
.empty-hint { color: var(--text-muted); font-size: 12px; padding: 14px 4px; }
.ai-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  font-size: 13px;
}
</style>
