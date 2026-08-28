<template>
  <div>
    <el-tabs v-model="subTab" type="card" size="small">
      <el-tab-pane label="测试计划" name="plans">
        <div class="card-header mb-md">
          <el-select v-model="filterType" placeholder="类型筛选" clearable size="small" style="width:130px">
            <el-option v-for="t in testTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
          <el-button size="small" type="primary" @click="openPlan()"><el-icon><Plus /></el-icon> 添加计划</el-button>
        </div>
        <div v-if="plans.length===0" style="text-align:center;padding:40px;color:var(--text-muted)">暂无测试计划</div>
        <div v-for="tp in filteredPlans" :key="tp.id" class="test-plan-card">
          <div class="tp-header" @click="selectPlan(tp)">
            <span class="tag" :class="'tag-'+typeCls(tp.test_type)">{{ typeLabel(tp.test_type) }}</span>
            <span class="tp-name">{{ tp.name }}</span>
            <span class="tag" :class="planStatusCls(tp.status)">{{ planStatusLabel(tp.status) }}</span>
          </div>
          <div class="tp-dates" @click="selectPlan(tp)">{{ tp.planned_start || '?' }} → {{ tp.planned_end || '?' }}</div>
          <div v-if="tp.description" class="tp-desc" @click="selectPlan(tp)">{{ tp.description.slice(0, 80) }}</div>
          <div class="tp-actions">
            <el-upload :action="`/api/test-plans/${tp.id}/upload`" :headers="uploadHeaders"
              :show-file-list="false" :on-success="onPlanFileUploaded" style="display:inline-block">
              <el-button link size="small" type="primary">📎 上传文件</el-button>
            </el-upload>
            <a v-if="tp.attachment_path" :href="'/api/uploads/'+tp.attachment_path" target="_blank"
              style="font-size:11px;color:#10b981;margin-left:8px">已上传: {{ tp.attachment_path.split('/').pop() }}</a>
            <el-button link size="small" @click.stop="openPlan(tp)" style="margin-left:auto">编辑</el-button>
            <el-popconfirm title="删除?" @confirm="delPlan(tp.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="测试结果" name="results" v-if="selectedPlan">
        <div class="card-header mb-md">
          <span style="font-weight:600;color:var(--text)">{{ selectedPlan.name }}</span>
          <el-button size="small" type="primary" @click="openResult()"><el-icon><Plus /></el-icon> 记录结果</el-button>
        </div>
        <el-table :data="results" stripe size="small">
          <el-table-column prop="name" label="测试项" min-width="180" />
          <el-table-column label="结果" width="80">
            <template #default="{row}">
              <span v-if="row.result==='pass'" class="tag tag-green">通过</span>
              <span v-else-if="row.result==='fail'" class="tag tag-red">失败</span>
              <span v-else-if="row.result==='partial'" class="tag tag-orange">部分</span>
              <span v-else class="tag tag-gray">待测</span>
            </template>
          </el-table-column>
          <el-table-column prop="test_date" label="日期" width="100" />
          <el-table-column prop="notes" label="备注" min-width="150" show-overflow-tooltip />
          <el-table-column label="操作" width="100">
            <template #default="{row}">
              <el-button link size="small" type="primary" @click="openResult(row)">编辑</el-button>
              <el-popconfirm title="删除?" @confirm="delResult(row.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="问题8D" name="issues">
        <div class="card-header mb-md"><span></span><el-button size="small" type="primary" @click="openIssue()"><el-icon><Plus /></el-icon> 记录问题</el-button></div>
        <el-table :data="issues" stripe size="small">
          <el-table-column label="严重" width="55"><template #default="{row}"><span :class="'tag tag-'+sevCls(row.severity)" style="font-size:10px">{{ row.severity }}</span></template></el-table-column>
          <el-table-column prop="title" label="问题标题" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="80"><template #default="{row}">{{ issueStatusLabel(row.status) }}</template></el-table-column>
          <el-table-column label="根因" width="120" show-overflow-tooltip><template #default="{row}">{{ row.d4_root_cause || '-' }}</template></el-table-column>
          <el-table-column label="操作" width="150">
            <template #default="{row}">
              <el-button link size="small" type="primary" @click="openIssue(row)">8D</el-button>
              <el-popconfirm title="删除?" @confirm="delIssue(row.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="测试文件" name="files">
        <div class="card-header mb-md">
          <span style="font-size:12px;color:var(--text-muted)">上传测试报告/数据文件，不限格式</span>
          <el-upload :action="uploadUrl" :headers="uploadHeaders" :show-file-list="false"
            :on-success="onFileUploaded" :before-upload="onFileBefore">
            <el-button size="small" type="primary">📤 上传文件</el-button>
          </el-upload>
        </div>
        <el-table v-if="testFiles.length>0" :data="testFiles" stripe size="small">
          <el-table-column prop="name" label="测试项" min-width="160" show-overflow-tooltip />
          <el-table-column label="结果" width="80">
            <template #default="{row}">
              <span v-if="row.result==='pass'" class="tag tag-green">通过</span>
              <span v-else-if="row.result==='fail'" class="tag tag-red">失败</span>
              <span v-else class="tag tag-gray">待测</span>
            </template>
          </el-table-column>
          <el-table-column prop="test_date" label="日期" width="100" />
          <el-table-column label="文件" min-width="200">
            <template #default="{row}">
              <a :href="'/api/uploads/' + row.attachment_path" target="_blank" style="color:#409eff;font-size:12px">
                {{ row.attachment_path ? row.attachment_path.split('/').pop() : '-' }}
              </a>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70">
            <template #default="{row}">
              <el-popconfirm title="删除附件?" @confirm="clearAttachment(row.id)">
                <template #reference><el-button link size="small" type="danger">清除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
        <div v-else style="text-align:center;padding:40px;color:var(--text-muted)">暂无测试文件，上传后在此查看</div>
      </el-tab-pane>
    </el-tabs>

    <!-- Plan Dialog -->
    <el-dialog v-model="showPlanDlg" :title="editingPlan ? '编辑测试计划' : '添加测试计划'" width="480px">
      <el-form :model="planForm" label-width="80px">
        <el-form-item label="名称" required><el-input v-model="planForm.name" /></el-form-item>
        <el-row :gutter="12"><el-col :span="12"><el-form-item label="类型"><el-select v-model="planForm.test_type" style="width:100%"><el-option v-for="t in testTypes" :key="t.value" :label="t.label" :value="t.value" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item label="状态"><el-select v-model="planForm.status" style="width:100%"><el-option label="计划中" value="planned" /><el-option label="进行中" value="in_progress" /><el-option label="已完成" value="completed" /></el-select></el-form-item></el-col></el-row>
        <el-row :gutter="12"><el-col :span="12"><el-form-item label="开始"><el-date-picker v-model="planForm.planned_start" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col><el-col :span="12"><el-form-item label="结束"><el-date-picker v-model="planForm.planned_end" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col></el-row>
        <el-form-item label="描述"><el-input v-model="planForm.description" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showPlanDlg=false">取消</el-button><el-button type="primary" @click="savePlan" :loading="saving">保存</el-button></template>
    </el-dialog>

    <!-- Result Dialog -->
    <el-dialog v-model="showResultDlg" :title="editingResult ? '编辑结果' : '记录测试结果'" width="480px">
      <el-form :model="resultForm" label-width="80px">
        <el-form-item label="测试项" required><el-input v-model="resultForm.name" /></el-form-item>
        <el-row :gutter="12"><el-col :span="12"><el-form-item label="结果"><el-select v-model="resultForm.result" style="width:100%"><el-option label="通过" value="pass" /><el-option label="失败" value="fail" /><el-option label="部分通过" value="partial" /><el-option label="待测" value="pending" /></el-select></el-form-item></el-col><el-col :span="12"><el-form-item label="日期"><el-date-picker v-model="resultForm.test_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col></el-row>
        <el-form-item label="实测值"><el-input v-model="resultForm.measured_value" /></el-form-item>
        <el-form-item label="规格值"><el-input v-model="resultForm.spec_value" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="resultForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showResultDlg=false">取消</el-button><el-button type="primary" @click="saveResult" :loading="saving">保存</el-button></template>
    </el-dialog>

    <!-- Issue 8D Dialog -->
    <el-dialog v-model="showIssueDlg" :title="editingIssue ? '编辑问题8D' : '记录测试问题'" width="600px" top="20px">
      <el-form :model="issueForm" label-width="100px" size="small">
        <el-form-item label="问题标题" required><el-input v-model="issueForm.title" /></el-form-item>
        <el-row :gutter="12"><el-col :span="8"><el-form-item label="严重度"><el-select v-model="issueForm.severity" style="width:100%"><el-option label="高" value="高" /><el-option label="中" value="中" /><el-option label="低" value="低" /></el-select></el-form-item></el-col><el-col :span="8"><el-form-item label="状态"><el-select v-model="issueForm.status" style="width:100%"><el-option label="待分析" value="open" /><el-option label="分析中" value="analyzing" /><el-option label="已解决" value="resolved" /><el-option label="已关闭" value="closed" /></el-select></el-form-item></el-col><el-col :span="8"><el-form-item label="关联结果"><el-select v-model="issueForm.test_result_id" clearable style="width:100%" placeholder="可选"><el-option v-for="r in allResults" :key="r.id" :label="r.name" :value="r.id" /></el-select></el-form-item></el-col></el-row>
        <el-collapse v-model="dphase">
          <el-collapse-item title="D1 团队" name="d1"><el-input v-model="issueForm.d1_team" type="textarea" :rows="2" placeholder="参与问题解决的人员" /></el-collapse-item>
          <el-collapse-item title="D2 问题描述" name="d2"><el-input v-model="issueForm.d2_problem" type="textarea" :rows="2" placeholder="详细描述问题现象" /></el-collapse-item>
          <el-collapse-item title="D3 临时措施" name="d3"><el-input v-model="issueForm.d3_containment" type="textarea" :rows="2" placeholder="临时遏制措施" /></el-collapse-item>
          <el-collapse-item title="D4 根因分析" name="d4"><el-input v-model="issueForm.d4_root_cause" type="textarea" :rows="2" placeholder="根本原因（5Why/鱼骨图）" /></el-collapse-item>
          <el-collapse-item title="D5 永久纠正措施" name="d5"><el-input v-model="issueForm.d5_corrective" type="textarea" :rows="2" /></el-collapse-item>
          <el-collapse-item title="D6 实施验证" name="d6"><el-input v-model="issueForm.d6_implementation" type="textarea" :rows="2" /></el-collapse-item>
          <el-collapse-item title="D7 预防措施" name="d7"><el-input v-model="issueForm.d7_prevention" type="textarea" :rows="2" /></el-collapse-item>
          <el-collapse-item title="D8 团队认可" name="d8"><el-input v-model="issueForm.d8_recognition" type="textarea" :rows="2" /></el-collapse-item>
        </el-collapse>
      </el-form>
      <template #footer><el-button @click="showIssueDlg=false">取消</el-button><el-button type="primary" @click="saveIssue" :loading="saving">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })

