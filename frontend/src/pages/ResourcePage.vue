<template>
  <div class="resource-page">
    <el-tabs v-model="activeTab" type="card" @tab-change="onTabChange">
      <!-- Tab 1: 资源负荷 -->
      <el-tab-pane label="资源负荷" name="load">
        <div class="stat-grid" style="margin-bottom:20px">
          <div class="stat-card stat-info">
            <div class="stat-value">{{ members.length }}</div>
            <div class="stat-label">团队总人数</div>
          </div>
          <div class="stat-card stat-danger">
            <div class="stat-value">{{ overloadedCount }}</div>
            <div class="stat-label">过载人员</div>
          </div>
          <div class="stat-card stat-success">
            <div class="stat-value">{{ totalAssignments }}</div>
            <div class="stat-label">总项目分配</div>
          </div>
          <div class="stat-card stat-warning">
            <div class="stat-value">{{ avgAllocation }}%</div>
            <div class="stat-label">平均投入比例</div>
          </div>
        </div>

        <div class="card" style="margin-bottom:20px">
          <div class="card-header">
            <div class="card-title">资源负荷直方图</div>
            <div class="card-actions"><el-button size="small" @click="loadMatrix" :loading="loading">刷新</el-button></div>
          </div>
          <ResourceHistogram :data="resourceData" @select="onSelectPerson" />
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">人员-项目分配表</div></div>
          <el-table :data="resourceData" stripe size="small">
            <el-table-column prop="name" label="姓名" width="80" fixed />
            <el-table-column prop="department" label="部门" width="100" />
            <el-table-column label="总投入" width="140">
              <template #default="{row}">
                <el-progress :percentage="Math.min(row.total_allocation,100)" :stroke-width="8"
                  :color="row.total_allocation>100?'#ef4444':row.total_allocation>80?'#f59e0b':'#10b981'" />
              </template>
            </el-table-column>
            <el-table-column label="参与项目" min-width="350">
              <template #default="{row}">
                <span v-if="!row.projects.length" style="color:var(--text-muted)">未分配</span>
                <span v-for="p in row.projects" :key="p.project_id" class="tag" :class="p.has_recent_activity?'tag-blue':'tag-gray'" style="margin:1px 2px;cursor:pointer;font-size:11px"
                  @click="$router.push('/projects/'+p.project_id)">
                  <span v-if="p.has_recent_activity" title="近4周有周报活动">● </span>
                  {{ p.project_name }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="活跃" width="70">
              <template #default="{row}">
                <span v-if="row.active_projects">{{ row.active_projects }} 个项目</span>
                <span v-else style="color:#c0c4cc">-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="80">
              <template #default="{row}">
                <span v-if="row.is_overloaded" class="tag tag-red">过载</span>
                <span v-else-if="row.total_allocation>80" class="tag tag-orange">偏高</span>
                <span v-else class="tag tag-green">正常</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 人员与账号 -->
      <el-tab-pane label="人员与账号" name="members">
        <div class="stat-grid" style="margin-bottom:20px">
          <div class="stat-card stat-info">
            <div class="stat-value">{{ members.length }}</div>
            <div class="stat-label">团队总人数</div>
          </div>
          <div class="stat-card stat-success">
            <div class="stat-value">{{ accountCount }}</div>
            <div class="stat-label">已关联账号</div>
          </div>
          <div class="stat-card stat-warning">
            <div class="stat-value">{{ deptPermCount }}</div>
            <div class="stat-label">部门矩阵生效</div>
          </div>
          <div class="stat-card stat-danger">
            <div class="stat-value">{{ noDeptCount }}</div>
            <div class="stat-label">未设置部门</div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="card-title">人员列表</div>
            <div style="display:flex;gap:8px">
              <el-input v-model="memberKeyword" placeholder="搜索姓名 / 部门" size="small" clearable
                style="width:210px" :prefix-icon="Search" />
              <el-button type="primary" size="small" @click="openMemberEdit(null)"><el-icon><Plus /></el-icon> 新增人员</el-button>
            </div>
          </div>
          <el-table :data="filteredMembers" stripe :row-style="{height:'56px'}" :cell-style="{padding:'12px 0'}">
            <el-table-column label="姓名" width="120" fixed>
              <template #default="{row}">
                <div class="mb-name">
                  <span class="mb-avatar" :style="{ background: deptColor(row.department) }">{{ (row.name || '?').slice(0, 1) }}</span>
                  <span>{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="所属部门" width="140">
              <template #default="{row}">
                <el-select :model-value="row.department || ''" size="small" style="width:130px" clearable
                  placeholder="按部门设置权限" @change="(v) => quickChangeDept(row, v)">
                  <el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.name" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="权限来源" width="150">
              <template #default="{row}">
                <el-tooltip placement="top" :content="permSource(row).tip" :show-after="200">
                  <span class="tag" :class="permSource(row).cls" style="font-size:11px;cursor:default">{{ permSource(row).label }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="职务" width="110">
              <template #default="{row}">
                <span v-if="row.title" style="color:var(--text-secondary);font-size:13px">{{ row.title }}</span>
                <span v-else style="color:#c0c4cc">—</span>
              </template>
            </el-table-column>
            <el-table-column label="关联账号" width="120">
              <template #default="{row}">
                <template v-if="getUserForMember(row)">
                  <span :class="'tag tag-'+roleColor(getUserForMember(row).role)" style="font-size:12px;cursor:pointer;padding:4px 8px" @click="openMemberEdit(row)">{{ getUserForMember(row).username }}</span>
                </template>
                <el-button v-else link size="small" type="primary" @click="openMemberEdit(row)">创建账号</el-button>
              </template>
            </el-table-column>
            <el-table-column prop="email" label="邮箱" min-width="160" show-overflow-tooltip />
            <el-table-column label="最后登录" width="150">
              <template #default="{row}">
                <span v-if="getUserForMember(row)?.last_login" style="font-size:12px;color:var(--text-secondary)">{{ fmtTime(getUserForMember(row).last_login) }}</span>
                <span v-else style="color:#c0c4cc;font-size:12px">-</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="210" fixed="right">
              <template #default="{row}">
                <el-button link size="small" type="primary" @click="openMemberEdit(row)">编辑</el-button>
                <el-button link size="small" type="warning" @click="bindDingtalk(row)">绑定钉钉</el-button>
                <template v-if="getUserForMember(row)">
                  <el-button link size="small" @click="resetUserPwd(getUserForMember(row))">重置密码</el-button>
                </template>
                <el-popconfirm v-if="row.is_active!==false" title="确认停用该人员和关联账号?" @confirm="deactivateMember(row.id)">
                  <template #reference><el-button link size="small" type="danger">停用</el-button></template>
                </el-popconfirm>
                <el-popconfirm v-else title="重新启用?" @confirm="reactivateMember(row.id)">
                  <template #reference><el-button link size="small" type="success">启用</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>

      </el-tab-pane>
      <el-tab-pane label="角色权限" name="permissions">
        <RolePermissionPanel @saved="onPermSaved" />
      </el-tab-pane>
    </el-tabs>

    <!-- Member Dialog -->
    <el-dialog v-model="showAddMember" :title="editingMember ? '编辑人员与账号' : '新增人员与账号'" width="700px" top="3vh">
      <el-form :model="memberForm" label-width="80px" autocomplete="off">
        <el-form-item label="姓名" required><el-input v-model="memberForm.name" autocomplete="off" /></el-form-item>
        <el-form-item label="部门">
          <el-select v-model="memberForm.department" filterable allow-create default-first-option placeholder="选择或输入部门" style="width:100%" autocomplete="off">
            <el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="职务">
          <el-select v-model="memberForm.title" filterable allow-create default-first-option placeholder="如：项目经理、软件工程师" style="width:100%">
            <el-option v-for="r in projectRoles" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="邮箱"><el-input v-model="memberForm.email" autocomplete="off" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="memberForm.phone" autocomplete="off" /></el-form-item>
        <el-form-item label="技能"><el-input v-model="memberForm.skills" placeholder="电磁仿真,Maxwell" autocomplete="off" /></el-form-item>
        <el-divider content-position="center">账号与权限</el-divider>
        <div v-if="!editingMember" style="font-size:12px;color:#8f959e;margin:-8px 0 10px">新增时填写用户名和密码将同时创建登录账号；留空则仅添加人员，之后可在列表点「创建账号」补充</div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="用户名">
              <el-input v-model="memberForm.username" placeholder="登录账号" :disabled="!!editingMember && !!memberForm.userId" autocomplete="off" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="密码">
              <el-input v-model="memberForm.password" type="password" show-password :placeholder="editingMember ? '输入新密码（留空不修改）' : '至少3位'" autocomplete="new-password" />
              <span style="font-size:11px;color:#8f959e">{{ editingMember ? '加密存储，不可查看原文' : '' }}</span>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="账号角色">
          <el-select v-model="memberForm.accRole" style="width:100%" :disabled="!editingMember && !memberForm.username">
            <el-option label="管理员" value="admin" />
            <el-option label="编辑者" value="editor" />
            <el-option label="查看者" value="viewer" />
            <el-option label="成员" value="member" />
          </el-select>
          <span style="font-size:11px;color:#8f959e">管理员可直接查看全部项目和驾驶舱数据</span>
        </el-form-item>
        <el-form-item label="知识库管理员" v-if="memberForm.userId || memberForm.username">
          <el-switch v-model="memberForm.kbAdmin" />
          <span style="font-size:11px;color:#8f959e;margin-left:8px">可在知识库中删除项目文档（个人级授权，不影响他人）</span>
        </el-form-item>
      </el-form>
      <div v-if="memberForm.department" style="margin-top:0;font-size:12px;color:var(--text-secondary)">
        账号权限按所属部门（{{ memberForm.department }}）的权限矩阵计算，可在「角色权限」Tab 配置
      </div>
      <template #footer><el-button @click="showAddMember=false">取消</el-button><el-button type="primary" @click="saveMember" :loading="savingMember">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Search } from '@element-plus/icons-vue'
import { getTeamMembers, createTeamMember, updateTeamMember, getResourceMatrix, getDepartments } from '../api/index.js'
import api from '../api/index.js'
import ResourceHistogram from '../components/resource/ResourceHistogram.vue'
import RolePermissionPanel from '../components/resource/RolePermissionPanel.vue'

const activeTab = ref('load')
const resourceData = ref([])
const members = ref([])
const loading = ref(false)
const showAddMember = ref(false)
const editingMember = ref(null)
const savingMember = ref(false)
const memberForm = reactive({ name: '', department: '', title: '', email: '', phone: '', skills: '', username: '', password: '', userId: null, accRole: 'member', kbAdmin: false })
const origAccRole = ref('member')

// Account management
const users = ref([])
const projectRoles = ref([])
const departments = ref([])

const MODULE_LABELS = {
  my_work: '我的工作台', dashboard: '项目驾驶舱', mgmt_weekly: '管理层周报',
  product_tech: '产品技术库', bom: 'BOM管理', projects: '系统集成开发项目台账',
  tasks_milestones: '任务与里程碑', issue_risks: '问题风险管理', phase_gate: '阶段门评审',
  reports: '报告中心', ai: 'AI 助手', knowledge: '知识库',
  clients: '客户管理', users: '资源管理', audit_logs: '操作审计', settings: '系统设置',
}

// 各部门已配置的权限矩阵摘要（key=部门名）
const deptMatrixMap = computed(() => {
  const map = {}
  for (const d of departments.value) {
    const perms = (d.permissions && typeof d.permissions === 'object') ? d.permissions : {}
    const modules = Object.entries(perms)
      .filter(([, p]) => p && typeof p === 'object' && p.view === true)
      .map(([k]) => MODULE_LABELS[k] || k)
    map[d.name] = { count: modules.length, modules }
  }
  return map
})

// 每个人员的权限来源：优先按所属部门的权限矩阵，未配置则沿用账号角色
function permSource(row) {
  const dept = (row.department || '').trim()
  if (dept) {
    const m = deptMatrixMap.value[dept]
    if (m && m.count > 0) {
      return {
        type: 'dept',
        cls: 'tag-blue',
        label: `部门矩阵·${m.count} 个模块`,
        tip: `权限按部门「${dept}」的矩阵计算，可访问：${m.modules.join('、')}`,
      }
    }
    if (m) {
      return {
        type: 'dept-unset',
        cls: 'tag-orange',
        label: '部门矩阵未配置',
        tip: `部门「${dept}」尚未配置权限矩阵，权限暂沿用账号角色；可在「角色权限」Tab 为该部门勾选矩阵`,
      }
    }
    return {
      type: 'role',
      cls: 'tag-gray',
      label: '沿用角色权限',
      tip: `所属部门「${dept}」未在「角色权限」Tab 中配置，权限沿用账号角色`,
    }
  }
  const u = getUserForMember(row)
  return {
    type: 'role',
    cls: 'tag-gray',
    label: '沿用角色权限',
    tip: u ? `未设置部门，权限沿用账号角色「${roleLabel(u.role)}」` : '未设置部门且未关联账号',
  }
}

const AVATAR_COLORS = ['#1d6fd6', '#10b981', '#f59e0b', '#8b5cf6', '#0ea5e9', '#f43f5e', '#14b8a6', '#f97316']
function deptColor(name) {
  let h = 0
  for (const c of (name || '')) h = (h * 31 + c.codePointAt(0)) % 997
  return AVATAR_COLORS[h % AVATAR_COLORS.length]
}

// 人员与账号：搜索与统计
const memberKeyword = ref('')
const filteredMembers = computed(() => {
  const kw = memberKeyword.value.trim().toLowerCase()
  if (!kw) return members.value
  return members.value.filter(m =>
    (m.name || '').toLowerCase().includes(kw) || (m.department || '').toLowerCase().includes(kw))
})
const accountCount = computed(() => members.value.filter(m => getUserForMember(m)).length)
const deptPermCount = computed(() => members.value.filter(m => permSource(m).type === 'dept').length)
const noDeptCount = computed(() => members.value.filter(m => !(m.department || '').trim()).length)

const overloadedCount = computed(() => resourceData.value.filter(r => r.is_overloaded).length)
const totalAssignments = computed(() => resourceData.value.reduce((s, r) => s + r.projects.length, 0))
const avgAllocation = computed(() => {
  const total = resourceData.value.reduce((s, r) => s + r.total_allocation, 0)
  return Math.round(total / Math.max(1, resourceData.value.length))
})

function roleColor(role) {
  const map = { admin: 'red', editor: 'blue', biz: 'orange', viewer: 'purple', member: 'green' }
  return map[role] || 'gray'
}
function roleLabel(role) {
  const map = { admin: '管理员', editor: '编辑者', biz: '商务经理', viewer: '查看者', member: '成员' }
  return map[role] || role
}
onMounted(() => { loadAll() })

async function loadAll() {
  loading.value = true
  try {
    const [mRes, rmRes] = await Promise.all([
      getTeamMembers(),
      getResourceMatrix().catch(() => ({ data: [] })),
    ])
    members.value = mRes.data || []
    resourceData.value = rmRes.data || []
    if (!resourceData.value.length && members.value.length) {
      resourceData.value = members.value.map(m => ({
        member_id: m.id, name: m.name, department: m.department || '',
        title: m.title || '', total_allocation: 0, is_overloaded: false, projects: [],
      }))
    }
  } finally { loading.value = false }
}

async function loadMatrix() {
  loading.value = true
  try { const res = await getResourceMatrix(); if (res.data?.length) resourceData.value = res.data } finally { loading.value = false }
}

function onSelectPerson(item) {}

function onTabChange(tab) {
  if (tab === 'members') { loadUsers(); loadProjectRoles(); loadDepartments() }
}

async function openMemberEdit(row) {
  editingMember.value = row
  // Ensure users/departments are loaded
  if (!users.value.length) await loadUsers()
  await loadProjectRoles()  // 每次打开都刷新，自定义角色保存后立即可选
  if (!departments.value.length) await loadDepartments()

  if (row) {
    const acc = getUserForMember(row)
    const accRole = acc ? (acc.role || 'member') : 'member'
    origAccRole.value = accRole
    Object.assign(memberForm, {
      name: row.name||'', department: row.department||'', title: row.title||'',
      email: row.email||'', phone: row.phone||'', skills: row.skills||'',
      username: acc ? acc.username : '', password: '',
      userId: acc ? acc.id : null, accRole,
      kbAdmin: acc ? !!acc.kb_admin : false,
    })
  } else {
    origAccRole.value = 'member'
    Object.assign(memberForm, {
      name: '', department: '', title: '', email: '', phone: '', skills: '',
      username: '', password: '', userId: null, accRole: 'member', kbAdmin: false,
    })
  }
  showAddMember.value = true
}

async function saveMember() {
  if (!memberForm.name) { ElMessage.warning('请输入姓名'); return }
  savingMember.value = true
  try {
    // Save personnel info — strip account fields from TeamMember data
    const { userId, username, password, ...memberData } = memberForm
    let savedMember
    if (editingMember.value) {
      await updateTeamMember(editingMember.value.id, memberData)
      savedMember = editingMember.value
    } else {
      const res = await createTeamMember({...memberData, username, password, accRole: memberForm.accRole})
      savedMember = res.data || res
    }

    // Handle account: createTeamMember may have auto-created it
    const accountAutoCreated = savedMember?.account_created

    if (!accountAutoCreated && username && password && !editingMember.value) {
      // createTeamMember did NOT create account (username might be taken), try explicitly
      try {
        await api.post('/auth/users', { username, password, member_id: savedMember?.id, role: memberForm.accRole, kb_admin: memberForm.kbAdmin })
        ElMessage.success('人员与账号已创建，可登录')
      } catch(e) {
        if (e?.response?.status === 400 || e?.response?.status === 409) {
          ElMessage.warning('用户名已被占用，请换一个')
        }
      }
    } else if (accountAutoCreated) {
      ElMessage.success('人员与账号已创建，可登录')
    } else if (editingMember.value && userId) {
      // Update existing account (password optional); 仅当角色被修改时下发,避免误覆盖自定义角色
      const body = {}
      if (memberForm.accRole !== origAccRole.value) body.role = memberForm.accRole
      if (password) body.password = password
      body.kb_admin = memberForm.kbAdmin
      await api.put('/auth/users/' + userId, body)
      ElMessage.success('已更新人员与账号')
    } else if (editingMember.value && username && password) {
      // No userId but has username — create account for existing member
      try {
        await api.post('/auth/users', { username, password, member_id: editingMember.value.id })
        ElMessage.success('账号已创建')
      } catch(e) {
        ElMessage.warning('账号创建失败: ' + ((((e.response||{}).data||{}).detail) || e.message))
      }
    } else if (editingMember.value) {
      ElMessage.success('已更新人员信息')
    }

    showAddMember.value = false; editingMember.value = null
    await loadAll()
    if (activeTab.value === 'members') { await loadUsers() }
  } catch (e) { ElMessage.error('操作失败: ' + (e?.response?.data?.detail || e.message)) }
  savingMember.value = false
}

async function deactivateMember(id) {
  const user = users.value.find(u => u.member_name && members.value.find(m => m.id === id && m.name === u.member_name))
  if (user) {
    try { await api.put(`/auth/users/${user.id}`, { is_active: false }) } catch(e) {}
  }
  await updateTeamMember(id, { is_active: false })
  ElMessage.success('人员和账号已停用')
  await loadAll(); await loadUsers()
}
async function reactivateMember(id) {
  const user = users.value.find(u => u.member_name && members.value.find(m => m.id === id && m.name === u.member_name))
  if (user) {
    try { await api.put(`/auth/users/${user.id}`, { is_active: true }) } catch(e) {}
  }
  await updateTeamMember(id, { is_active: true })
  ElMessage.success('已启用')
  await loadAll(); await loadUsers()
}

function getUserForMember(member) {
  return users.value.find(u => (u.member_name && u.member_name === member.name) || u.full_name === member.name)
}

function fmtTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d)) return iso
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// Account CRUD
async function loadUsers() {
  try { const r=await api.get('/auth/users'); users.value=r.data||[] } catch { users.value=[] }
}
async function loadDepartments() {
  try { const r=await getDepartments(); departments.value=r.data||[] } catch { departments.value=[] }
}
// 职务下拉选项：系统设置的角色表（项目经理/软件工程师等），支持自定义输入
async function loadProjectRoles() {
  try {
    const r = await api.get('/lookups/roles')
    projectRoles.value = (r.data || []).map(x => x.name).filter(Boolean)
  } catch { projectRoles.value = [] }
}

async function resetUserPwd(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入新密码（至少3位）', '重置密码', { inputType: 'password', confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) {
      await api.put(`/auth/users/${row.id}`, { password: value })
      ElMessage.success('密码已重置')
    }
  } catch {}
}

