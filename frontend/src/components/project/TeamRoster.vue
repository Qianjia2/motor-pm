<template>
  <el-card shadow="never">
    <template #header>
      <div class="flex-between">
        <span>
          <strong>项目团队</strong>
          <span v-if="members.length" style="color:var(--text-muted);font-size:12px;margin-left:8px">
            共 {{ members.length }} 人
          </span>
        </span>
        <el-button type="primary" size="small" @click="openAdd">
          <el-icon><Plus /></el-icon> 添加成员
        </el-button>
      </div>
    </template>

    <div v-loading="loading" style="min-height:60px">
      <div v-if="!loading && !members.length" style="text-align:center;padding:20px;color:var(--text-muted);font-size:13px">
        尚未配置项目组，点右上角「添加成员」开始组建
      </div>

      <el-table v-else :data="sorted" size="small" stripe>
        <el-table-column label="姓名" width="90">
          <template #default="{ row }">{{ row.member?.name || '—' }}</template>
        </el-table-column>
        <el-table-column label="项目角色" width="130">
          <template #default="{ row }">
            <el-select v-model="row.role_id" size="small" style="width:100%" @change="saveRole(row)">
              <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="member.title" label="职务" width="100" show-overflow-tooltip />
        <el-table-column prop="member.department" label="部门" width="110" show-overflow-tooltip />
        <el-table-column label="投入比例" width="150">
          <template #header>
            <span style="display:inline-flex;align-items:center;gap:3px">投入比例
              <el-tooltip content="该成员在本项目投入的工作量占比（0~100%），100% 表示全职投入本项目。用于资源负载评估与人员调配参考。" placement="top">
                <el-icon style="cursor:help;color:var(--text-muted)"><QuestionFilled /></el-icon>
              </el-tooltip>
            </span>
          </template>
          <template #default="{ row }">
            <el-slider v-model="row.allocation_pct" :min="0" :max="100" @change="saveAllocation(row)" style="width:120px" />
          </template>
        </el-table-column>
        <el-table-column label="关键" width="70">
          <template #default="{ row }">
            <el-switch v-model="row.is_key" size="small" @change="saveKey(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-popconfirm title="移出项目组?" @confirm="removeMember(row)">
              <template #reference><el-button type="danger" link size="small">移除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 添加成员 -->
    <el-dialog v-model="showAdd" title="添加项目成员" width="550px">
      <el-form :model="addForm" label-width="100px">
        <el-form-item label="成员">
          <el-select v-model="addForm.member_id" placeholder="选择成员" filterable style="width:100%">
            <el-option v-for="m in availableMembers" :key="m.id" :label="`${m.name}（${m.department || '—'}）`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="addForm.role_id" placeholder="选择角色" style="width:100%">
            <el-option v-for="r in roles" :key="r.id" :label="r.name" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="投入比例(%)">
          <el-input-number v-model="addForm.allocation_pct" :min="0" :max="100" />
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">成员在本项目投入的工作量占比，100%=全职投入（默认）</div>
        </el-form-item>
        <el-form-item label="关键人员">
          <el-switch v-model="addForm.is_key" />
        </el-form-item>
        <el-form-item label="可访问阶段">
          <el-checkbox-group v-model="addForm.phase_ids">
            <el-checkbox v-for="p in phases" :key="p.id" :label="p.id" :value="p.id" style="margin-right:12px">{{ p.name }}</el-checkbox>
          </el-checkbox-group>
          <div style="font-size:11px;color:var(--text-muted);margin-top:4px">留空=全部可见，勾选=仅可见指定阶段</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="confirmAdd">添加</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, QuestionFilled } from '@element-plus/icons-vue'
import {
  getProjectMembers, addProjectMember, updateProjectMember, removeProjectMember,
  getTeamMembers, getRoles, getPhases,
} from '../../api/index.js'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  projectType: { type: String, default: '' },
})
const emit = defineEmits(['changed'])

