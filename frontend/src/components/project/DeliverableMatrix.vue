<template>
  <div>
    <div class="card-header mb-md">
      <div>
        <el-select v-model="filterPhase" placeholder="筛选阶段" clearable size="small" style="width:140px;margin-right:8px" @change="load">
          <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
        <el-select v-model="filterLine" placeholder="筛选技术线" clearable size="small" style="width:140px" @change="load">
          <el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.id" />
        </el-select>
      </div>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon> 添加交付物
      </el-button>
    </div>

    <!-- 矩阵视图 -->
    <div class="matrix-wrap" v-if="phases.length && lines.length">
      <table class="matrix-table">
        <thead>
          <tr>
            <th class="corner-cell">技术线 \\ 阶段</th>
            <th v-for="p in phases" :key="p.id" class="phase-header">{{ p.name }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in lines" :key="line.id">
            <td class="line-header">
              <el-tag size="small" type="info">{{ line.short_name || line.name }}</el-tag>
            </td>
            <td v-for="phase in phases" :key="phase.id" class="matrix-cell">
              <div
                v-for="dv in getCellItems(line.id, phase.id)"
                :key="dv.id"
                class="cell-item"
                :class="'cell-' + dv.status"
                @click="openDialog(dv)"
                :title="dv.name"
              >
                <span class="cell-dot"></span>
                <span class="cell-name">{{ dv.name }}</span>
                <el-dropdown v-if="matchStd(dv)" trigger="click" size="small" @command="cmd => tplCmd(cmd, dv)" @click.stop>
                  <el-icon class="cell-tpl" :title="'模板：' + matchStd(dv).name"><Document /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="download">下载模板</el-dropdown-item>
                      <el-dropdown-item v-if="isAdmin" command="upload">{{ matchStd(dv).template_path ? '更换模板' : '上传模板' }}</el-dropdown-item>
                      <el-dropdown-item v-if="isAdmin && matchStd(dv).template_path" command="remove" divided>删除模板</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-icon v-else class="cell-tpl cell-tpl-none" @click.stop="noStdHint(dv)" title="未匹配到标准"><Document /></el-icon>
              </div>
              <div
                class="cell-add"
                @click="openDialog(null, phase.id, line.id)"
                title="添加交付物"
              >
                +
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 列表视图 -->
    <div style="margin-top:16px">
      <el-table :data="filteredItems" stripe size="small">
        <el-table-column prop="name" label="交付物名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="phase?.name" label="阶段" width="100" />
        <el-table-column prop="line?.name" label="技术线" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="owner?.name" label="负责人" width="80" />
        <el-table-column prop="submitted_date" label="提交日期" width="110" />
        <el-table-column label="文件" width="170">
          <template #default="{row}">
            <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <a v-if="row.file_path" :href="fileUrl(row.file_path)" target="_blank" style="font-size:12px;color:var(--primary)" :title="fileName(row.file_path)">{{ fileName(row.file_path) }}</a>
              <el-tag v-if="(row.attachments || []).length" size="small" type="success" :title="'附件：' + (row.attachments || []).map(a => a.file_name).join('、')">📎 {{ (row.attachments || []).length }}</el-tag>
              <span v-if="!row.file_path && !(row.attachments || []).length" style="color:var(--text-muted);font-size:12px">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{row}">
            <el-dropdown trigger="click" size="small" @command="cmd => tplCmd(cmd, row)">
              <el-button type="warning" link size="small">📄 模板<el-icon style="margin-left:2px"><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <template v-if="matchStd(row)">
                    <el-dropdown-item command="download">下载模板</el-dropdown-item>
                    <el-dropdown-item v-if="isAdmin" command="upload">{{ matchStd(row).template_path ? '更换模板' : '上传模板' }}</el-dropdown-item>
                    <el-dropdown-item v-if="isAdmin && matchStd(row).template_path" command="remove" divided>删除模板</el-dropdown-item>
                  </template>
                  <el-dropdown-item v-else disabled>未匹配到标准，可在标准维护添加同名标准</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button type="success" link size="small" @click="openAiReport(row)">🤖 AI报告</el-button>
            <el-button type="primary" link size="small" @click="openDialog(row)">编辑</el-button>
            <el-button type="success" link size="small" v-if="row.status === 'not_submitted'" @click="quickSubmit(row)">提交</el-button>
            <el-popconfirm title="确认删除?" @confirm="deleteItem(row.id)">
              <template #reference>
                <el-button type="danger" link size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <input ref="tplInput" type="file" style="display:none" accept=".doc,.docx,.xls,.xlsx,.ppt,.pptx,.pdf,.zip" @change="onTplFile">

    <!-- 编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingItem ? '编辑交付物' : '添加交付物'" width="500px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：电磁可行性分析报告" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="阶段" required>
              <el-select v-model="form.phase_id" style="width:100%">
                <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="技术线">
              <el-select v-model="form.line_id" style="width:100%" clearable>
                <el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="未提交" value="not_submitted" />
            <el-option label="已提交" value="submitted" />
            <el-option label="已评审" value="reviewed" />
            <el-option label="已批准" value="approved" />
            <el-option label="已驳回" value="rejected" />
          </el-select>
        </el-form-item>
        <el-form-item label="主文件">
          <div style="width:100%">
            <div v-if="form.file_path" style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
              <a :href="fileUrl(form.file_path)" target="_blank" style="font-size:12px;color:var(--primary)">📄 {{ fileName(form.file_path) }}</a>
              <el-button link size="small" type="danger" @click="clearFile">清除</el-button>
            </div>
            <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onFileRemove" :on-exceed="onFileExceed"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.zip,.dwg,.step,.stp,.stl,.igs,.iges,.dxf,.mp4,.avi,.mov,.mkv">
              <el-button size="small">📎 选择主文件</el-button>
            </el-upload>
            <div v-if="pendingFile" style="font-size:12px;color:#67c23a;margin-top:4px">已选择：{{ pendingFile.name }}</div>
          </div>
        </el-form-item>
        <el-form-item label="设计资料附件">
          <div style="width:100%">
            <div v-for="att in attList" :key="att.id" style="display:flex;align-items:center;gap:8px;margin-bottom:6px;background:#f9fafb;padding:4px 8px;border-radius:4px">
              <a :href="fileUrl(att.file_path)" target="_blank" style="font-size:12px;color:var(--primary);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" :title="att.file_name">{{ att.file_name }}</a>
              <span style="font-size:11px;color:#9ca3af;flex-shrink:0">{{ fmtSize(att.file_size) }}</span>
              <el-button link size="small" type="danger" style="flex-shrink:0" @click="deleteAtt(att)">删除</el-button>
            </div>
            <div v-for="(pf, i) in pendingFiles" :key="'pf' + i" style="display:flex;align-items:center;gap:8px;margin-bottom:6px;background:#f0f9eb;padding:4px 8px;border-radius:4px">
              <span style="font-size:12px;color:#67c23a;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ pf.name }}</span>
              <span style="font-size:11px;color:#9ca3af;flex-shrink:0">待保存上传</span>
              <el-button link size="small" type="danger" style="flex-shrink:0" @click="removePending(i)">移除</el-button>
            </div>
            <el-upload ref="attUploadRef" :auto-upload="false" :multiple="true" :show-file-list="false"
              :on-change="onAttChange" :on-exceed="onAttExceed"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.zip,.dwg,.step,.stp,.stl,.igs,.iges,.dxf,.mp4,.avi,.mov,.mkv">
              <el-button size="small">📎 添加附件（可多选）</el-button>
            </el-upload>
            <div style="font-size:11px;color:#8f959e;margin-top:2px">三维模型 / 仿真过程视频等设计资料，单个不超过 200MB，保存时自动上传</div>
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
        <el-button type="primary" @click="save">保存</el-button>
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getDeliverables, createDeliverable, updateDeliverable,
  getLines, getPhases, getTeamMembers,
  getStandards, uploadStandardTemplate, deleteStandardTemplate,
} from '../../api/index.js'
import { useAuthStore } from '../../stores/auth.js'
import api from '../../api/index.js'