const subTab = ref('plans')
const plans = ref([])
const results = ref([])
const issues = ref([])
const selectedPlan = ref(null)
const filterType = ref('')
const dphase = ref([])

const testTypes = [
  { value: 'DV', label: 'DV设计验证' }, { value: 'PV', label: 'PV生产验证' },
  { value: 'bench', label: '台架测试' }, { value: 'durability', label: '耐久测试' },
  { value: 'environmental', label: '环境试验' }, { value: 'other', label: '其他' },
]
function typeLabel(v) { return testTypes.find(t=>t.value===v)?.label||v }
function typeCls(v) { return v==='DV'||v==='PV'?'blue':v==='bench'?'green':'orange' }
function planStatusLabel(s) { const m={planned:'计划中',in_progress:'进行中',completed:'已完成',cancelled:'已取消'}; return m[s]||s }
function planStatusCls(s) { return s==='completed'?'green':s==='in_progress'?'blue':'gray' }
function issueStatusLabel(s) { const m={open:'待分析',analyzing:'分析中',resolved:'已解决',closed:'已关闭'}; return m[s]||s }
function sevCls(s) { return s==='高'?'red':s==='中'?'orange':'green' }

const filteredPlans = computed(() => filterType.value ? plans.value.filter(p=>p.test_type===filterType.value) : plans.value)

