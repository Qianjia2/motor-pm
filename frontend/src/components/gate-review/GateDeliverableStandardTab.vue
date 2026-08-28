<template>
  <div class="gds-tab">
    <div class="toolbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button value="check">对照检查</el-radio-button>
        <el-radio-button value="manage">标准维护</el-radio-button>
      </el-radio-group>
      <el-button v-if="mode === 'manage' && isAdmin" type="primary" size="small" style="margin-left:12px" @click="openDialog(null)">+ 新增标准</el-button>
      <el-button v-if="mode === 'check'" size="small" style="margin-left:12px" @click="loadCheck">刷新</el-button>
    </div>

    <!-- 对照检查 -->
    <div v-if="mode === 'check'" class="check-view">
      <div class="filter-row">
        <el-select v-model="checkPhaseId" placeholder="选择阶段" size="small" style="width:220px" @change="loadCheck">
          <el-option-group v-for="tg in phaseTypeGroups" :key="tg.type" :label="tg.label">
            <el-option v-for="p in tg.phases" :key="p.id" :label="`${p.code || ''} ${p.name}`" :value="p.id" />
          </el-option-group>
        </el-select>
        <el-select v-model="checkProjectId" placeholder="全部项目" clearable size="small" style="width:220px;margin-left:8px" @change="loadCheck">
          <el-option-group v-for="tg in projectTypeGroups" :key="tg.type" :label="tg.label">
            <el-option v-for="pr in tg.phases" :key="pr.id" :label="pr.name" :value="pr.id" />
          </el-option-group>
        </el-select>
      </div>
      <el-table v-loading="checkLoading" :data="checkData.standards || []" size="small" class="check-table">
        <el-table-column type="expand">
          <template #default="{ row }">
            <el-table :data="row.projects || []" size="small" class="proj-check-table">
              <el-table-column label="项目" min-width="220">
                <template #default="{ row: pr }">
                  <span class="p-link" @click="$router.push(`/projects/${pr.project_id}`)">{{ pr.project_name }}</span>
                </template>
              </el-table-column>
              <el-table-column label="匹配交付物" min-width="180">
                <template #default="{ row: pr }">
                  <div v-if="(pr.deliverables || []).length">
                    <div v-for="dl in pr.deliverables" :key="dl.deliverable_id" style="display:flex;align-items:center;gap:4px;padding:1px 0">
                      <span>{{ dl.deliverable_name }}</span>
                      <el-tag :type="statusTag(dl.status)" size="small">{{ statusLabel(dl.status) }}</el-tag>
                    </div>
                  </div>
                  <span v-else class="t-muted">—</span>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="{ row: pr }">
                  <el-tag :type="statusTag(pr.status)" size="small">{{ statusLabel(pr.status) }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="提交日期" width="110">
                <template #default="{ row: pr }">{{ pr.submitted_date || '—' }}</template>
              </el-table-column>
              <el-table-column label="负责人" width="100">
                <template #default="{ row: pr }">{{ pr.owner_name || '—' }}</template>
              </el-table-column>
            </el-table>
          </template>
        </el-table-column>
        <el-table-column label="交付物标准" min-width="200">
          <template #default="{ row }">
            <div>
              <span class="std-name">{{ row.name }}</span>
              <el-tag v-if="row.required" type="danger" size="small" style="margin-left:6px">必需</el-tag>
              <el-tag v-else type="info" size="small" style="margin-left:6px">可选</el-tag>
              <div v-if="row.description" class="std-desc">{{ row.description }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="通过标准" min-width="240">
          <template #default="{ row }">
            <span v-if="row.acceptance_criteria" class="std-criteria">{{ row.acceptance_criteria }}</span>
            <span v-else class="t-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="责任角色" width="120">
          <template #default="{ row }">
            <span v-if="row.responsible_role" class="std-role">{{ row.responsible_role }}</span>
            <span v-else class="t-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="100">
          <template #default="{ row }">{{ catLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="完成情况" width="160">
          <template #default="{ row }">
            <span class="done-count" :class="{ 'all-done': doneCount(row) === (row.projects || []).length && (row.projects || []).length > 0 }">
              {{ doneCount(row) }}/{{ (row.projects || []).length }} 已达标
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!checkLoading && !(checkData.standards || []).length" class="empty-hint">
        该阶段暂无标准交付物，请到「标准维护」添加
      </div>
    </div>

    <!-- 标准维护 -->
    <div v-else class="manage-view">
      <div v-for="tg in typeGroups" :key="tg.type" class="gds-type-group" v-show="isAdmin || tg.standardsCount">
        <div class="gds-type-head" @click="toggleType(tg.type)">
          <span class="gds-arrow" :class="{ open: !typeCollapsed[tg.type] }">▶</span>
          <span class="gds-type-name">{{ tg.label }}</span>
          <el-tag :type="tg.type === 'software' ? 'warning' : 'success'" size="small" effect="dark">{{ tg.type === 'software' ? '软件开发' : '系统集成' }}</el-tag>
          <span class="gds-count">{{ tg.phases.length }} 个阶段 · {{ tg.standardsCount }} 项标准</span>
          <span class="gds-more">
            <el-button v-if="isAdmin" link size="small" @click.stop="openDialog(null, tg.phases[0]?.id)">+ 新增</el-button>
          </span>
        </div>
        <div v-show="!typeCollapsed[tg.type]" class="gds-type-body">
          <div v-for="p in tg.phases" :key="p.id" class="gds-group" v-show="isAdmin || stdsOf(p).length">
            <div class="gds-group-head" @click="toggleGroup(p.id)">
              <span class="gds-arrow" :class="{ open: !collapsed[p.id] }">▶</span>
              <span class="gds-phase">{{ p.code || '' }} {{ p.name }}</span>
              <span class="gds-count">{{ stdsOf(p).length }} 项标准</span>
              <span class="gds-more">
                <el-button v-if="isAdmin" link size="small" @click.stop="openDialog(null, p.id)">+ 新增</el-button>
              </span>
            </div>
            <div v-show="!collapsed[p.id]" class="gds-group-body">
              <div v-for="row in stdsOf(p)" :key="row.id" class="gds-item">
                <div class="gds-item-top">
                  <span class="std-name">{{ row.name }}</span>
                  <el-tag :type="tagType(row.category)" size="small" effect="plain">{{ catLabel(row.category) }}</el-tag>
                  <el-tag :type="row.required ? 'danger' : 'info'" size="small">{{ row.required ? '必需' : '可选' }}</el-tag>
                  <span v-if="row.responsible_role" class="std-role">👤 {{ row.responsible_role }}</span>
                  <span class="gds-item-ops">
                    <el-button link size="small" type="primary" @click="previewTpl(row)">📄 模板</el-button>
                    <el-button v-if="row.template_path" link size="small" @click="downloadTpl(row)">下载</el-button>
                    <template v-if="isAdmin">
                      <el-button v-if="!row.template_path" link size="small" @click="pickTemplate(row)">上传模板</el-button>
                      <el-button v-else link size="small" @click="pickTemplate(row)">更换</el-button>
                      <el-button v-if="row.template_path" link size="small" type="danger" @click="removeTemplate(row)">删模板</el-button>
                      <el-button link size="small" @click="openDialog(row)">编辑</el-button>
                      <el-button link size="small" type="danger" @click="del(row)">删除</el-button>
                    </template>
                  </span>
                </div>
                <div v-if="row.description" class="gds-item-desc" :title="row.description">{{ row.description }}</div>
                <div v-if="row.acceptance_criteria" class="gds-item-criteria" :title="row.acceptance_criteria">
                  <span class="c-label">通过标准</span>{{ row.acceptance_criteria }}
                </div>
              </div>
              <div v-if="!stdsOf(p).length" class="gds-empty">暂无标准</div>
            </div>
          </div>
        </div>
      </div>
      <div v-if="!isAdmin" class="empty-hint">仅管理员可维护标准清单</div>
    </div>

    <input ref="tplInput" type="file" style="display:none" accept=".doc,.docx,.xls,.xlsx,.ppt,.pptx,.pdf,.zip" @change="onTplFile">

    <!-- 模板预览弹窗 -->
    <FilePreviewDialog ref="previewRef" />

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑标准' : '新增标准'" width="480">
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="阶段" required>
          <el-select v-model="form.phase_id" placeholder="选择阶段" style="width:100%">
            <el-option v-for="p in phases" :key="p.id" :label="`${p.code || ''} ${p.name}`" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如:需求规格书" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width:100%">
            <el-option label="文档" value="document" />
            <el-option label="报告" value="report" />
            <el-option label="审批" value="approval" />
            <el-option label="其他" value="other" />
          </el-select>
        </el-form-item>
        <el-form-item label="必需">
          <el-switch v-model="form.required" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="通过标准">
          <el-input v-model="form.acceptance_criteria" type="textarea" :rows="3" placeholder="满足哪些条件即可判定该交付物通过" />
        </el-form-item>
        <el-form-item label="责任角色">
          <el-input v-model="form.responsible_role" placeholder="如:系统工程师、项目经理" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api, { getStandards, createStandard, updateStandard, deleteStandard, getChecklist, uploadStandardTemplate, deleteStandardTemplate } from '../../api/index.js'
import FilePreviewDialog from '../common/FilePreviewDialog.vue'

const props = defineProps({
  phases: { type: Array, default: () => [] },
  projects: { type: Array, default: () => [] },
  isAdmin: { type: Boolean, default: false },
  projectType: { type: String, default: 'all' }, // all|hardware|software
})

const mode = ref('check')
const standards = ref([])
const checkData = ref({ standards: [] })
const checkPhaseId = ref(null)
const checkProjectId = ref(null)
const checkLoading = ref(false)
const dialogVisible = ref(false)
const saving = ref(false)
const form = ref({ id: null, phase_id: null, name: '', category: 'document', required: true, sort_order: 0, description: '', acceptance_criteria: '', responsible_role: '' })

function phaseName(id) {
  const p = props.phases.find(x => x.id === id)
  return p ? `${p.code || ''} ${p.name}` : id
}
function catLabel(c) {
  return { document: '文档', report: '报告', approval: '审批', other: '其他' }[c] || c || '—'
}
function statusTag(s) {
  return { approved: 'success', submitted: 'primary', reviewed: 'primary', rejected: 'warning', not_submitted: 'info', missing: 'danger' }[s] || 'info'
}
function statusLabel(s) {
  return { approved: '已批准', submitted: '已提交', reviewed: '已评审', rejected: '已驳回', not_submitted: '未提交', missing: '缺失' }[s] || s
}
function doneCount(row) {
  return (row.projects || []).filter(p => p.status === 'approved' || p.status === 'submitted').length
}

// 标准维护:按项目类型 → 阶段 两级分组 + 折叠
const collapsed = ref({})
const typeCollapsed = ref({})
function stdsOf(p) {
  return standards.value
    .filter(s => s.phase_id === p.id)
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
}
function toggleGroup(id) {
  collapsed.value = { ...collapsed.value, [id]: !collapsed.value[id] }
}
function toggleType(type) {
  typeCollapsed.value = { ...typeCollapsed.value, [type]: !typeCollapsed.value[type] }
}
function groupByType(items) {
  const map = {}
  for (const it of items) {
    const t = it.project_type === 'software' ? 'software' : 'hardware'
    if (!map[t]) map[t] = { type: t, label: t === 'software' ? '软件开发项目' : '系统集成开发项目', phases: [] }
    map[t].phases.push(it)
  }
  return Object.values(map)
}
const phaseTypeGroups = computed(() => groupByType(props.phases))
const projectTypeGroups = computed(() => groupByType(props.projects))
const typeGroups = computed(() => groupByType(props.phases).map(tg => ({
  type: tg.type,
  label: tg.label,
  phases: tg.phases,
  standardsCount: tg.phases.reduce((s, p) => s + stdsOf(p).length, 0),
})))
function tagType(c) {
  return { document: 'info', report: 'warning', approval: 'success', other: 'default' }[c] || 'info'
}

// ── 模板上传/下载/删除 ──
const tplTarget = ref(null)
const tplInput = ref(null)
function pickTemplate(row) {
  tplTarget.value = row
  tplInput.value?.click()
}
async function onTplFile(e) {
  const f = e.target.files?.[0]
  e.target.value = ''
  if (!f || !tplTarget.value) return
  const fd = new FormData()
  fd.append('file', f)
  try {
    await uploadStandardTemplate(tplTarget.value.id, fd)
    ElMessage.success('模板已上传')
    await loadStandards()
  } catch (err) {
    ElMessage.error('上传失败: ' + (err?.response?.data?.detail || err.message))
  }
  tplTarget.value = null
}
const previewRef = ref(null)
async function previewTpl(row) {
  try {
    const res = await api.get(`/gate-deliverable-standards/${row.id}/template`, { responseType: 'blob' })
    const ext = row.template_path ? (row.template_path.split('.').pop() || 'docx') : 'docx'
    await previewRef.value.openBlob(res.data, `模板-${row.name}.${ext}`)
  } catch (e) { ElMessage.error('模板获取失败: ' + (e?.response?.data?.detail || e.message)) }
}
async function downloadTpl(row) {
  try {
    const res = await api.get(`/gate-deliverable-standards/${row.id}/template`, { responseType: 'blob' })
    const ext = row.template_path ? (row.template_path.split('.').pop() || 'docx') : 'docx'
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `模板-${row.name}.${ext}`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('模板下载失败')
  }
}
async function removeTemplate(row) {
  await ElMessageBox.confirm(`确认删除「${row.name}」的模板?删除后恢复为自动生成骨架`, '提示', { type: 'warning' })
  await deleteStandardTemplate(row.id)
  ElMessage.success('已删除模板')
  await loadStandards()
}

async function loadStandards() {
  const params = props.projectType === 'all' ? undefined : { project_type: props.projectType }
  standards.value = (await getStandards(params)).data || []
}
async function loadCheck() {
  if (!checkPhaseId.value) return
  checkLoading.value = true
  try {
    checkData.value = (await getChecklist({ phase_id: checkPhaseId.value, project_id: checkProjectId.value || undefined })).data || { standards: [] }
  } finally { checkLoading.value = false }
}
function openDialog(row, phaseId) {
  form.value = row
    ? { id: row.id, phase_id: row.phase_id, name: row.name, category: row.category, required: row.required, sort_order: row.sort_order, description: row.description, acceptance_criteria: row.acceptance_criteria || '', responsible_role: row.responsible_role || '' }
    : { id: null, phase_id: phaseId ?? (props.phases[0]?.id || null), name: '', category: 'document', required: true, sort_order: 0, description: '', acceptance_criteria: '', responsible_role: '' }
  dialogVisible.value = true
}
async function save() {
  if (!form.value.phase_id || !form.value.name.trim()) { ElMessage.warning('阶段和名称必填'); return }
  saving.value = true
  try {
    if (form.value.id) await updateStandard(form.value.id, form.value)
    else await createStandard(form.value)
    dialogVisible.value = false
    ElMessage.success('已保存')
    await loadStandards()
  } finally { saving.value = false }
}
async function del(row) {
  await ElMessageBox.confirm(`确认删除标准「${row.name}」?`, '提示', { type: 'warning' })
  await deleteStandard(row.id)
  ElMessage.success('已删除')
  await loadStandards()
}

onMounted(async () => {
  await loadStandards()
  if (props.phases.length) checkPhaseId.value = props.phases[0].id
})
watch(() => props.phases, (v) => {
  if (v.length && !checkPhaseId.value) { checkPhaseId.value = v[0].id; loadCheck() }
})
watch(checkPhaseId, (v) => { if (v) loadCheck() })
// 项目类型切换:重载标准 + 重置对照检查的阶段选择
watch(() => props.projectType, async () => {
  await loadStandards()
  checkPhaseId.value = props.phases[0]?.id || null
  if (checkPhaseId.value) loadCheck()
})
</script>

<style scoped>
.gds-tab { padding: 4px 0; }
.toolbar { display: flex; align-items: center; margin-bottom: 10px; }
.filter-row { display: flex; align-items: center; margin-bottom: 10px; }
.check-table { width: 100%; }
.proj-check-table { margin: 4px 20px 8px; width: calc(100% - 40px); }
.std-name { font-weight: 600; }
.std-desc { font-size: 12px; color: var(--text-muted); margin-top: 2px; line-height: 1.5; }
.std-criteria { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.std-role { font-size: 12px; color: var(--text-secondary); }
.done-count { font-size: 12px; color: var(--text-secondary); }
.all-done { color: #10b981; font-weight: 600; }

/* 标准维护:按项目类型 → 阶段 两级分组 */
.manage-view { display: flex; flex-direction: column; gap: 14px; }
.gds-type-group { border: 1px solid var(--border, #e5e7eb); border-radius: 10px; overflow: hidden; background: #fefefe; }
.gds-type-head { display: flex; align-items: center; gap: 8px; padding: 10px 14px; cursor: pointer; background: #f3f5f9; user-select: none; }
.gds-type-head:hover { background: #eceff5; }
.gds-type-name { font-weight: 700; font-size: 14px; }
.gds-type-body { display: flex; flex-direction: column; gap: 10px; padding: 12px; background: #fbfbfc; }
.gds-group { background: #fff; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; overflow: hidden; }
.gds-group-head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; cursor: pointer; background: #fafafa; user-select: none; }
.gds-group-head:hover { background: #f3f4f6; }
.gds-arrow { font-size: 10px; color: var(--text-muted); transition: transform .2s; }
.gds-arrow.open { transform: rotate(90deg); }
.gds-phase { font-weight: 600; font-size: 13px; }
.gds-count { font-size: 12px; color: var(--text-muted); }
.gds-more { margin-left: auto; }
.gds-group-body { padding: 4px 12px 8px; }
.gds-item { padding: 8px 0; border-bottom: 1px dashed var(--border, #e5e7eb); }
.gds-item:last-child { border-bottom: none; }
.gds-item-top { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gds-item-ops { margin-left: auto; }
.gds-item-desc { font-size: 12px; color: var(--text-muted); margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gds-item-criteria { font-size: 12px; color: var(--text-secondary); margin-top: 3px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.c-label { color: var(--primary); margin-right: 4px; }
.gds-empty { color: var(--text-muted); font-size: 12px; padding: 6px 2px; }
.p-link { cursor: pointer; }
.p-link:hover { color: var(--primary); text-decoration: underline; }
.t-muted { color: var(--text-muted); }
.empty-hint { color: var(--text-muted); font-size: 12px; padding: 14px 4px; }
</style>