const props = defineProps({
  projectId: { type: Number, required: true },
})

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)

const lines = ref([])
const phases = ref([])
const members = ref([])
const items = ref([])
const standards = ref([])
const tplTarget = ref(null)
const filterPhase = ref(null)
const filterLine = ref(null)
const dialogVisible = ref(false)
const editingItem = ref(null)
const pendingFile = ref(null)
const pendingFiles = ref([])
const attList = ref([])
const uploadRef = ref(null)
const attUploadRef = ref(null)
const aiDialogVisible = ref(false)
const aiLoading = ref(false)
const aiReportContent = ref('')
const aiReportName = ref('')
const aiMeta = ref('')
const aiFillUrl = ref('')
const aiFillReady = ref(false)
const aiFillLoading = ref(false)

const form = reactive({
  name: '', description: '', phase_id: null, line_id: null,
  status: 'not_submitted', file_path: '', owner_id: null,
})

const filteredItems = computed(() => {
  let list = items.value
  if (filterPhase.value) list = list.filter(d => d.phase_id === filterPhase.value)
  if (filterLine.value) list = list.filter(d => d.line_id === filterLine.value)
  return list
})

function getCellItems(lineId, phaseId) {
  return items.value.filter(d => d.line_id === lineId && d.phase_id === phaseId)
}