async function bindDingtalk(row) {
  try {
    const res = await api.get(`/auth/bind-dingtalk-url`, { params: { member_id: row.id } })
    window.open(res.url, 'dingtalk_bind', 'width=400,height=500')
    ElMessage.info('请用钉钉扫描弹出的二维码完成绑定')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '获取绑定二维码失败')
  }
}

async function delUser(id) {
  try { await api.delete(`/auth/users/${id}`); ElMessage.success('已删除'); await loadUsers() }
  catch (e) { ElMessage.error(e?.response?.data?.detail || '删除失败') }
}

async function quickChangeDept(row, deptName) {
  try {
    await updateTeamMember(row.id, { department: deptName || '' })
    ElMessage.success('所属部门已更新，权限按该部门矩阵计算')
    await loadAll()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '操作失败') }
}

async function onPermSaved() {
  await Promise.all([loadDepartments(), loadUsers()])
}

</script>

<style scoped>
.resource-page { max-width: 1400px; }
.tag-gray { background:#f0f0f0; color:#909399; border:1px solid #ddd; }
.mb-name { display:flex; align-items:center; gap:9px; }
.mb-avatar {
  width:32px; height:32px; border-radius:50%; color:#fff;
  font-size:14px; font-weight:600; flex-shrink:0;
  display:flex; align-items:center; justify-content:center;
}
</style>