// Test files
const testFiles = ref([])
const uploadUrl = computed(() => `/api/projects/${props.projectId}/test-files/upload-batch`)
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
function onFileBefore(file) { return true }
async function onFileUploaded(res) {
  ElMessage.success(res.message || '上传成功')
  await loadTestFiles()
}
async function clearAttachment(id) {
  await api.put(`/test-results/${id}`, { attachment_path: '' })
  ElMessage.success('已清除')
  await loadTestFiles()
}
async function loadTestFiles() {
  try { const r = await api.get(`/projects/${props.projectId}/test-files`); testFiles.value = r.data||[] } catch(e) { testFiles.value = [] }
}

// ── Dialogs ──
const showPlanDlg = ref(false); const editingPlan = ref(null); const saving = ref(false)
const planForm = reactive({ name:'', test_type:'DV', planned_start:null, planned_end:null, status:'planned', description:'' })
const showResultDlg = ref(false); const editingResult = ref(null)
const resultForm = reactive({ name:'', test_date:null, result:'pending', measured_value:'', spec_value:'', notes:'' })
const showIssueDlg = ref(false); const editingIssue = ref(null)
const issueForm = reactive({ title:'', severity:'中', status:'open', test_result_id:null, d1_team:'', d2_problem:'', d3_containment:'', d4_root_cause:'', d5_corrective:'', d6_implementation:'', d7_prevention:'', d8_recognition:'' })
const allResults = ref([])