// 标准 ↔ 交付物匹配:阶段相同 + 名称双向包含,与标准维护共享同一数据源
function matchStd(dv) {
  return standards.value.find(s =>
    s.phase_id === dv.phase_id &&
    s.name && dv.name && (s.name.includes(dv.name) || dv.name.includes(s.name))
  ) || null
}

function tplCmd(cmd, row) {
  const std = matchStd(row)
  if (!std) return
  if (cmd === 'download') downloadTpl(std)
  else if (cmd === 'upload') { tplTarget.value = std; tplInput.value?.click() }
  else if (cmd === 'remove') removeTpl(std)
}

function noStdHint(dv) {
  ElMessage.info('该交付物未匹配到标准，可在「阶段门评审→标准维护」添加同名标准后关联模板')
}

async function openAiReport(row) {
  aiReportName.value = row.name || '交付物报告'
  aiReportContent.value = ''
  aiMeta.value = ''
  aiFillUrl.value = `/report-gen/fill-deliverable/${row.id}`
  aiFillReady.value = !!(matchStd(row)?.template_path)
  aiDialogVisible.value = true
  aiLoading.value = true
  try {
    const r = await api.get(`/report-gen/deliverable/${row.id}`, { timeout: 180000 })
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

function downloadBlob(res, filename) {
  const url = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportAiDocx() {
  try {
    const r = await api.post('/report-gen/export/docx', { content: aiReportContent.value, title: `${aiReportName.value} - AI报告` }, { responseType: 'blob', timeout: 60000 })
    downloadBlob(r, `${aiReportName.value}_AI报告.docx`)
  } catch (e) { ElMessage.error('Word 导出失败') }
}

async function exportAiPptx() {
  try {
    const r = await api.post('/report-gen/export/pptx', { content: aiReportContent.value, title: `${aiReportName.value} - AI报告` }, { responseType: 'blob', timeout: 60000 })
    downloadBlob(r, `${aiReportName.value}_AI报告.pptx`)
  } catch (e) { ElMessage.error('PPT 导出失败') }
}

async function fillTemplateFile() {
  if (!aiFillReady.value) { ElMessage.warning('该交付物未匹配到标准或标准没有模板，请先在「标准维护」添加同名标准并上传 .docx 模板'); return }
  aiFillLoading.value = true
  try {
    const r = await api.get(aiFillUrl.value, { responseType: 'blob', timeout: 180000 })
    downloadBlob(r, `${aiReportName.value}_模板填充版.docx`)
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

async function downloadTpl(std) {
  try {
    const res = await api.get(`/gate-deliverable-standards/${std.id}/template`, { responseType: 'blob' })
    const ext = std.template_path ? (std.template_path.split('.').pop() || 'docx') : 'docx'
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `模板-${std.name}.${ext}`
    a.click()
    URL.revokeObjectURL(url)
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
    await loadStandards()
  } catch (err) {
    ElMessage.error('上传失败: ' + (err?.response?.data?.detail || err.message))
  }
}

async function removeTpl(std) {
  try {
    await ElMessageBox.confirm(`确认删除「${std.name}」的模板?删除后恢复为自动生成骨架`, '提示', { type: 'warning' })
  } catch (e) { return }
  try {
    await deleteStandardTemplate(std.id)
    ElMessage.success('已删除模板')
    await loadStandards()
  } catch (err) {
    ElMessage.error('删除失败: ' + (err?.response?.data?.detail || err.message))
  }
}

async function loadStandards() {
  standards.value = (await getStandards()).data || []
}

onMounted(async () => {
  await loadStandards()
  const [l, p, m] = await Promise.all([getLines(), getPhases(), getTeamMembers()])
  lines.value = l.data
  phases.value = p.data
  members.value = m.data
  await load()
})

async function load() {
  const params = {}
  if (filterPhase.value) params.phase_id = filterPhase.value
  if (filterLine.value) params.line_id = filterLine.value
  const res = await getDeliverables(props.projectId, params)
  items.value = res.data
}

function onFileChange(file) { pendingFile.value = file.raw }
function onFileRemove() { pendingFile.value = null }
function onFileExceed() { ElMessage.warning('只能选择一个文件') }
function onAttChange(file) { pendingFiles.value.push(file.raw) }
function onAttExceed() { ElMessage.warning('每次最多选择 5 个文件') }
function removePending(i) { pendingFiles.value.splice(i, 1) }
function fmtSize(n) {
  if (!n) return ''
  return n >= 1048576 ? (n / 1048576).toFixed(1) + 'MB' : Math.max(1, Math.round(n / 1024)) + 'KB'
}
async function deleteAtt(att) {
  try {
    await api.delete(`/deliverables/${editingItem.value.id}/attachments/${att.id}`)
    attList.value = attList.value.filter(a => a.id !== att.id)
    ElMessage.success('附件已删除')
  } catch (e) { ElMessage.error('删除失败: ' + (e?.response?.data?.detail || e.message)) }
}
async function loadAtts(deliverableId) {
  attList.value = deliverableId ? ((await api.get(`/deliverables/${deliverableId}/attachments`)).data || []) : []
}
function fileName(p) {
  const n = String(p || '').split(/[\\/]/).pop() || p
  return n.replace(/^[0-9a-f]{8}_/, '') || n
}
function fileUrl(p) { return '/uploads/' + String(p || '').replace(/^[\\/]+/, '') }
async function clearFile() {
  if (!editingItem.value) { form.file_path = ''; return }
  try {
    await updateDeliverable(editingItem.value.id, { file_path: null })
    form.file_path = ''
    ElMessage.success('已清除')
    await load()
  } catch (e) { ElMessage.error('清除失败') }
}

function openDialog(row, phaseId, lineId) {
  editingItem.value = row || null
  pendingFile.value = null
  pendingFiles.value = []
  uploadRef.value?.clearFiles()
  attUploadRef.value?.clearFiles()
  loadAtts(row?.id)
  if (row) {
    Object.assign(form, {
      name: row.name || '', description: row.description || '',
      phase_id: row.phase_id, line_id: row.line_id,
      status: row.status || 'not_submitted',
      file_path: row.file_path || '', owner_id: row.owner_id,
    })
  } else {
    Object.assign(form, {
      name: '', description: '',
      phase_id: phaseId || null, line_id: lineId || null,
      status: 'not_submitted', file_path: '', owner_id: null,
    })
  }
  dialogVisible.value = true
}

async function save() {
  if (!form.name) { ElMessage.warning('请输入名称'); return }
  if (!form.phase_id) { ElMessage.warning('请选择阶段'); return }
  try {
    let id = editingItem.value ? editingItem.value.id : null
    if (editingItem.value) {
      await updateDeliverable(editingItem.value.id, form)
      ElMessage.success('已更新')
    } else {
      const res = await createDeliverable(props.projectId, form)
      id = res.data?.id || id
      ElMessage.success('已添加')
    }
    if (pendingFile.value && id) {
      const fd = new FormData()
      fd.append('file', pendingFile.value)
      const up = await api.post(`/deliverables/${id}/upload-file`, fd)
      form.file_path = up.data.file_path
      pendingFile.value = null
    }
    for (const f of pendingFiles.value) {
      const fd = new FormData()
      fd.append('file', f)
      await api.post(`/deliverables/${id}/attachments`, fd)
    }
    pendingFiles.value = []
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('操作失败: ' + (e?.response?.data?.detail || e.message))
  }
}

async function quickSubmit(row) {
  await updateDeliverable(row.id, { status: 'submitted', submitted_date: new Date().toISOString().slice(0, 10) })
  ElMessage.success('已提交')
  await load()
}

async function deleteItem(id) {
  // Soft delete via update
  const res = await api.delete(`/deliverables/${id}`)
  ElMessage.success('已删除')
  await load()
}

function statusType(s) {
  return { not_submitted: 'info', submitted: 'warning', reviewed: '', approved: 'success', rejected: 'danger' }[s] || 'info'
}
function statusLabel(s) {
  return { not_submitted: '未提交', submitted: '已提交', reviewed: '已评审', approved: '已批准', rejected: '已驳回' }[s] || s
}
</script>

<style scoped>
.matrix-wrap {
  overflow-x: auto;
  margin-bottom: 16px;
}
.matrix-table {
  border-collapse: collapse;
  width: 100%;
  min-width: 900px;
  font-size: 12px;
}
.matrix-table th, .matrix-table td {
  border: 1px solid #e4e7ed;
  padding: 4px;
  vertical-align: top;
}
.corner-cell {
  background: #f5f7fa;
  width: 90px;
  font-weight: 600;
}
.phase-header {
  background: #f5f7fa;
  text-align: center;
  font-weight: 600;
  padding: 8px 4px !important;
  min-width: 130px;
}
.line-header {
  background: #fafafa;
  text-align: center;
}
.matrix-cell {
  min-height: 60px;
  position: relative;
}
.cell-item {
  padding: 3px 6px;
  margin: 2px 0;
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  transition: background 0.2s;
}
.cell-item:hover { opacity: 0.8; }
.cell-not_submitted { background: #f0f2f5; }
.cell-submitted { background: #e6f0ff; }
.cell-reviewed { background: #e6f7ff; }
.cell-approved { background: #e8f5e9; }
.cell-rejected { background: #fef0f0; }
.cell-dot {
  width: 6px; height: 6px; border-radius: 50%;
}
.cell-not_submitted .cell-dot { background: #c0c4cc; }
.cell-submitted .cell-dot { background: #409eff; }
.cell-reviewed .cell-dot { background: #67c23a; }
.cell-approved .cell-dot { background: #67c23a; }
.cell-rejected .cell-dot { background: #f56c6c; }
.cell-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.cell-tpl {
  margin-left: auto;
  flex-shrink: 0;
  cursor: pointer;
  font-size: 12px;
  color: #e6a23c;
  padding: 1px 2px;
}
.cell-tpl:hover { opacity: 0.75; }
.cell-tpl-none { color: #c0c4cc; }
.ai-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  font-size: 13px;
}
.cell-add {
  text-align: center;
  color: #c0c4cc;
  cursor: pointer;
  padding: 2px;
  font-size: 14px;
}
.cell-add:hover { color: #409eff; }
</style>
