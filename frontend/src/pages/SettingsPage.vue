<template>
  <div class="settings-page">
    <el-row :gutter="16">
      <el-col :span="12">
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">
            <div class="card-title">项目阶段</div>
            <el-button size="small" type="primary" v-if="isAdmin" @click="openEdit('phase')">+ 添加</el-button>
          </div>
          <el-table :data="phases" stripe size="small">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="code" label="代码" width="80" />
            <el-table-column prop="sort_order" label="排序" width="60" />
            <el-table-column v-if="isAdmin" label="操作" width="100">
              <template #default="{row}">
                <el-button link size="small" type="primary" @click="openEdit('phase',row)">编辑</el-button>
                <el-popconfirm title="删除?" @confirm="delItem('phases',row.id)">
                  <template #reference><el-button link size="small" type="danger">删</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">
            <div class="card-title">门径评审</div>
            <el-button size="small" type="primary" v-if="isAdmin" @click="openEdit('gate')">+ 添加</el-button>
          </div>
          <el-table :data="gates" stripe size="small">
            <el-table-column prop="code" label="代码" width="70" />
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="sort_order" label="排序" width="60" />
            <el-table-column v-if="isAdmin" label="操作" width="100">
              <template #default="{row}">
                <el-button link size="small" type="primary" @click="openEdit('gate',row)">编辑</el-button>
                <el-popconfirm title="删除?" @confirm="delItem('gates',row.id)">
                  <template #reference><el-button link size="small" type="danger">删</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="12">
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">
            <div class="card-title">技术线</div>
            <el-button size="small" type="primary" v-if="isAdmin" @click="openEdit('line')">+ 添加</el-button>
          </div>
          <el-table :data="lines" stripe size="small">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="short_name" label="简称" width="80" />
            <el-table-column prop="sort_order" label="排序" width="60" />
            <el-table-column v-if="isAdmin" label="操作" width="100">
              <template #default="{row}">
                <el-button link size="small" type="primary" @click="openEdit('line',row)">编辑</el-button>
                <el-popconfirm title="删除?" @confirm="delItem('technical-lines',row.id)">
                  <template #reference><el-button link size="small" type="danger">删</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card" style="margin-bottom:16px">
          <div class="card-header">
            <div class="card-title">角色</div>
            <el-button size="small" type="primary" v-if="isAdmin" @click="openEdit('role')">+ 添加</el-button>
          </div>
          <el-table :data="roles" stripe size="small">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="code" label="代码" width="80" />
            <el-table-column prop="sort_order" label="排序" width="60" />
            <el-table-column v-if="isAdmin" label="操作" width="100">
              <template #default="{row}">
                <el-button link size="small" type="primary" @click="openEdit('role',row)">编辑</el-button>
                <el-popconfirm title="删除?" @confirm="delItem('roles',row.id)">
                  <template #reference><el-button link size="small" type="danger">删</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="showEditDialog" :title="editTitle" width="450px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item v-for="f in editFields" :key="f.key" :label="f.label">
          <el-input v-if="f.type==='text'" v-model="editForm[f.key]" />
          <el-input-number v-else-if="f.type==='int'" v-model="editForm[f.key]" :min="0" :max="999" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog=false">取消</el-button>
        <el-button type="primary" @click="saveEdit" :loading="saving">保存</el-button>
      </template>
    </el-dialog>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <div class="card-title">钉钉集成（审批）</div>
        <div style="display:flex;gap:8px">
          <el-button v-if="isAdmin" size="small" type="primary" @click="fetchDtTemplates" :loading="dtLoading">从钉钉拉取模板</el-button>
        </div>
      </div>
      <div v-if="dtConfig">
        <el-descriptions :column="2" border size="small" style="margin-bottom:12px">
          <el-descriptions-item label="CorpId">{{ dtConfig.corp_id || '未配置' }}</el-descriptions-item>
          <el-descriptions-item label="AppKey">{{ dtConfig.app_key || '未配置' }}</el-descriptions-item>
          <el-descriptions-item label="凭证状态">
            <el-tag :type="dtConfig.has_secret ? 'success' : 'danger'" size="small">{{ dtConfig.has_secret ? '已配置' : '未配置' }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <template v-if="isAdmin">
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">AppKey / AppSecret / CorpId 需在钉钉开放平台「企业内部应用」中获取，权限由钉钉企业管理员授权</div>
          <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
            <el-input v-model="dtCreds.app_key" placeholder="AppKey" style="width:200px" />
            <el-input v-model="dtCreds.app_secret" placeholder="AppSecret" style="width:200px" />
            <el-input v-model="dtCreds.corp_id" placeholder="CorpId" style="width:200px" />
            <el-button type="primary" @click="saveDtCreds" :loading="dtSaving">保存凭证</el-button>
          </div>
          <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
            已关联模板 = 项目详情→「钉钉审批」发起审批可选的流程，也决定拉取审批单的模板下拉和「全部模板」搜索范围；无关流程（离职、请假等）不要勾选即可不显示
          </div>
        </template>

        <el-table v-if="dtTemplates.length" :data="dtTemplates" stripe size="small">
          <el-table-column prop="name" label="模板名称" />
          <el-table-column prop="process_code" label="process_code" />
          <el-table-column v-if="isAdmin" label="操作" width="80">
            <template #default="{row}">
              <el-button link size="small" type="danger" @click="removeDtTemplate(row)">移除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else style="padding:12px;text-align:center;color:var(--text-muted);font-size:13px">暂无关联模板</div>
      </div>
    </div>

    <!-- 钉钉模板选择弹窗 -->
    <el-dialog v-model="showDtPicker" title="选择钉钉审批模板" width="600px">
      <div v-if="dtAvailable.length" style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <el-input v-model="dtTplFilter" size="small" placeholder="搜索模板名称" style="width:200px" clearable />
        <el-checkbox :model-value="allDtPicked" size="small" @change="toggleAllDt">全选</el-checkbox>
        <span style="font-size:12px;color:var(--text-muted)">已勾选 {{ dtPicked.length }} / {{ dtFiltered.length }} 个</span>
      </div>
      <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
        勾选需要关联到平台的审批模板：项目详情→「钉钉审批」→发起审批可选流程、拉取审批单的模板下拉与「全部模板」搜索范围均只包含勾选的模板；无关流程（如离职、请假）不要勾选即可不显示
      </div>
      <div style="max-height:380px;overflow:auto">
        <el-checkbox-group v-model="dtPicked">
          <div v-for="t in dtFiltered" :key="t.process_code" style="padding:6px 0;border-bottom:1px solid #f0f2f5">
            <el-checkbox :label="t.process_code">
              <span>{{ t.name }}</span>
              <span style="color:#c0c4cc;font-size:11px;margin-left:6px">{{ t.process_code }}</span>
            </el-checkbox>
          </div>
          <div v-if="!dtFiltered.length" style="padding:12px;text-align:center;color:var(--text-muted);font-size:13px">无匹配模板</div>
        </el-checkbox-group>
      </div>
      <div v-if="dtErr" style="color:#f56c6c;font-size:12px;margin-top:8px">{{ dtErr }}</div>
      <template #footer>
        <el-button @click="showDtPicker=false">取消</el-button>
        <el-button type="primary" :disabled="!dtAvailable.length" @click="saveDtTemplates">保存</el-button>
      </template>
    </el-dialog>

    <div class="card">
      <div class="card-header"><div class="card-title">系统信息</div></div>
      <el-descriptions :column="2" border size="small">
        <el-descriptions-item label="后端">FastAPI + SQLAlchemy 2.0</el-descriptions-item>
        <el-descriptions-item label="前端">Vue 3 + Element Plus + Vite</el-descriptions-item>
        <el-descriptions-item label="数据库">SQLite</el-descriptions-item>
        <el-descriptions-item label="访问">{{ accessUrl }}</el-descriptions-item>
      </el-descriptions>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getPhases, getGates, getLines, getRoles, getClients } from '../api/index.js'
