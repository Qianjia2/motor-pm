<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <div class="card-header">
          <span><strong>{{ isEdit ? '编辑项目' : '新建项目' }}</strong></span>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
        style="max-width:800px"
      >
        <el-divider content-position="left">基本信息</el-divider>

        <el-form-item label="项目类型" prop="project_type">
          <el-radio-group v-model="form.project_type" @change="onTypeChange">
            <el-radio value="hardware">电机研发项目（含样机试制）</el-radio>
            <el-radio value="software">软件研发项目（纯软件性能模块开发）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" placeholder="如：200kW永磁同步电机驱动器开发" />
        </el-form-item>
        <el-form-item label="项目编号" prop="code">
          <el-input v-model="form.code" placeholder="如：P2026-EM001" />
        </el-form-item>
        <el-form-item label="项目描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="简要描述项目背景和目标" />
        </el-form-item>
        <el-form-item label="客户">
          <div style="display:flex;gap:8px;width:100%">
            <el-select v-model="form.client_id" placeholder="选择客户" filterable clearable style="flex:1">
              <el-option v-for="c in clients" :key="c.id" :label="c.name + ' (' + c.abbreviation + ')'" :value="c.id" />
            </el-select>
            <el-button @click="openAddClient" size="small">+ 新增客户</el-button>
          </div>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="优先级">
              <el-select v-model="form.priority" style="width:100%">
                <el-option label="P0-最高" value="P0" />
                <el-option label="P1-高" value="P1" />
                <el-option label="P2-中" value="P2" />
                <el-option label="P3-低" value="P3" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" style="width:100%">
                <el-option label="高" value="high" />
                <el-option label="中" value="medium" />
                <el-option label="低" value="low" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="截止日期类型">
              <el-select v-model="form.deadline_type" style="width:100%">
                <el-option label="硬性" value="硬性" />
                <el-option label="可调" value="可调" />
                <el-option label="未知" value="未知" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="启动日期">
              <el-date-picker v-model="form.start_date" type="date" placeholder="选择日期" style="width:100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="计划完成日期">
              <el-date-picker v-model="form.planned_end_date" type="date" placeholder="选择日期" style="width:100%" value-format="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="当前阶段">
              <el-select v-model="form.current_phase_id" style="width:100%">
                <el-option v-for="p in phases" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider content-position="left">项目目标 (Section A)</el-divider>

        <el-form-item label="最终交付物">
          <el-input v-model="form.final_deliverable" type="textarea" :rows="2" placeholder="如：200kW电机样机2台 + 控制器2台 + 型式试验报告" />
        </el-form-item>
        <el-form-item label="验收标准">
          <el-input v-model="form.acceptance_criteria" type="textarea" :rows="2" placeholder="具体的验收指标和验收方" />
        </el-form-item>
        <el-form-item label="要解决的问题">
          <el-input v-model="form.problem_statement" type="textarea" :rows="2" placeholder="一句话描述项目要解决的核心问题" />
        </el-form-item>
        <el-form-item label="对齐目标">
          <el-input v-model="form.aligned_target" placeholder="对上支撑什么目标（公司KPI/客户合同/战略方向）" />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="合同总额(万)">
              <el-input-number v-model="form.contract_amount" :min="0" :precision="1" :step="10" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="总预算">
              <el-input-number v-model="form.budget_total" :min="0" :step="100000" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="已花费">
              <el-input-number v-model="form.budget_spent" :min="0" :step="100000" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" @click="submitForm" :loading="submitting">
            {{ isEdit ? '保存修改' : '创建项目' }}
          </el-button>
          <el-button @click="$router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 新增客户弹窗 -->
    <el-dialog v-model="showAddClient" title="新增客户" width="450px">
      <el-form :model="newClientForm" label-width="80px">
        <el-form-item label="客户名称" required>
          <el-input v-model="newClientForm.name" placeholder="如：优普森电气有限公司" />
        </el-form-item>
        <el-form-item label="缩写" required>
          <el-input v-model="newClientForm.abbreviation" placeholder="如：YPS（用于编号前缀）" maxlength="8" />
        </el-form-item>
        <el-form-item label="联系人">
          <el-input v-model="newClientForm.contact_person" placeholder="对接人姓名" />
        </el-form-item>
        <el-form-item label="联系电话">
          <el-input v-model="newClientForm.contact_phone" placeholder="对接人电话" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAddClient = false">取消</el-button>
        <el-button type="primary" @click="addClient">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { createProject, updateProject, getProject, getPhases, getClients, createClient, updateClient } from '../api/index.js'
