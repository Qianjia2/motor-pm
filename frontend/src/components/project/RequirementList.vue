<template>
  <div>
    <div class="card-header mb-md">
      <div style="display:flex;gap:8px">
        <el-select v-model="filterCat" placeholder="类别筛选" clearable size="small" style="width:130px">
          <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
        </el-select>
        <el-select v-model="filterPri" placeholder="优先级筛选" clearable size="small" style="width:110px">
          <el-option v-for="p in priorities" :key="p" :label="p" :value="p" />
        </el-select>
      </div>
      <div style="display:flex;gap:6px">
        <el-upload :action="uploadUrl" :headers="uploadHeaders" :show-file-list="false"
          accept=".xlsx,.xls" :on-success="onUploaded">
          <el-button size="small">📥 导入Excel</el-button>
        </el-upload>
        <el-button size="small" @click="showAIDialog=true">🤖 AI 辅助录入</el-button>
        <el-button size="small" @click="downloadTemplate">📋 模板</el-button>
        <el-button size="small" @click="exportReqs">📤 导出</el-button>
        <el-button type="primary" size="small" @click="openEdit()">
          <el-icon><Plus /></el-icon> 添加
        </el-button>
      </div>
    </div>

    <el-table :data="filteredReqs" stripe size="small">
      <el-table-column label="优先级" width="70">
        <template #default="{row}">
          <span :class="'tag tag-'+priCls(row.priority)" style="font-size:10px">{{ row.priority }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" width="80">
        <template #default="{row}">
          <span class="tag tag-blue" style="font-size:10px">{{ catLabel(row.category) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="需求标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="来源" width="80">
        <template #default="{row}">{{ row.source || '-' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="75">
        <template #default="{row}">{{ statusLabel(row.status) }}</template>
      </el-table-column>
      <el-table-column label="附件" width="120" align="center">
        <template #default="{row}">
          <div style="display:flex;align-items:center;gap:4px;justify-content:center">
            <template v-if="row.attachment_path">
              <a :href="`/uploads/${row.attachment_path}`" target="_blank"
                style="font-size:12px;color:var(--primary);max-width:80px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
                :title="getFileName(row.attachment_path)">
                {{ getFileName(row.attachment_path) }}
              </a>
              <el-popconfirm title="清除附件?" @confirm="clearAttachment(row)">
                <el-button link size="small" type="danger" title="清除附件">✕</el-button>
              </el-popconfirm>
            </template>
            <el-upload v-else
              :action="`/api/requirements/${row.id}/upload-attachment`" :headers="uploadHeaders"
              :show-file-list="false"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.zip,.dwg,.step,.stp,.stl,.igs,.iges,.dxf,.mp4,.avi,.mov,.mkv"
              :on-success="onAttachUploaded">
              <el-button link size="small" type="primary" title="上传附件">📎</el-button>
            </el-upload>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="版本" width="50">
        <template #default="{row}">V{{ row.version || 1 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="140">
        <template #default="{row}">
          <el-button link size="small" type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link size="small" type="success" v-if="row.deliverable_id" @click="$emit('goDeliverable', row.deliverable_id)">追溯</el-button>
          <el-popconfirm title="删除?" @confirm="delReq(row.id)">
            <template #reference><el-button link size="small" type="danger">删</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="filteredReqs.length === 0" style="text-align:center;padding:40px;color:var(--text-muted)">
      暂无需求，点击"添加需求"录入
      <div style="font-size:12px;margin-top:4px">需求来源：客户/技术协议/标准规范/内部</div>
    </div>

    <!-- Edit Dialog -->
    <el-dialog v-model="showDialog" :title="editing ? '编辑需求' : '添加需求'" width="550px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="需求标题" required>
          <el-input v-model="form.title" placeholder="如：额定功率≥200kW@800V" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="类别">
              <el-select v-model="form.category" style="width:100%">
                <el-option v-for="c in categories" :key="c.value" :label="c.label" :value="c.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" style="width:100%">
                <el-option v-for="p in priorities" :key="p" :label="p" :value="p" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="来源">
              <el-input v-model="form.source" placeholder="客户/协议" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width:100%">
                <el-option label="草稿" value="draft" />
                <el-option label="已评审" value="reviewed" />
                <el-option label="已批准" value="approved" />
                <el-option label="已变更" value="changed" />
                <el-option label="已关闭" value="closed" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="关联交付物">
              <el-select v-model="form.deliverable_id" clearable style="width:100%" placeholder="可选">
                <el-option v-for="d in deliverables" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="需求附件">
          <div style="display:flex;align-items:center;gap:8px">
            <el-upload :show-file-list="false"
              :action="formAttachmentUrl" :headers="uploadHeaders"
              :on-success="onFormAttachUploaded"
              accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg,.pdf,.doc,.docx,.xlsx,.xls,.pptx,.ppt,.txt,.csv,.zip,.dwg,.step,.stp,.stl,.igs,.iges,.dxf,.mp4,.avi,.mov,.mkv">
              <el-button size="small">📎 上传附件</el-button>
            </el-upload>
            <span v-if="form.attachment_path" style="font-size:12px;color:#22c55e">
              ✅ {{ getFileName(form.attachment_path) }}
              <el-button link size="small" type="danger" @click="form.attachment_path='';form._clearAttachment=true">清除</el-button>
            </span>
            <span v-else style="font-size:12px;color:var(--text-muted)">支持图片/文档/工程图/表格/压缩包等</span>
          </div>
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="需求详细说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog=false">取消</el-button>
        <el-button type="primary" @click="saveReq" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <!-- AI辅助录入 -->
    <el-dialog v-model="showAIDialog" title="🤖 AI 辅助录入需求" width="600px">
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">粘贴客户SOR、邮件、微信聊天记录等原始文本，AI自动拆解为需求条目</p>
      <el-input v-model="aiRawText" type="textarea" :rows="10" placeholder="在此粘贴原始文本..." />
      <div v-if="aiItems.length>0" style="margin-top:16px">
        <div style="font-weight:600;margin-bottom:8px">AI 识别到 {{ aiItems.length }} 条需求：</div>
        <div v-for="(item,i) in aiItems" :key="i" class="ai-req-item">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px">
            <el-checkbox v-model="item._selected" />
            <span class="tag" :class="'tag-'+priCls(item.priority)" style="font-size:10px">{{ item.priority }}</span>
            <span class="tag tag-blue" style="font-size:10px">{{ item.category }}</span>
            <strong>{{ item.title }}</strong>
          </div>
          <div style="font-size:12px;color:var(--text-secondary);padding-left:22px">{{ item.description }}</div>
        </div>
      </div>
      <template #footer>
        <el-button @click="showAIDialog=false">取消</el-button>
        <el-button type="primary" @click="parseAI" :loading="aiParsing">🤖 解析文本</el-button>
        <el-button type="success" @click="importAIItems" :disabled="aiItems.filter(x=>x._selected).length===0" :loading="aiImporting">
          导入选中 ({{ aiItems.filter(x=>x._selected).length }})
        </el-button>
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
const uploadUrl = computed(() => `/api/projects/${props.projectId}/requirements/upload`)
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
const formAttachmentUrl = computed(() => editing.value ? `/api/requirements/${editing.value.id}/upload-attachment` : '')
function onUploaded(res) { ElMessage.success(res.message || `导入了${res.created}条`); load() }
function onAttachUploaded(res) { ElMessage.success(res.message || '附件已上传'); load() }
function onFormAttachUploaded(res) {
  form.attachment_path = res.attachment_path
  form._clearAttachment = false
  ElMessage.success('附件已上传')
}
function downloadTemplate() { window.open(`/api/projects/${props.projectId}/requirements/template`, '_blank') }
function exportReqs() { window.open(`/api/projects/${props.projectId}/requirements/export?token=${localStorage.getItem('access_token')}`, '_blank') }
const emit = defineEmits(['goDeliverable'])

const reqs = ref([])
const deliverables = ref([])
const filterCat = ref('')
const filterPri = ref('')
const showDialog = ref(false)
const editing = ref(null)
const saving = ref(false)
// AI-assisted entry
const showAIDialog = ref(false)
const aiRawText = ref('')
const aiParsing = ref(false)
const aiItems = ref([])
const aiImporting = ref(false)

const categories = [
  { value: 'functional', label: '功能' },
  { value: 'performance', label: '性能' },
  { value: 'interface', label: '接口' },
  { value: 'safety', label: '安全' },
  { value: 'reliability', label: '可靠性' },
  { value: 'cost', label: '成本' },
]
const priorities = ['P0', 'P1', 'P2', 'P3']

const form = reactive({ title: '', category: 'functional', priority: 'P1', source: '', status: 'draft', description: '', deliverable_id: null, attachment_path: '', _clearAttachment: false })

const filteredReqs = computed(() => {
  let list = reqs.value
  if (filterCat.value) list = list.filter(r => r.category === filterCat.value)
  if (filterPri.value) list = list.filter(r => r.priority === filterPri.value)
  return list
})

function catLabel(v) { return categories.find(c => c.value === v)?.label || v }
function statusLabel(v) {
  const m = { draft: '草稿', reviewed: '已评审', approved: '已批准', changed: '已变更', closed: '已关闭' }
  return m[v] || v
}
function priCls(v) { return v === 'P0' ? 'red' : v === 'P1' ? 'orange' : 'green' }
function getFileName(p) { if (!p) return ''; const parts = p.replace(/\\/g,'/').split('/'); return parts[parts.length-1] }
async function clearAttachment(row) {
  try { await api.delete(`/requirements/${row.id}/attachment`); ElMessage.success('附件已清除'); await load() }
  catch(e) { ElMessage.error('清除失败') }
}

onMounted(load)

async function load() {
  try {
    const [rRes, dRes] = await Promise.all([
      api.get(`/projects/${props.projectId}/requirements`),
      api.get(`/projects/${props.projectId}/deliverables`).catch(() => ({ data: [] })),
    ])
    reqs.value = rRes.data || []
    deliverables.value = dRes.data || []
  } catch (e) { reqs.value = [] }
}

function openEdit(row) {
  editing.value = row || null
  if (row) {
    Object.assign(form, { ...row, _clearAttachment: false })
  } else {
    Object.assign(form, { title: '', category: 'functional', priority: 'P1', source: '', status: 'draft', description: '', deliverable_id: null, attachment_path: '', _clearAttachment: false })
  }
  showDialog.value = true
}

async function saveReq() {
  if (!form.title) { ElMessage.warning('请输入标题'); return }
  saving.value = true
  try {
    const payload = { ...form }
    if (editing.value) {
      await api.put(`/requirements/${editing.value.id}`, payload)
      if (form._clearAttachment) {
        await api.delete(`/requirements/${editing.value.id}/attachment`)
      }
    } else {
      await api.post(`/projects/${props.projectId}/requirements`, payload)
    }
    ElMessage.success('已保存'); showDialog.value = false; editing.value = null
    await load()
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}

async function delReq(id) {
  await api.delete(`/requirements/${id}`)
  ElMessage.success('已删除'); await load()
}

// ── AI辅助录入 ──
async function parseAI() {
  if (!aiRawText.value.trim()) { ElMessage.warning('请先粘贴文本'); return }
  aiParsing.value = true; aiItems.value = []
  try {
    const res = await api.post(`/projects/${props.projectId}/requirements/ai-parse`, { text: aiRawText.value }, { timeout: 180000 })
    const items = res.data?.items || []
    aiItems.value = items.map(x => ({ ...x, _selected: true }))
    if (!items.length) ElMessage.info('AI未识别到需求条目，请检查文本内容')
    else ElMessage.success(`AI解析到 ${items.length} 条需求`)
  } catch (e) {
    ElMessage.error('解析失败: ' + (e?.response?.data?.detail || e?.message || 'AI服务不可用'))
  }
  aiParsing.value = false
}

async function importAIItems() {
  const selected = aiItems.value.filter(x => x._selected)
  if (!selected.length) return
  aiImporting.value = true
  let ok = 0
  for (const item of selected) {
    try {
      await api.post(`/projects/${props.projectId}/requirements`, {
        title: item.title, description: item.description || '',
        category: item.category || 'functional', priority: item.priority || 'P1',
        source: item.source || 'AI解析', status: 'draft',
      })
      ok++
    } catch {}
  }
  ElMessage.success(`已导入 ${ok}/${selected.length} 条需求`)
  showAIDialog.value = false; aiRawText.value = ''; aiItems.value = []
  aiImporting.value = false
  await load()
}
</script>
