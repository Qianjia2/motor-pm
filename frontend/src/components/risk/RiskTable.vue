<template>
  <div>
    <div class="card-header mb-md">
      <div>
        <el-radio-group v-model="filterType" size="small" @change="emitFilter">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="risk">风险</el-radio-button>
          <el-radio-button value="issue">问题</el-radio-button>
        </el-radio-group>
        <el-select v-model="filterStatus" placeholder="状态" clearable size="small" style="width:100px;margin-left:8px" @change="emitFilter">
          <el-option label="未关闭" value="open" />
          <el-option label="处理中" value="in_progress" />
          <el-option label="已关闭" value="closed" />
        </el-select>
      </div>
      <el-button type="primary" size="small" @click="openDialog()">
        <el-icon><Plus /></el-icon> 添加
      </el-button>
    </div>

    <el-table :data="items" stripe @row-click="openDialog" row-style="cursor:pointer">
      <el-table-column label="类型" width="70">
        <template #default="{row}">
          <el-tag :type="row.type === 'risk' ? 'warning' : 'danger'" size="small">
            {{ row.type === 'risk' ? '风险' : '问题' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="等级" width="80">
        <template #default="{row}">
          <el-tag v-if="row.risk_level" :type="levelType(row.risk_level)" size="small">
            {{ levelLabel(row.risk_level) }}
          </el-tag>
          <el-tag v-else-if="row.severity" :type="row.severity === 'A' ? 'danger' : row.severity === 'B' ? 'warning' : 'info'" size="small">
            {{ row.severity }}
          </el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="line?.name" label="技术线" width="90" />
      <el-table-column prop="phase?.name" label="阶段" width="90" />
      <el-table-column label="状态" width="90">
        <template #default="{row}">
          <StatusBadge :status="row.status" />
        </template>
      </el-table-column>
      <el-table-column prop="owner?.name" label="负责人" width="80" />
      <el-table-column prop="target_resolve_date" label="目标解决日" width="110" />
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{row}">
          <el-button type="primary" link size="small" @click.stop="openDialog(row)">编辑</el-button>
          <el-button
            v-if="row.status !== 'closed'"
            type="success"
            link
            size="small"
            @click.stop="openCloseDialog(row)"
          >关闭</el-button>
          <span @click.stop>
          <el-popconfirm title="确认删除?" @confirm="handleDelete(row.id)">
            <template #reference>
              <el-button type="danger" link size="small">删除</el-button>
            </template>
          </el-popconfirm>
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingItem ? '编辑' : '添加' + (form.type === 'risk' ? '风险' : '问题')"
      width="600px"
    >
      <el-form :model="form" label-width="100px">
        <el-form-item label="类型">
          <el-radio-group v-model="form.type" :disabled="!!editingItem">
            <el-radio value="risk">风险</el-radio>
            <el-radio value="issue">问题</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="简要描述风险或问题" />
        </el-form-item>
        <el-form-item label="详细描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-row :gutter="12" v-if="form.type === 'risk'">
          <el-col :span="12">
            <el-form-item label="概率">
              <el-select v-model="form.probability" style="width:100%">
                <el-option label="高" value="high" />
                <el-option label="中" value="medium" />
                <el-option label="低" value="low" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="影响">
              <el-select v-model="form.impact" style="width:100%">
                <el-option label="高" value="high" />
                <el-option label="中" value="medium" />
                <el-option label="低" value="low" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item v-if="form.type === 'issue'" label="严重程度">
          <el-select v-model="form.severity" style="width:200px">
            <el-option label="A - 致命" value="A" />
            <el-option label="B - 严重" value="B" />
            <el-option label="C - 一般" value="C" />
            <el-option label="D - 轻微" value="D" />
          </el-select>
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="技术线">
              <el-select v-model="form.line_id" placeholder="选择" clearable style="width:100%">
                <el-option v-for="l in lines" :key="l.id" :label="l.name" :value="l.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属阶段">
              <el-select v-model="form.phase_id" placeholder="选择" clearable style="width:100%">
                <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="负责人">
          <el-select v-model="form.owner_id" placeholder="选择" clearable filterable style="width:100%">
            <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:200px">
            <el-option label="未关闭" value="open" />
            <el-option label="处理中" value="in_progress" />
            <el-option label="已解决" value="resolved" />
            <el-option label="已关闭" value="closed" />
          </el-select>
        </el-form-item>

        <el-form-item label="缓解措施">
          <el-input v-model="form.mitigation_plan" type="textarea" :rows="2" placeholder="应对措施或解决方案" />
        </el-form-item>

        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="识别日期">
              <el-date-picker v-model="form.identified_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="目标解决日">
              <el-date-picker v-model="form.target_resolve_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 关闭验证弹窗 -->
    <el-dialog v-model="closeDialogVisible" title="关闭问题 - 验证结果" width="500px">
      <el-form :model="closeForm" label-width="100px">
        <el-form-item label="问题标题">
          <span style="font-weight:600">{{ closeForm.title }}</span>
        </el-form-item>
        <el-form-item label="验证结果" required>
          <el-input
            v-model="closeForm.resolution"
            type="textarea"
            :rows="4"
            placeholder="请填写设计验证结果、测试数据、整改措施等..."
          />
        </el-form-item>
        <el-form-item label="附件上传">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.jpg,.png,.zip,.step,.stp,.dwg"
            drag
          >
            <el-icon :size="32"><UploadFilled /></el-icon>
            <div style="font-size:12px;color:#909399">拖拽或点击上传验证文件</div>
            <template #tip>
              <div style="font-size:11px;color:#c0c4cc">
                支持 PDF/Word/Excel/图片/压缩包/CAD（可选）
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="closeDialogVisible = false">取消</el-button>
        <el-button type="success" @click="confirmClose" :loading="closing">
          确认关闭
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getLines, getPhases, getTeamMembers } from '../../api/index.js'
import api from '../../api/index.js'
import StatusBadge from '../common/StatusBadge.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'delete', 'filter', 'close', 'refresh'])

const filterType = ref('')
const filterStatus = ref('')
const dialogVisible = ref(false)
const editingItem = ref(null)
const lines = ref([])
const phases = ref([])
const members = ref([])

const form = reactive({
  type: 'risk', title: '', description: '',
  probability: '', impact: '', severity: '',
  line_id: null, phase_id: null, owner_id: null,
  status: 'open', mitigation_plan: '',
  identified_date: null, target_resolve_date: null,
})

async function handleDelete(id) { try { await api.delete(`/risks/${id}`); ElMessage.success('已删除'); emit('refresh') } catch(e) { ElMessage.error('删除失败') } }

onMounted(async () => {
  const [l, p, m] = await Promise.all([getLines(), getPhases(), getTeamMembers()])
  lines.value = l.data
  phases.value = p.data
  members.value = m.data
})

function openDialog(row) {
  editingItem.value = row || null
  if (row) {
    Object.assign(form, {
      type: row.type || 'risk',
      title: row.title || '',
      description: row.description || '',
      probability: row.probability || '',
      impact: row.impact || '',
      severity: row.severity || '',
      line_id: row.line_id || null,
      phase_id: row.phase_id || null,
      owner_id: row.owner_id || null,
      status: row.status || 'open',
      mitigation_plan: row.mitigation_plan || '',
      identified_date: row.identified_date || null,
      target_resolve_date: row.target_resolve_date || null,
    })
  } else {
    Object.assign(form, {
      type: 'risk', title: '', description: '',
      probability: '', impact: '', severity: '',
      line_id: null, phase_id: null, owner_id: null,
      status: 'open', mitigation_plan: '',
      identified_date: null, target_resolve_date: null,
    })
  }
  dialogVisible.value = true
}

function save() {
  if (!form.title) {
    ElMessage.warning('请输入标题')
    return
  }
  emit('save', { ...form, id: editingItem.value?.id })
  dialogVisible.value = false
}

function emitFilter() {
  emit('filter', { type: filterType.value, status: filterStatus.value })
}

function levelType(level) {
  return { critical: 'danger', high: 'warning', medium: '', low: 'info' }[level] || 'info'
}
function levelLabel(level) {
  return { critical: '严重', high: '高', medium: '中', low: '低' }[level] || level
}

// ── Close dialog ────────────────────────────

const closeDialogVisible = ref(false)
const closing = ref(false)
const closeForm = reactive({ id: null, title: '', resolution: '' })
const closeFile = ref(null)

function openCloseDialog(row) {
  closeForm.id = row.id
  closeForm.title = row.title
  closeForm.resolution = ''
  closeFile.value = null
  closeDialogVisible.value = true
}

function onFileChange(file) {
  closeFile.value = file.raw
}
function onFileRemove() {
  closeFile.value = null
}

async function confirmClose() {
  if (!closeForm.resolution.trim()) {
    ElMessage.warning('请填写验证结果')
    return
  }
  closing.value = true
  try {
    const fd = new FormData()
    fd.append('resolution', closeForm.resolution)
    if (closeFile.value) {
      fd.append('file', closeFile.value)
    }
    await api.post(`/risks/${closeForm.id}/close`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    ElMessage.success('问题已关闭')
    closeDialogVisible.value = false
    emit('close')
  } catch (e) {
    ElMessage.error('关闭失败: ' + (e.response?.data?.error || e.message))
  } finally {
    closing.value = false
  }
}
</script>
