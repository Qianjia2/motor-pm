<template>
  <div class="rg-wrap">
    <el-row :gutter="16">
      <el-col :span="8">
        <div class="card" style="padding:16px">
          <div class="card-title" style="margin-bottom:12px">报告类型</div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <div v-for="t in types" :key="t.key"
              :class="['rg-type-card', { active: reportType === t.key }]"
              @click="reportType = t.key">
              <div class="rg-type-name">{{ t.name }}</div>
              <div class="rg-type-info">{{ t.sections.length }}个章节 · {{ t.sections.slice(0,3).join(' / ') }}</div>
            </div>
          </div>

          <div style="margin-top:12px">
            <div class="card-title" style="margin-bottom:8px">补充说明（可选）</div>
            <el-input v-model="context" type="textarea" :rows="2" placeholder="额外要求、重点关注内容等..." />
          </div>

          <div style="margin-top:12px">
            <div class="card-title" style="margin-bottom:8px">数据来源</div>
            <div style="font-size:12px;color:var(--text-secondary);line-height:1.8">
              <div>里程碑 {{ dataStats.milestones }} 条</div>
              <div>需求 {{ dataStats.requirements }} 条</div>
              <div>周报 {{ dataStats.reports }} 期</div>
              <div>风险/问题 {{ dataStats.risks }} 条</div>
              <div>变更 {{ dataStats.changes }} 条</div>
              <div>文档 {{ dataStats.docs }} 个</div>
            </div>
          </div>

          <div style="margin-top:12px">
            <div class="card-title" style="margin-bottom:8px">📷 图片转报告</div>
            <input type="file" ref="imageInput" multiple accept="image/png,image/jpeg,image/jpg,image/gif,image/bmp,image/webp" style="display:none" @change="onImagesSelected" />
            <el-button @click="$refs.imageInput.click()" :loading="imageLoading" style="width:100%">
              📷 上传图片（可多选）→ AI 生成报告
            </el-button>
            <div v-if="imageLoading" style="text-align:center;padding:8px;font-size:12px;color:var(--text-secondary)">
              正在 OCR 识别 + AI 生成报告...
            </div>
          </div>

          <el-button type="primary" style="margin-top:16px;width:100%" @click="generate" :loading="generating">
            🤖 AI 生成报告
          </el-button>
        </div>
      </el-col>

      <el-col :span="16">
        <div class="card" style="padding:16px;min-height:500px">
          <div class="card-header">
            <span class="card-title">{{ currentTypeName || '选择报告类型' }}</span>
            <span v-if="sourceLabel" style="margin-left:12px;font-size:12px;color:var(--text-muted);background:#f0f5ff;padding:2px 10px;border-radius:10px">
              {{ sourceLabel }}<template v-if="templateUsed">: {{ templateUsed }}</template>
            </span>
            <div v-if="reportContent" style="display:flex;gap:4px;flex-wrap:wrap;align-items:center">
              <template v-if="reportSource === 'ocr_image' && suggestedPhase">
                <span style="font-size:12px;color:var(--text-secondary)">保存到:</span>
                <el-select v-model="savePhaseId" size="small" style="width:130px">
                  <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
                <el-button size="small" type="success" @click="saveToPhase" :loading="savingToPhase">💾 保存</el-button>
              </template>
              <el-button size="small" @click="toggleEdit">{{ editing ? '👁 预览' : '✏️ 编辑' }}</el-button>
              <el-button size="small" @click="copyContent">📋 复制</el-button>
              <el-button size="small" @click="downloadMd">📥 .md</el-button>
              <el-button size="small" @click="downloadDocx" :loading="downloadingDocx">📄 .docx</el-button>
              <el-button size="small" @click="downloadPptx" :loading="downloadingPptx">📊 .pptx</el-button>
            </div>
          </div>

          <div v-if="generating || imageLoading" style="text-align:center;padding:60px">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <p style="margin-top:12px;color:var(--text-secondary)">AI 正在分析项目数据并生成报告...</p>
            <p style="font-size:12px;color:var(--text-muted)">预计 10-30 秒</p>
          </div>

          <div v-else-if="error" style="text-align:center;padding:60px;color:#ef4444">
            {{ error }}
          </div>

          <div v-else-if="reportContent && editing" style="padding:8px">
            <el-input v-model="reportContent" type="textarea" :rows="22" style="font-size:13px;line-height:1.8;font-family:monospace" placeholder="编辑报告内容..." />
          </div>

          <div v-else-if="reportContent" class="markdown-body" v-html="renderedContent" style="padding:8px;line-height:1.8;font-size:14px">
          </div>

          <div v-else style="text-align:center;padding:60px;color:var(--text-muted)">
            选择报告类型后点击「AI 生成报告」
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })

const types = ref([])
const reportType = ref('')
const context = ref('')
const templateText = ref('')
const generating = ref(false)
const reportContent = ref('')
const error = ref('')
const dataStats = ref({ milestones: 0, reports: 0, risks: 0, changes: 0, docs: 0, requirements: 0 })
const imageLoading = ref(false)
const suggestedPhase = ref(null)
const savePhaseId = ref(null)
const savingToPhase = ref(false)
const phases = ref([])

async function loadPhases() {
  try { const r = await api.get('/lookups/phases'); phases.value = r.data || [] } catch(e) {}
}

async function saveToPhase() {
  if (!savePhaseId.value) { ElMessage.warning('请选择阶段'); return }
  savingToPhase.value = true
  try {
    await api.post('/report-gen/save-image-report', {
      project_id: props.projectId,
      phase_id: savePhaseId.value,
      content: reportContent.value,
      title: `[图片识别] ${currentTypeName.value}`,
      report_type: reportType.value || 'stage_report',
    })
    ElMessage.success('报告已保存到对应阶段')
  } catch(e) { ElMessage.error('保存失败') }
  finally { savingToPhase.value = false }
}

async function onImagesSelected(e) {
  const files = e.target.files
  if (!files || files.length === 0) return
  imageLoading.value = true
  error.value = ''
  reportContent.value = ''
  editing.value = false
  try {
    const fd = new FormData()
    for (const f of files) fd.append('files', f)
    fd.append('report_type', reportType.value || 'stage_report')
    fd.append('context', context.value || '')
    const r = await api.post('/report-gen/image-to-report', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 300000,
    })
    const d = r.data
    reportContent.value = d.content
    templateUsed.value = null
    reportSource.value = 'ocr_image'
    if (d.suggested_phase) {
      suggestedPhase.value = d.suggested_phase
      savePhaseId.value = d.suggested_phase.id
    }
    // Build status message with stats
    const stats = d.ocr_stats || {}
    let msg = `${stats.total || files.length}张: 识别${stats.recognized || '?'}张`
    if (d.ai_failed) msg += ' (AI失败，显示原始OCR文字)'
    if (d.ocr_errors?.length) msg += ` | ${d.ocr_errors.length}张有问题`
    ElMessage.success(msg)
    // Show errors as a warning if partial
    if (d.ocr_errors?.length && stats.recognized > 0) {
      setTimeout(() => {
        ElMessage.warning(`部分图片失败: ${d.ocr_errors.slice(0,3).join('; ')}`)
      }, 500)
    }
    // Failure case
    if (!d.ok) {
      error.value = d.detail + '\n' + (d.ocr_errors || []).join('\n')
      if (d.tips) error.value += '\n\n' + d.tips.join('\n')
      reportContent.value = ''
    }
  } catch (e) {
    error.value = e?.response?.data?.detail || '图片识别失败'
  } finally {
    imageLoading.value = false
    e.target.value = ''
  }
}

const currentTypeName = computed(() => types.value.find(t => t.key === reportType.value)?.name || '')

