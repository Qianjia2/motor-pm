<template>
  <div>
    <el-button size="small" @click="openDialog">钉钉审批</el-button>

    <el-dialog v-model="showDlg" :title="'钉钉审批 — ' + projectName" width="650px" top="3vh">
      <el-tabs v-model="activeTab">
        <!-- Tab 1: Create approval -->
        <el-tab-pane label="发起审批" name="create">
          <el-form :model="form" label-width="80px" size="small" v-if="templates.length">
            <el-form-item label="审批类型">
              <el-select v-model="form.tplIdx" style="width:100%">
                <el-option v-for="(t,i) in templates" :key="i" :label="t.name" :value="i" />
              </el-select>
            </el-form-item>
            <el-form-item label="手机号">
              <el-input v-model="form.mobile" placeholder="钉钉绑定的手机号" />
            </el-form-item>
            <el-form-item label="标题">
              <el-input v-model="form.title" />
            </el-form-item>
            <el-form-item label="内容">
              <el-input v-model="form.content" type="textarea" :rows="4" />
            </el-form-item>
          </el-form>
          <div v-else style="padding:24px;text-align:center;color:var(--text-muted)">
            暂无审批模板。请在系统设置→钉钉集成中添加模板。
          </div>
          <div v-if="templates.length" style="font-size:12px;color:var(--text-muted);margin-top:8px">
            在钉钉中发起审批，审批状态可在下方「审批记录」中查看。
          </div>
        </el-tab-pane>

        <!-- Tab 2: Approval records -->
        <el-tab-pane label="审批记录" name="records">
          <div style="margin-bottom:12px;display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap">
            <el-select v-model="newType" size="small" style="width:110px">
              <el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" />
            </el-select>
            <el-input v-model="newTitle" size="small" placeholder="审批标题" style="flex:1;min-width:140px" />
            <el-button size="small" type="primary" @click="addRecord">添加记录</el-button>
            <el-button size="small" @click="openPicker" :disabled="!templates.length">从钉钉拉取审批单</el-button>
          </div>
          <el-table :data="items" stripe size="small" max-height="300">
            <el-table-column label="类型" width="90">
              <template #default="{row}"><el-tag size="small" :type="row.type==='contract'?'warning':'info'">{{ typeLabel(row.type) }}</el-tag></template>
            </el-table-column>
            <el-table-column label="标题" min-width="140">
              <template #default="{row}">{{ row.title || row.note || '—' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100">
              <template #default="{row}">
                <el-select v-model="row.status" size="small" @change="updateItem(row)" style="width:80px">
                  <el-option v-for="s in statuses" :key="s.value" :label="s.label" :value="s.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="发起人" width="80">
              <template #default="{row}">{{ row.created_by||'—' }}</template>
            </el-table-column>
            <el-table-column label="时间" width="100">
              <template #default="{row}">{{ row.created_at?.slice(0,10) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="160">
              <template #default="{$index,row}">
                <el-button v-if="row.instance_id" link size="small" @click="showDetail(row)">详情</el-button>
                <el-button v-if="row.instance_id" link size="small" @click="refreshStatus(row)">刷新</el-button>
                <el-popconfirm title="删除?" @confirm="removeItem($index,row.id)">
                  <template #reference><el-button link size="small" type="danger">删</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="items.length===0" style="padding:24px;text-align:center;color:var(--text-muted);font-size:13px">
            暂无审批记录
          </div>
        </el-tab-pane>
      </el-tabs>

      <template #footer>
        <el-button @click="showDlg=false">关闭</el-button>
        <el-button v-if="activeTab==='create' && templates.length" type="primary" @click="doCreate" :loading="creating">发起审批</el-button>
      </template>
    </el-dialog>

    <!-- 从钉钉拉取审批单并关联到本项目 -->
    <el-dialog v-model="showPicker" title="从钉钉拉取审批单" width="720px" top="5vh">
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px;flex-wrap:wrap">
        <el-select v-model="pickerTpl" size="small" style="width:200px" @change="loadInstances">
          <el-option label="全部模板" value="" />
          <el-option v-for="t in templates" :key="t.process_code" :label="t.name" :value="t.process_code" />
        </el-select>
        <el-select v-model="pickerDays" size="small" style="width:100px" @change="loadInstances">
          <el-option label="最近 7 天" :value="7" />
          <el-option label="最近 30 天" :value="30" />
          <el-option label="最近 60 天" :value="60" />
          <el-option label="最近 90 天" :value="90" />
          <el-option label="最近 180 天" :value="180" />
          <el-option label="最近 360 天" :value="360" />
        </el-select>
        <el-input v-model="pickerKeyword" size="small" placeholder="关键词（标题/内容）" style="width:150px" clearable @keyup.enter="loadInstances" />
        <el-input v-model="pickerMobile" size="small" placeholder="发起人手机号（可选）" style="width:150px" clearable />
        <el-button size="small" @click="loadInstances" :loading="pickerLoading">查询</el-button>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
        <template v-if="!pickerTpl">当前为「全部模板」搜索：需扫描企业下所有审批模板，耗时较长，建议配合关键词使用；时间范围越大调用量越多（360 天约为 30 天的 10 倍），建议先用小范围，查不到再放大；</template>
        <template v-else>已选择单个流程模板；</template>
        钉钉平台仅保留约 1 年内的审批数据，超过 360 天的单子查不到
      </div>
      <div v-if="instances.length" style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
        勾选需要关联到本项目的审批单，关联后可在「审批记录」中刷新状态
      </div>
      <el-table :data="instances" stripe size="small" max-height="380" @selection-change="sel=>pickedInstances=sel">
        <el-table-column type="selection" width="40" />
        <el-table-column label="流程模板" min-width="130">
          <template #default="{row}">{{ row.process_name || '—' }}</template>
        </el-table-column>
        <el-table-column label="审批标题" min-width="150">
          <template #default="{row}">{{ row.title || '—' }}</template>
        </el-table-column>
        <el-table-column label="关键内容" min-width="180">
          <template #default="{row}">
            <div v-if="row.key_fields && row.key_fields.length" class="key-fields-cell">
              <div v-for="kf in row.key_fields" :key="kf">{{ kf }}</div>
            </div>
            <span v-else style="color:var(--text-muted)">—</span>
          </template>
        </el-table-column>
        <el-table-column label="发起人" width="90">
          <template #default="{row}">{{ row.originator || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{row}">
            <el-tag size="small" :type="instStatusType(row.status)">{{ instStatusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发起时间" width="125">
          <template #default="{row}">{{ row.created_at }}</template>
        </el-table-column>
      </el-table>
      <div v-if="!instances.length && !pickerLoading" style="padding:16px;text-align:center;color:var(--text-muted);font-size:13px">
        {{ pickerSearched ? (pickerTpl ? '该模板近期没有已发起的审批单' : '没有找到匹配的审批单，试试缩小时间范围或换关键词') : '设置条件后点击「查询」开始拉取' }}
      </div>
      <div v-if="pickerErr" style="color:#f56c6c;font-size:12px;margin-top:8px">{{ pickerErr }}</div>
      <template #footer>
        <el-button @click="showPicker=false">取消</el-button>
        <el-button type="primary" :disabled="!pickedInstances.length" @click="linkInstances" :loading="linking">关联到本项目</el-button>
      </template>
    </el-dialog>

    <!-- 审批单详情: 表单 + 审批过程 + 钉钉打开 -->
    <el-dialog v-model="showDetailDlg" title="审批单详情" width="640px" top="4vh">
      <div v-if="detail" style="min-height:200px">
        <el-descriptions :column="2" border size="small" style="margin-bottom:12px">
          <el-descriptions-item label="标题" :span="2">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag size="small" :type="instStatusType(detail.status)">{{ instStatusLabel(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="发起人">{{ detail.originator }}</el-descriptions-item>
          <el-descriptions-item label="发起时间">{{ detail.create_time }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ detail.finish_time || '—' }}</el-descriptions-item>
        </el-descriptions>

        <div style="font-weight:600;margin-bottom:8px">表单内容</div>
        <el-table :data="detail.form_values" stripe size="small" max-height="180">
          <el-table-column prop="name" label="字段" min-width="120" />
          <el-table-column prop="value" label="内容" min-width="200" show-overflow-tooltip />
        </el-table>
        <div v-if="!detail.form_values.length" style="padding:8px;color:var(--text-muted);font-size:12px">无表单内容</div>

        <div style="font-weight:600;margin:12px 0 8px">审批过程</div>
        <el-timeline v-if="timeline.length" style="padding-left:4px">
          <el-timeline-item v-for="(op,i) in timeline" :key="i" :timestamp="op.time"
            :type="op.type==='审批驳回' ? 'danger' : 'primary'">
            <div>{{ op.label }}</div>
            <div v-if="op.remark" style="color:var(--text-muted);font-size:12px">备注：{{ op.remark }}</div>
          </el-timeline-item>
        </el-timeline>
        <div v-else style="padding:8px;color:var(--text-muted);font-size:12px">暂无审批过程记录</div>
        <div style="font-size:11px;color:#c0c4cc;margin-top:6px">审批人姓名需钉钉管理员给应用开通「通讯录用户详情」权限后显示</div>
      </div>
      <template #footer>
        <a v-if="detail?.links?.pc_client" :href="detail.links.pc_client">
          <el-button size="small" type="primary">电脑端打开</el-button>
        </a>
        <a v-if="detail?.links?.mobile" :href="detail.links.mobile" target="_blank" rel="noopener">
          <el-button size="small">钉钉手机端打开</el-button>
        </a>
        <el-button size="small" @click="showDetailDlg=false">关闭</el-button>
      </template>
      <div v-if="detail?.links?.pc_client" style="font-size:11px;color:#c0c4cc;padding:0 4px 4px">
        电脑端打开会在钉钉客户端侧边栏中打开该审批单（需已安装钉钉客户端）；钉钉手机端打开需在手机端使用
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../../api/index.js'

const props = defineProps({
  projectName: { type: String, default: '' },
  projectId: { type: [Number, String], default: '' },
})

const types = [
  { value: 'contract', label: '合同审批' },
  { value: 'requirement', label: '需求评审' },
  { value: 'tech_review', label: '技术评审' },
  { value: 'purchase', label: '采购申请' },
  { value: 'change', label: '变更申请' },
  { value: 'other', label: '其他' },
]
const statuses = [
  { value: 'pending', label: '审批中' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
]
function typeLabel(v) { return types.find(t => t.value === v)?.label || v }

const showDlg = ref(false)
const activeTab = ref('records')
const templates = ref([])
const items = ref([])
const creating = ref(false)
// Create form
const form = reactive({ tplIdx: 0, mobile: '', title: '', content: '' })
// Record form
const newType = ref('contract')
const newTitle = ref('')

async function loadData() {
  try {
    const [tR, iR] = await Promise.all([
      api.get('/dingtalk/templates'),
      api.get(`/projects/${props.projectId}/dingtalk-approvals`),
    ])
    templates.value = tR.data || []
    items.value = iR.data || []
  } catch(e) {}
}

function openDialog() {
  loadData()
  form.tplIdx = 0
  form.title = `【${props.projectName || '项目'}】审批`
  form.content = ''
  form.mobile = ''
  showDlg.value = true
  activeTab.value = 'records'
}

// ── 从钉钉拉取已发起的审批单 ──
const showPicker = ref(false)
const pickerTpl = ref('')
const pickerDays = ref(30)
const pickerMobile = ref('')
const pickerKeyword = ref('')
const pickerSearched = ref(false)
const instances = ref([])
const pickedInstances = ref([])
const pickerLoading = ref(false)
const pickerErr = ref('')
const linking = ref(false)

function instStatusLabel(s) {
  return { 'NEW': '审批中', 'RUNNING': '审批中', 'COMPLETED': '已通过', 'TERMINATED': '已驳回', 'CANCELED': '已撤销' }[s] || '审批中'
}
function instStatusType(s) {
  return { 'COMPLETED': 'success', 'TERMINATED': 'danger', 'CANCELED': 'info' }[s] || 'warning'
}

function openPicker() {
  if (!templates.value.length) { ElMessage.warning('请先在系统设置中添加钉钉模板'); return }
  showPicker.value = true
  pickerErr.value = ''
  pickedInstances.value = []
  instances.value = []
  pickerSearched.value = false
  pickerTpl.value = ''
  pickerMobile.value = ''
  pickerKeyword.value = ''
}

async function loadInstances() {
  pickerLoading.value = true
  pickerErr.value = ''
  try {
    const r = await api.get('/dingtalk/instances', { params: { process_code: pickerTpl.value, days: pickerDays.value, mobile: pickerMobile.value, keyword: pickerKeyword.value }, timeout: 300000 })
    instances.value = r.data || []
    pickedInstances.value = []
    pickerSearched.value = true
  } catch(e) {
    pickerErr.value = e.response?.data?.detail || '拉取失败'
  }
  pickerLoading.value = false
}

// ── 审批单详情(表单 + 审批过程 + 钉钉打开链接) ──
const showDetailDlg = ref(false)
const detail = ref(null)
const detailLoading = ref(false)

const timeline = computed(() => {
  if (!detail.value) return []
  const map = {
    'START_PROCESS_INSTANCE': '发起审批',
    'EXECUTE_TASK_NORMAL': op => op.result === 'AGREE' ? '审批通过' : op.result === 'REFUSE' ? '审批驳回' : '审批',
    'REDIRECT': '转交审批',
  }
  return (detail.value.operation_records || [])
    .filter(op => op.type !== 'PROCESS_CC')
    .map(op => {
      const m = map[op.type]
      return {
        time: op.time,
        label: (typeof m === 'function' ? m(op) : m || op.type) + (op.userid ? ` · ${op.userid}` : ''),
        remark: op.remark,
        type: op.type,
      }
    })
})

async function showDetail(row) {
  if (!row.instance_id) return
  detail.value = null
  showDetailDlg.value = true
  detailLoading.value = true
  try {
    const r = await api.get(`/dingtalk/instances/${row.instance_id}`)
    detail.value = r.data
  } catch(e) {
    ElMessage.error(e.response?.data?.detail || '查询失败')
    showDetailDlg.value = false
  }
  detailLoading.value = false
}

async function linkInstances() {
  const picked = pickedInstances.value
  if (!picked.length) return
  linking.value = true
  try {
    for (const inst of picked) {
      await api.post(`/projects/${props.projectId}/dingtalk-approvals`, {
        type: 'other',
        title: inst.title || '钉钉审批',
        instance_id: inst.instance_id,
        status: inst.status === 'COMPLETED' ? 'approved' : inst.status === 'TERMINATED' ? 'rejected' : 'pending',
        note: inst.originator ? `发起人: ${inst.originator}` : '',
      })
    }
    ElMessage.success(`已关联 ${picked.length} 条审批单`)
    showPicker.value = false
    await loadData()
  } catch(e) { ElMessage.error('关联失败') }
  linking.value = false
}

// Create approval
async function doCreate() {
  if (!form.mobile) { ElMessage.warning('请输入钉钉手机号'); return }
  if (!form.title) { ElMessage.warning('请输入标题'); return }
  creating.value = true
  try {
    // First look up DingTalk user ID
    const uR = await api.get('/dingtalk/users/search', { params: { mobile: form.mobile } })
    const user = uR.data?.result || uR.data || {}
    const userId = user.userId || user.userid || ''
    if (!userId) { ElMessage.error('未找到该手机号对应的钉钉用户'); creating.value = false; return }

    // Create approval
    const tpl = templates.value[form.tplIdx]
    const rsp = await api.post('/dingtalk/approvals', {
      process_code: tpl.process_code,
      user_id: userId,
      title: form.title,
      form_values: [
        { name: '标题', value: form.title },
        { name: '内容', value: form.content },
        { name: '项目', value: props.projectName },
      ],
    })

    if (rsp.data?.ok && rsp.data.instance_id) {
      ElMessage.success('审批已发起')
      // Auto-add to records
      await api.post(`/projects/${props.projectId}/dingtalk-approvals`, {
        type: 'other', title: `${tpl.name} — ${form.title}`,
        instance_id: rsp.data.instance_id, status: 'pending',
      })
      form.title = ''; form.content = ''; form.mobile = ''
      activeTab.value = 'records'
      await loadData()
    } else {
      const raw = rsp.data?.raw || rsp.data || {}
      ElMessage.error('发起失败: ' + (raw.message || JSON.stringify(raw)))
    }
  } catch(e) { ElMessage.error('发起失败: ' + (e.response?.data?.detail || e.message)) }
  creating.value = false
}

// Manual records
async function addRecord() {
  const title = newTitle.value.trim()
  if (!title) { ElMessage.warning('请输入标题'); return }
  try {
    await api.post(`/projects/${props.projectId}/dingtalk-approvals`, { type: newType.value, title, status: 'pending' })
    ElMessage.success('已添加'); newTitle.value = ''; await loadData()
  } catch(e) { ElMessage.error('添加失败') }
}
async function updateItem(row) {
  try { await api.put(`/projects/${props.projectId}/dingtalk-approvals/${row.id}`, { status: row.status, type: row.type, title: row.title }) } catch(e) {}
}
async function removeItem(idx, id) {
  try { await api.delete(`/projects/${props.projectId}/dingtalk-approvals/${id}`); items.value.splice(idx,1); ElMessage.success('已删除') } catch(e) {}
}
async function refreshStatus(row) {
  if (!row.instance_id) return
  try {
    const r = await api.get(`/dingtalk/approvals/${row.instance_id}`)
    const inst = r.data?.result || r.data || {}
    const statusMap = { 'COMPLETED': 'approved', 'TERMINATED': 'rejected', 'RUNNING': 'pending', 'NEW': 'pending' }
    const newStatus = statusMap[inst.status] || row.status
    if (newStatus !== row.status) {
      row.status = newStatus
      await updateItem(row)
      ElMessage.success(`状态已更新: ${newStatus === 'approved' ? '已通过' : newStatus === 'rejected' ? '已驳回' : '审批中'}`)
    } else {
      ElMessage.info('状态未变化')
    }
  } catch(e) { ElMessage.error('刷新失败') }
}

defineExpose({ openDialog })
showDlg.value = false
</script>

<style scoped>
.key-fields-cell {
  line-height: 1.5;
  font-size: 12px;
  color: var(--text-color);
}
.key-fields-cell div {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