const members = ref([])
const roles = ref([])
const pool = ref([])
const allPhases = ref([])
const phases = ref([])
const loading = ref(true)
const saving = ref(false)
const showAdd = ref(false)
const addForm = ref({ member_id: null, role_id: null, allocation_pct: 100, is_key: false, phase_ids: [] })

const availableMembers = computed(() => {
  const used = new Set(members.value.map(m => m.member_id))
  return pool.value.filter(m => !used.has(m.id))
})

// 阶段接口返回硬件(PP*)和软件(S*)两套，只留本项目类型那套
// 类型未知(父组件还没拉到项目)时不过滤，等 watch 补上
function matchType(p, t) {
  if (t === 'software') return p.project_type === 'software'
  if (t === 'hardware') return !p.project_type || p.project_type === 'hardware'
  return true
}
watch(() => props.projectType, (t) => {
  phases.value = allPhases.value.filter(p => matchType(p, t))
})

// 角色下拉改过之后 row.role.name 是旧值，按 role_id 现查，排序和标签才跟得上
function roleName(row) {
  return roles.value.find(r => r.id === row.role_id)?.name || row.role?.name || ''
}
const isPm = (row) => roleName(row) === '项目经理'

// 概览要一眼看到关键角色：项目经理排最前，其次关键人员，最后按投入比例降序
const sorted = computed(() => [...members.value].sort((a, b) => {
  const pm = (isPm(b) ? 1 : 0) - (isPm(a) ? 1 : 0)
  if (pm) return pm
  const key = (b.is_key ? 1 : 0) - (a.is_key ? 1 : 0)
  if (key) return key
  return (b.allocation_pct || 0) - (a.allocation_pct || 0)
}))

async function reload() {
  members.value = (await getProjectMembers(props.projectId)).data || []
  emit('changed', members.value.length)
}

async function load() {
  loading.value = true
  try {
    const [m, r, p, ph] = await Promise.all([
      getProjectMembers(props.projectId), getRoles(), getTeamMembers(), getPhases(),
    ])
    members.value = m.data || []
    roles.value = r.data || []
    pool.value = p.data || []
    allPhases.value = ph.data || []
    phases.value = allPhases.value.filter(x => matchType(x, props.projectType))
    emit('changed', members.value.length)
  } catch (e) {
    ElMessage.error('团队加载失败: ' + (e?.message || ''))
  } finally {
    loading.value = false
  }
}

function openAdd() {
  addForm.value = { member_id: null, role_id: null, allocation_pct: 100, is_key: false, phase_ids: [] }
  showAdd.value = true
}

async function confirmAdd() {
  const f = addForm.value
  if (!f.member_id || !f.role_id) { ElMessage.warning('请选择成员和角色'); return }
  saving.value = true
  try {
    await addProjectMember(props.projectId, {
      member_id: f.member_id, role_id: f.role_id,
      allocation_pct: f.allocation_pct, is_key: f.is_key,
      phase_ids: f.phase_ids && f.phase_ids.length ? JSON.stringify(f.phase_ids) : '[]',
    })
    await reload()
    showAdd.value = false
    ElMessage.success('已添加')
  } catch (e) {
    const d = e?.response?.data?.detail
    ElMessage.error('添加失败: ' + (typeof d === 'string' ? d : (e.message || '请重试')))
  } finally {
    saving.value = false
  }
}

async function removeMember(row) {
  try {
    await removeProjectMember(row.id)
    await reload()
    ElMessage.success('已移出项目组')
  } catch (e) {
    ElMessage.error('移除失败: ' + (e?.message || ''))
  }
}

async function saveRole(row) {
  try { await updateProjectMember(row.id, { role_id: row.role_id }) }
  catch (e) { ElMessage.error('角色保存失败'); }
}

async function saveAllocation(row) {
  try { await updateProjectMember(row.id, { allocation_pct: row.allocation_pct }) }
  catch (e) { ElMessage.error('投入比例保存失败'); }
}

async function saveKey(row) {
  try { await updateProjectMember(row.id, { is_key: row.is_key }) }
  catch (e) { ElMessage.error('保存失败'); }
}

onMounted(load)
</script>