onMounted(load)
watch(subTab, (v) => { if (v === 'files') loadTestFiles() })

async function load() {
  try {
    const [pRes, iRes] = await Promise.all([
      api.get(`/projects/${props.projectId}/test-plans`),
      api.get(`/projects/${props.projectId}/test-issues`),
    ])
    plans.value = pRes.data || []; issues.value = iRes.data || []
  } catch (e) { plans.value = []; issues.value = [] }
}

async function selectPlan(tp) {
  selectedPlan.value = tp
  subTab.value = 'results'
  try { const res = await api.get(`/test-plans/${tp.id}/results`); results.value = res.data || [] } catch (e) { results.value = [] }
  // Load all results for issue linking
  try { allResults.value = results.value } catch (e) {}
}

// ── Plan CRUD ──
function openPlan(row) {
  editingPlan.value = row || null
  Object.assign(planForm, row ? {...row} : {name:'',test_type:'DV',planned_start:null,planned_end:null,status:'planned',description:''})
  showPlanDlg.value = true
}
async function savePlan() {
  if (!planForm.name) { ElMessage.warning('请输入名称'); return }
  saving.value = true
  try {
    if (editingPlan.value) { await api.put(`/test-plans/${editingPlan.value.id}`, {...planForm}) }
    else { await api.post(`/projects/${props.projectId}/test-plans`, {...planForm}) }
    ElMessage.success('已保存'); showPlanDlg.value = false; editingPlan.value = null; await load()
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}
async function delPlan(id) { await api.delete(`/test-plans/${id}`); ElMessage.success('已删除'); await load() }
function onPlanFileUploaded(res) { ElMessage.success(res.message || '文件已上传'); load() }

// ── Result CRUD ──
function openResult(row) {
  editingResult.value = row || null
  Object.assign(resultForm, row ? {...row} : {name:'',test_date:null,result:'pending',measured_value:'',spec_value:'',notes:''})
  showResultDlg.value = true
}
async function saveResult() {
  if (!resultForm.name) { ElMessage.warning('请输入名称'); return }
  saving.value = true
  try {
    if (editingResult.value) { await api.put(`/test-results/${editingResult.value.id}`, {...resultForm}) }
    else { await api.post(`/test-plans/${selectedPlan.value.id}/results`, {...resultForm}) }
    ElMessage.success('已保存'); showResultDlg.value = false; editingResult.value = null
    if (selectedPlan.value) await selectPlan(selectedPlan.value)
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}
async function delResult(id) { await api.delete(`/test-results/${id}`); ElMessage.success('已删除'); if (selectedPlan.value) await selectPlan(selectedPlan.value) }

// ── Issue 8D CRUD ──
function openIssue(row) {
  editingIssue.value = row || null
  const def = {title:'',severity:'中',status:'open',test_result_id:null,d1_team:'',d2_problem:'',d3_containment:'',d4_root_cause:'',d5_corrective:'',d6_implementation:'',d7_prevention:'',d8_recognition:''}
  Object.assign(issueForm, row ? {...def, ...row} : def)
  showIssueDlg.value = true; dphase.value = row ? [] : ['d1','d2']
}
async function saveIssue() {
  if (!issueForm.title) { ElMessage.warning('请输入标题'); return }
  saving.value = true
  try {
    if (editingIssue.value) { await api.put(`/test-issues/${editingIssue.value.id}`, {...issueForm}) }
    else { await api.post(`/projects/${props.projectId}/test-issues`, {...issueForm}) }
    ElMessage.success('已保存'); showIssueDlg.value = false; editingIssue.value = null; await load()
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}
async function delIssue(id) { await api.delete(`/test-issues/${id}`); ElMessage.success('已删除'); await load() }
</script>

<style scoped>
.test-plan-card { padding: 12px 16px; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 8px; cursor: pointer; transition: all .15s; }
.test-plan-card:hover { border-color: var(--primary); background: var(--primary-light); }
.tp-header { display: flex; align-items: center; gap: 8px; }
.tp-name { font-weight: 600; color: var(--text); flex: 1; }
.tp-dates { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.tp-desc { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
</style>