import api from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const isAdmin = computed(() => auth.isAdmin)

const phases = ref([])
const gates = ref([])
const lines = ref([])
const roles = ref([])
const clients = ref([])

const showEditDialog = ref(false)
const saving = ref(false)
const editType = ref('')
const editFields = ref([])
const editForm = reactive({})
const editTitle = computed(() => {
  const map = { phase: '阶段', gate: '门径', line: '技术线', role: '角色' }
  return (editForm.id ? '编辑' : '添加') + (map[editType.value] || '')
})

const fieldDefs = {
  phase: [{ key: 'name', label: '名称', type: 'text' }, { key: 'code', label: '代码', type: 'text' }, { key: 'sort_order', label: '排序', type: 'int' }],
  gate: [{ key: 'code', label: '代码', type: 'text' }, { key: 'name', label: '名称', type: 'text' }, { key: 'sort_order', label: '排序', type: 'int' }],
  line: [{ key: 'name', label: '名称', type: 'text' }, { key: 'short_name', label: '简称', type: 'text' }, { key: 'sort_order', label: '排序', type: 'int' }],
  role: [{ key: 'name', label: '名称', type: 'text' }, { key: 'code', label: '代码', type: 'text' }, { key: 'sort_order', label: '排序', type: 'int' }],
}
const apiPaths = { phase: 'phases', gate: 'gates', line: 'technical-lines', role: 'roles' }

function openEdit(type, row) {
  editType.value = type
  editFields.value = fieldDefs[type] || []
  Object.keys(editForm).forEach(k => delete editForm[k])
  if (row) Object.assign(editForm, { id: row.id, name: row.name || '', code: row.code || '', short_name: row.short_name || '', sort_order: row.sort_order || 0 })
  else editForm.sort_order = 0
  showEditDialog.value = true
}