const renderedContent = computed(() => {
  if (!reportContent.value) return ''
  // Simple markdown render
  let html = reportContent.value
    .replace(/### (.+)/g, '<h4>$1</h4>')
    .replace(/## (.+)/g, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- (.+)/g, '\n<li>$1</li>')
    .replace(/(\n<li>.*<\/li>)+/g, '<ul>$&</ul>')
    .replace(/\n/g, '<br>')
    .replace(/```json\n?([\s\S]*?)```/g, '<pre><code>$1</code></pre>')
  return html
})

onMounted(async () => {
  try { const r = await api.get('/report-gen/types'); types.value = r.data || [] } catch (e) {}
  loadStats()
  loadPhases()
})

async function loadStats() {
  try {
    const [ms, reqs, rpts, risks, changes, docs] = await Promise.all([
      api.get(`/projects/${props.projectId}/milestones`),
      api.get(`/projects/${props.projectId}/requirements`),
      api.get(`/projects/${props.projectId}/reports`),
      api.get(`/projects/${props.projectId}/risks`),
      api.get(`/projects/${props.projectId}/changes`),
      api.get(`/projects/${props.projectId}/docs`),
    ])
    dataStats.value = {
      milestones: (ms.data || []).length,
      requirements: (reqs.data || []).length,
      reports: (rpts.data || []).length,
      risks: (risks.data || []).length,
      changes: (changes.data || []).length,
      docs: (docs.data || []).length,
      tests: (tests.data || []).length,
    }
  } catch (e) {}
}

const templateUsed = ref(null)
const reportSource = ref('')
const sourceLabel = computed(() => {
  if (reportSource.value === 'library') return '📚 模版库匹配'
  if (reportSource.value === 'user') return '📋 用户提供模板'
  if (reportSource.value === 'ai_freeform') return '🤖 AI 自由格式'
  if (reportSource.value === 'ocr_image') return '📷 图片识别转报告'
  return ''
})

async function generate() {
  if (!reportType.value) { ElMessage.warning('请选择报告类型'); return }
  generating.value = true; error.value = ''; reportContent.value = ''
  templateUsed.value = null; reportSource.value = ''; editing.value = false
  try {
    const params = { type: reportType.value }
    if (context.value) params.context = context.value
    if (templateText.value) params.template = templateText.value.slice(0, 5000)
    const r = await api.get(`/report-gen/generate/${props.projectId}`, { params, timeout: 180000 })
    reportContent.value = r.data.content
    templateUsed.value = r.data.template_used || null
    reportSource.value = r.data.source || ''
    if (r.data.template_used) {
      ElMessage.success(`报告已生成（使用模板: ${r.data.template_used}）`)
    } else {
      ElMessage.success('报告已生成（AI 自由格式）')
    }
  } catch (e) {
    if (e.code === 'ECONNABORTED') { error.value = '生成超时（3分钟），AI 仍在处理中，请重试' }
    else if (e.response) { error.value = `服务器错误(${e.response.status}): ${e.response.data?.detail || JSON.stringify(e.response.data).slice(0,200)}` }
    else if (e.request) { error.value = `网络请求失败: ${e.message}` }
    else { error.value = `生成失败: ${e.message}` }
  } finally { generating.value = false }
}

const downloadingDocx = ref(false)
const downloadingPptx = ref(false)
const editing = ref(false)
function toggleEdit() { editing.value = !editing.value }

function copyContent() { navigator.clipboard.writeText(reportContent.value); ElMessage.success('已复制到剪贴板') }
function downloadMd() {
  const blob = new Blob([reportContent.value], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a'); a.href = url
  a.download = `${currentTypeName.value}_${new Date().toISOString().slice(0,10)}.md`; a.click()
  URL.revokeObjectURL(url)
}
async function downloadDocx() {
  downloadingDocx.value = true
  try {
    const r = await api.post('/report-gen/export/docx', { content: reportContent.value, title: currentTypeName.value }, { responseType: 'blob', timeout: 30000 })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url
    a.download = `${currentTypeName.value}_${new Date().toISOString().slice(0,10)}.docx`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('Word 下载完成')
  } catch(e) { ElMessage.error('Word 导出失败') }
  finally { downloadingDocx.value = false }
}
async function downloadPptx() {
  downloadingPptx.value = true
  try {
    const r = await api.post('/report-gen/export/pptx', { content: reportContent.value, title: currentTypeName.value }, { responseType: 'blob', timeout: 30000 })
    const url = URL.createObjectURL(r.data)
    const a = document.createElement('a'); a.href = url
    a.download = `${currentTypeName.value}_${new Date().toISOString().slice(0,10)}.pptx`; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('PPT 下载完成')
  } catch(e) { ElMessage.error('PPT 导出失败') }
  finally { downloadingPptx.value = false }
}
</script>

<style scoped>
.rg-wrap { }
.rg-type-card { border: 2px solid #e5e7eb; border-radius: 8px; padding: 10px 14px; cursor: pointer; transition: all .2s; }
.rg-type-card:hover { border-color: #93c5fd; background: #f0f7ff; }
.rg-type-card.active { border-color: #3b82f6; background: #eff6ff; }
.rg-type-name { font-weight: 600; font-size: 13px; color: #1e3a5f; }
.rg-type-info { font-size: 11px; color: #909399; margin-top: 3px; }
.markdown-body h3 { color: #1e3a5f; border-bottom: 1px solid #e5e7eb; padding-bottom: 6px; margin: 20px 0 10px; }
.markdown-body h4 { color: #374151; margin: 14px 0 8px; }
.markdown-body ul { padding-left: 20px; }
.markdown-body li { line-height: 1.8; }
.markdown-body strong { color: #1f2937; }
.markdown-body pre { background: #f9fafb; padding: 10px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
</style>