import { currentProjectType } from '../stores/projectType.js'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const submitting = ref(false)
const phases = ref([])
const clients = ref([])
const showAddClient = ref(false)
const newClientForm = ref({ name: '', abbreviation: '', contact_person: '', contact_phone: '' })

const isEdit = computed(() => !!route.params.id)

const form = ref({
  name: '',
  code: '',
  project_type: 'hardware',
  description: '',
  client_id: null,
  priority: 'P1',
  difficulty: 'medium',
  deadline_type: '',
  start_date: null,
  planned_end_date: null,
  current_phase_id: 1,
  problem_statement: '',
  final_deliverable: '',
  acceptance_criteria: '',
  aligned_target: '',
  contract_amount: null,
  budget_total: null,
  budget_spent: 0,
  overall_status: 'normal',
  completion_pct: 0,
})

const rules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  code: [{ required: true, message: '请输入项目编号', trigger: 'blur' }],
}

const defaultForm = () => ({
  name: '', code: '', project_type: 'hardware', description: '', client_id: null, priority: 'P1',
  difficulty: 'medium', deadline_type: '', start_date: null, planned_end_date: null,
  current_phase_id: null, problem_statement: '', final_deliverable: '',
  acceptance_criteria: '', aligned_target: '', contract_amount: null, budget_total: null,
  budget_spent: 0, overall_status: 'normal', completion_pct: 0,
})

async function loadPhasesByType() {
  const { data } = await getPhases({ project_type: form.value.project_type })
  phases.value = data
  const cur = form.value.current_phase_id
  const valid = cur && data.some(p => p.id === cur)
  if (!valid) form.value.current_phase_id = data[0]?.id || null
}

function onTypeChange() {
  loadPhasesByType()
}

async function loadForm() {
  if (isEdit.value) {
    try {
      const { data } = await getProject(route.params.id)
      for (const key of Object.keys(form.value)) {
        if (key in data) form.value[key] = data[key]
      }
      currentProjectType.value = data.project_type || 'hardware'
    } catch (e) { ElMessage.error('项目加载失败: ' + (e?.message || '')) }
  }
}

onMounted(async () => {
  const clientsRes = await getClients()
  clients.value = clientsRes.data
  await loadForm()
  await loadPhasesByType()
})

// 同一组件在 /projects/new 与 /projects/:id/edit 间切换时组件实例复用，
// 需要监听路由变化重置表单
watch(() => route.params.id, (nid, oid) => {
  if (nid === oid) return
  form.value = defaultForm()
  loadForm()
})

onUnmounted(() => { currentProjectType.value = null })

function openAddClient() {
  // 每次打开重置表单,避免残留上次数据导致缩写冲突
  newClientForm.value = { name: '', abbreviation: '', contact_person: '', contact_phone: '' }
  showAddClient.value = true
}

async function addClient() {
  if (!newClientForm.value.abbreviation) {
    ElMessage.warning('请填写客户缩写')
    return
  }
  const f = newClientForm.value
  const existing = clients.value.find(c => c.abbreviation === f.abbreviation.trim())
  if (!f.name && !existing) {
    ElMessage.warning('请填写客户名称和缩写')
    return
  }
  try {
    if (existing) {
      // 同缩写=同一客户,视为补充/更新信息(如补录姓名电话)
      await ElMessageBox.confirm(
        `客户缩写「${f.abbreviation}」已存在(${existing.name})。将更新该客户的联系人信息,是否继续?`,
        '更新已有客户', { confirmButtonText: '更新', cancelButtonText: '取消' }
      )
      await updateClient(existing.id, { ...f, name: existing.name })
      ElMessage.success('客户信息已补充更新')
      form.value.client_id = existing.id
    } else {
      const res = await createClient(f)
      ElMessage.success('客户已添加')
      clients.value.push(res.data)
      form.value.client_id = res.data.id
    }
    showAddClient.value = false
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error('添加失败: ' + (e.response?.data?.message || e.response?.data?.detail || e.message))
  }
}

async function submitForm() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  // 合同总额未填时不下发,避免把手工标记置为 true
  const payload = { ...form.value, contract_amount: form.value.contract_amount ?? undefined }
  try {
    if (isEdit.value) {
      await updateProject(route.params.id, payload)
      ElMessage.success('项目已更新')
    } else {
      await createProject(payload)
      ElMessage.success('项目已创建')
    }
    router.push('/projects')
  } catch (e) {
    ElMessage.error('操作失败: ' + (e.response?.data?.message || e.message))
  } finally {
    submitting.value = false
  }
}
</script>