async function saveEdit() {
  saving.value = true
  try {
    const base = apiPaths[editType.value]
    const payload = { ...editForm }
    delete payload.id
    if (editForm.id) {
      await api.put(`/lookups/${base}/${editForm.id}`, payload)
    } else {
      await api.post(`/lookups/${base}`, payload)
    }
    ElMessage.success('已保存')
    showEditDialog.value = false
    loadAll()
  } catch (e) { ElMessage.error('保存失败') } finally { saving.value = false }
}

async function delItem(base, id) {
  try {
    await api.delete(`/lookups/${base}/${id}`)
    ElMessage.success('已删除')
    loadAll()
  } catch (e) { ElMessage.error('删除失败') }
}

async function loadAll() {
  const [p, g, l, r, c] = await Promise.all([getPhases(), getGates(), getLines(), getRoles(), getClients()])
  phases.value = p.data; gates.value = g.data; lines.value = l.data; roles.value = r.data; clients.value = c.data || []
}

// ── 钉钉集成 ──
const dtConfig = ref(null)
const dtTemplates = ref([])
const accessUrl = ref('http://127.0.0.1:5002')
const dtCreds = reactive({ app_key: '', app_secret: '', corp_id: '' })
const dtLoading = ref(false)
const dtSaving = ref(false)
const showDtPicker = ref(false)
const dtAvailable = ref([])
const dtPicked = ref([])
const dtErr = ref('')
const dtTplFilter = ref('')
const dtFiltered = computed(() => {
  const f = (dtTplFilter.value || '').trim()
  if (!f) return dtAvailable.value
  return dtAvailable.value.filter(t => (t.name || '').includes(f) || (t.process_code || '').toLowerCase().includes(f.toLowerCase()))
})
const allDtPicked = computed(() => dtFiltered.value.length > 0 && dtFiltered.value.every(t => dtPicked.value.includes(t.process_code)))
function toggleAllDt(v) {
  if (v) dtPicked.value = [...new Set([...dtPicked.value, ...dtFiltered.value.map(t => t.process_code)])]
  else {
    const keep = new Set(dtFiltered.value.map(t => t.process_code))
    dtPicked.value = dtPicked.value.filter(c => !keep.has(c))
  }
}

async function loadDt() {
  try {
    const [cR, tR] = await Promise.all([api.get('/dingtalk/config'), api.get('/dingtalk/templates')])
    dtConfig.value = cR.data
    dtTemplates.value = tR.data || []
    if (cR.data) Object.assign(dtCreds, { app_key: cR.data.app_key || '', app_secret: '', corp_id: cR.data.corp_id || '' })
  } catch(e) {}
}
async function saveDtCreds() {
  if (!dtCreds.app_key || !dtCreds.app_secret) { ElMessage.warning('请填写 AppKey 和 AppSecret'); return }
  dtSaving.value = true
  try {
    await api.put('/dingtalk/credentials', { ...dtCreds })
    ElMessage.success('凭证已保存')
    await loadDt()
  } catch(e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) }
  dtSaving.value = false
}
async function fetchDtTemplates() {
  dtLoading.value = true; dtErr.value = ''
  try {
    const r = await api.get('/dingtalk/templates/available')
    dtAvailable.value = r.data || []
    dtTplFilter.value = ''
    dtPicked.value = dtTemplates.value.map(t => t.process_code)
    if (!dtAvailable.value.length) dtErr.value = '钉钉应用下暂无可见的审批模板，请确认应用已授权「OA审批」权限'
  } catch(e) {
    dtErr.value = e.response?.data?.detail || '拉取失败'
  }
  showDtPicker.value = true
  dtLoading.value = false
}
async function saveDtTemplates() {
  const picked = dtAvailable.value.filter(t => dtPicked.value.includes(t.process_code))
  try {
    await api.put('/dingtalk/templates', { templates: picked })
    ElMessage.success('模板已保存')
    showDtPicker.value = false
    await loadDt()
  } catch(e) { ElMessage.error('保存失败') }
}
async function removeDtTemplate(row) {
  const rest = dtTemplates.value.filter(t => t.process_code !== row.process_code)
  try {
    await api.put('/dingtalk/templates', { templates: rest })
    dtTemplates.value = rest
    ElMessage.success('已移除')
  } catch(e) { ElMessage.error('移除失败') }
}

onMounted(async () => {
  await loadAll(); await loadDt()
  try {
    const r = await api.get('/server-info')
    const ip = r.data?.lan_ip
    if (ip && ip !== '127.0.0.1') accessUrl.value = `http://${ip}:5002`
  } catch (e) {}
})
</script>

<style scoped>
.settings-page { max-width: 1400px; }
</style>
