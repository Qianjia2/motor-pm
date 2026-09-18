<template>
  <div class="rp-panel">
    <div class="rp-body">
      <!-- 左栏：角色列表（按部门分组） -->
      <div class="card rp-left">
        <div class="card-header">
          <div class="card-title">角色列表</div>
          <el-button type="primary" size="small" @click="openDeptDialog(null)"><el-icon><Plus /></el-icon> 新增部门</el-button>
        </div>
        <div class="rp-nav">
          <div v-for="d in departments" :key="d.id" class="rp-dept">
            <div class="rp-nav-item" :class="{ active: selectedDeptId === d.id }" @click="selectDept(d.id)">
              <span class="rp-nav-name">{{ d.name }}</span>
              <span class="rp-nav-badge">{{ d.role_count }}</span>
              <span class="rp-nav-ops">
                <el-button link size="small" @click.stop="openRoleForDept(d.id)">+角色</el-button>
                <el-button link size="small" @click.stop="openDeptDialog(d)">编辑</el-button>
                <el-popconfirm title="确认删除该部门？" @confirm="removeDept(d.id)">
                  <template #reference><el-button link size="small" type="danger" @click.stop>删</el-button></template>
                </el-popconfirm>
              </span>
            </div>
            <div v-for="r in deptRoles(d.id)" :key="r.id" class="rp-role-item"
                 :class="{ active: selectedRoleId === r.id }" @click="selectRole(r)">
              <span class="rp-role-name">{{ r.name }}</span>
              <span class="rp-role-desc">{{ r.desc || '—' }}</span>
              <span class="rp-role-ops">
                <el-button link size="small" @click.stop="openRoleDialog(r)">编辑</el-button>
                <el-popconfirm title="确认删除该角色？该操作不可恢复" @confirm="removeRole(r.id)">
                  <template #reference><el-button link size="small" type="danger" @click.stop>删</el-button></template>
                </el-popconfirm>
              </span>
            </div>
            <div v-if="!deptRoles(d.id).length" class="rp-role-empty">暂无角色</div>
          </div>
          <div v-if="!departments.length" class="rp-empty" style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px">
            暂无部门，请先新增
          </div>
        </div>
      </div>

      <!-- 右栏 -->
      <div class="rp-right">
        <div class="card">
          <div class="card-header">
            <div class="card-title">权限设置：{{ currentDeptLabel }}</div>
            <div style="display:flex;gap:8px;align-items:center">
              <el-button size="small" type="primary" plain :disabled="!selectedDept" @click="openRoleDialog(null)"><el-icon><Plus /></el-icon> 新增角色</el-button>
              <span v-if="!selectedDept" style="font-size:12px;color:var(--text-muted)">请先在左侧选择部门</span>
              <el-button type="primary" size="small" :disabled="!matrixDirty || !selectedDept" @click="saveMatrix">保存矩阵</el-button>
              <el-button size="small" :disabled="!selectedDept" @click="applyToMembers">应用到本部门所有人</el-button>
            </div>
          </div>
          <div v-if="selectedDept" style="padding:12px 0">
            <PermissionMatrixEditor v-model="matrix" @change="matrixDirty = true" />
            <div style="margin-top:8px;font-size:12px;color:var(--text-muted)">
              这是<strong>模板</strong>：新建人员时默认套用，但改动<strong>不会</strong>自动影响已有账号
              （权限一旦配到人身上就以那份为准）。保存后如需对全部门生效，
              点右上角「应用到本部门所有人」，确认框会说明将覆盖哪些人。
            </div>
          </div>
          <div v-else style="padding:40px;text-align:center;color:var(--text-muted);font-size:13px">
            请在左侧选择一个部门后配置其权限矩阵
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="card-title">说明</div></div>
          <div class="rp-desc">
            <div v-if="selectedRole" class="rp-desc-role">
              <div class="rp-desc-role-head">
                <span class="rp-desc-role-name">{{ selectedRole.name }}</span>
                <el-button link size="small" type="primary" @click="openRoleDialog(selectedRole)">编辑</el-button>
                <el-popconfirm title="确认删除该角色？该操作不可恢复" @confirm="removeRole(selectedRole.id)">
                  <template #reference><el-button link size="small" type="danger">删除</el-button></template>
                </el-popconfirm>
              </div>
              <div class="rp-desc-role-desc">{{ selectedRole.desc || '暂无说明' }}</div>
              <div class="rp-desc-muted">所属部门：{{ deptName(selectedRole.dept_id) }} · 该部门共 {{ deptRoles(selectedRole.dept_id).length }} 个角色</div>
            </div>
            <div v-else class="rp-desc-hint">在左侧选择一个角色查看其职责说明</div>
            <div class="rp-desc-block">
              <div class="rp-desc-title">权限规则</div>
              <div class="rp-desc-text">
                权限<strong>按人</strong>：每个账号自己那份矩阵说了算，在「人员与账号」Tab 的「权限」里单独配置，
                改完即时生效、不需要重新登录。这里配的是<strong>部门模板</strong>——新建人员时默认套用，
                改完要点「应用到本部门所有人」才会影响到已有账号。角色仅作为人员分组标签，不参与权限计算。
              </div>
            </div>
            <div class="rp-desc-block">
              <div class="rp-desc-title">角色说明参考示例</div>
              <div class="rp-desc-text">新建角色时，可在「说明」中按「权限配置：…」格式填写该角色的职责范围，便于快速识别：</div>
              <div v-for="t in roleTemplates" :key="t.name" class="rp-desc-tpl">
                <span class="rp-desc-tpl-name">{{ t.name }}</span>
                <span class="rp-desc-tpl-desc">{{ t.desc }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 部门对话框 -->
    <el-dialog v-model="deptDialog.show" :title="deptDialog.editing ? '编辑部门' : '新增部门'" width="400px">
      <el-form label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="deptDialog.form.name" maxlength="64" placeholder="如：产品工程部" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="deptDialog.show = false">取消</el-button>
        <el-button type="primary" @click="saveDept">保存</el-button>
      </template>
    </el-dialog>

    <!-- 角色对话框（仅作人员分组标签） -->
    <el-dialog v-model="roleDialog.show" :title="roleDialog.editing ? '编辑角色' : '新增角色'" width="480px">
      <el-form label-width="70px">
        <el-form-item label="名称" required>
          <el-input v-model="roleDialog.form.name" maxlength="64" placeholder="如：硬件组长" />
        </el-form-item>
        <el-form-item label="所属部门">
          <el-select v-model="roleDialog.form.dept_id" placeholder="选择部门" style="width:100%">
            <el-option v-for="d in departments" :key="d.id" :label="d.name" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="roleDialog.form.desc" maxlength="256" placeholder="如：权限配置：负责产品研发、技术方案、项目执行" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialog.show = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getDepartments, createDepartment, updateDepartment, deleteDepartment,
  getPermissionRoles, createPermissionRole, updatePermissionRole, deletePermissionRole,
  applyDepartmentPermissions,
} from '../../api/index.js'
import PermissionMatrixEditor from './PermissionMatrixEditor.vue'

const emit = defineEmits(['saved'])

const roleTemplates = [
  { name: '系统管理员', desc: '权限配置：拥有所有权限，管理系统配置和用户' },
  { name: '销售', desc: '权限配置：负责商机跟踪、客户管理、销售预测' },
  { name: '技术', desc: '权限配置：负责产品研发、技术方案、项目执行' },
  { name: '财务', desc: '权限配置：负责预算管理、成本核算、财务分析' },
  { name: '项目经理', desc: '权限配置：负责项目整体管理、进度协调、资源调配' },
]

const departments = ref([])
const roles = ref([])
const selectedDeptId = ref(null)
const selectedRoleId = ref(null)
const matrix = ref({})
const matrixDirty = ref(false)

const selectedDept = computed(() => departments.value.find(d => d.id === selectedDeptId.value) || null)
const currentDeptLabel = computed(() => selectedDept.value ? selectedDept.value.name : '未选择部门')
const deptRoles = (deptId) => roles.value.filter(r => r.dept_id === deptId)
const deptName = (deptId) => departments.value.find(d => d.id === deptId)?.name || '—'
const selectedRole = computed(() => roles.value.find(r => r.id === selectedRoleId.value) || null)

function selectDept(id) {
  selectedDeptId.value = id
  const d = departments.value.find(x => x.id === id)
  matrix.value = JSON.parse(JSON.stringify(d?.permissions || {}))
  matrixDirty.value = false
  const sr = selectedRole.value
  if (sr && sr.dept_id !== id) selectedRoleId.value = null
}

function selectRole(r) {
  if (selectedDeptId.value !== r.dept_id) selectDept(r.dept_id)
  selectedRoleId.value = r.id
}

async function loadData() {
  try {
    const [d, r] = await Promise.all([getDepartments(), getPermissionRoles()])
    departments.value = d.data || []
    roles.value = r.data || []
    if (selectedRoleId.value && !roles.value.some(x => x.id === selectedRoleId.value)) selectedRoleId.value = null
    if (!selectedDeptId.value && departments.value.length) {
      selectDept(departments.value[0].id)
    } else if (selectedDeptId.value) {
      const still = departments.value.find(x => x.id === selectedDeptId.value)
      if (!still && departments.value.length) selectDept(departments.value[0].id)
    }
  } catch (e) {
    ElMessage.error('加载部门权限数据失败')
  }
}

// ── 部门 ──
const deptDialog = reactive({ show: false, editing: null, form: { name: '' } })
function openDeptDialog(d) {
  deptDialog.editing = d
  deptDialog.form.name = d ? d.name : ''
  deptDialog.show = true
}
async function saveDept() {
  const name = deptDialog.form.name.trim()
  if (!name) { ElMessage.warning('请输入部门名称'); return }
  try {
    if (deptDialog.editing) await updateDepartment(deptDialog.editing.id, { name })
    else await createDepartment({ name })
    ElMessage.success('已保存')
    deptDialog.show = false
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function removeDept(id) {
  try {
    await deleteDepartment(id)
    ElMessage.success('已删除')
    selectedDeptId.value = null
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

// ── 角色（仅分组） ──
const roleDialog = reactive({ show: false, editing: null, form: { name: '', dept_id: null, desc: '' } })
function openRoleForDept(deptId) {
  selectDept(deptId)
  openRoleDialog(null)
}
function openRoleDialog(r) {
  roleDialog.editing = r
  roleDialog.form.name = r ? r.name : ''
  roleDialog.form.dept_id = r ? r.dept_id : (selectedDeptId.value || null)
  roleDialog.form.desc = r ? (r.desc || '') : ''
  roleDialog.show = true
}
async function saveRole() {
  const f = roleDialog.form
  if (!f.name.trim()) { ElMessage.warning('请输入角色名称'); return }
  if (!roleDialog.editing && !f.dept_id) { ElMessage.warning('请选择所属部门'); return }
  try {
    if (roleDialog.editing) {
      await updatePermissionRole(roleDialog.editing.id, { name: f.name.trim(), desc: f.desc.trim() })
      ElMessage.success('已更新')
    } else {
      await createPermissionRole({ name: f.name.trim(), dept_id: f.dept_id, desc: f.desc.trim() })
      ElMessage.success('已创建')
    }
    roleDialog.show = false
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}
async function removeRole(id) {
  try {
    await deletePermissionRole(id)
    ElMessage.success('已删除')
    selectedRoleId.value = null
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '删除失败')
  }
}

async function saveMatrix() {
  if (!selectedDept.value) return
  try {
    await updateDepartment(selectedDept.value.id, { permissions: matrix.value })
    ElMessage.success('权限矩阵已保存')
    matrixDirty.value = false
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

/** 把当前矩阵下发给本部门所有人的账号：先 dry_run 拿名单，确认后再下发。 */
async function applyToMembers() {
  const dept = selectedDept.value
  if (!dept) return
  try {
    // 用编辑器里当前这份（不一定已保存），这样可以先预览再决定要不要落库
    const preview = await applyDepartmentPermissions(dept.id, matrix.value, true)
    const info = preview.data || {}
    if (!info.affected) {
      ElMessage.info(`「${dept.name}」下没有可下发的账号（管理员和停用账号不在其中）`)
      return
    }
    const warn = info.customized
      ? `其中 ${info.customized} 人已单独配置过权限，将被覆盖。`
      : '其中没有已单独配置的账号，不会覆盖任何人的个性化设置。'
    try {
      await ElMessageBox.confirm(
        `将把当前矩阵下发给「${dept.name}」的 ${info.affected} 个账号。${warn}`,
        '确认下发', { type: 'warning', confirmButtonText: '下发', cancelButtonText: '取消' })
    } catch {
      return // 用户点了取消——不是错误，静默返回
    }
    const r = await applyDepartmentPermissions(dept.id, matrix.value, false)
    ElMessage.success(`已下发给 ${r.data.affected} 个账号`)
    await loadData()
    emit('saved')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '下发失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.rp-panel { display: flex; flex-direction: column; gap: 16px; }
.rp-body { display: flex; gap: 16px; align-items: flex-start; }
.rp-left { width: 300px; flex-shrink: 0; }
.rp-right { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 16px; }
.rp-nav { padding: 8px 0; max-height: 520px; overflow-y: auto; }
.rp-dept { margin-bottom: 2px; }
.rp-nav-item {
  position: relative;
  display: flex; align-items: center; gap: 6px;
  padding: 7px 12px; margin: 1px 6px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: var(--text);
}
.rp-nav-item:hover { background: #f2f3f5; }
.rp-nav-item.active { background: #e8f3ff; color: #1d6fd6; font-weight: 600; }
.rp-nav-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rp-nav-badge {
  font-size: 11px; color: var(--text-muted); background: #f2f3f5;
  border-radius: 10px; padding: 0 7px; line-height: 16px; flex-shrink: 0;
}
.rp-nav-ops {
  display: none; position: absolute; right: 8px; top: 50%;
  transform: translateY(-50%); align-items: center; flex-shrink: 0;
  background: inherit;
}
.rp-nav-item:hover .rp-nav-ops { display: flex; }
.rp-role-item {
  position: relative;
  display: flex; flex-direction: column; gap: 1px;
  padding: 5px 12px 6px 28px; margin: 1px 6px; border-radius: 6px; cursor: pointer;
}
.rp-role-item:hover { background: #f7f8fa; }
.rp-role-item.active { background: #e8f3ff; }
.rp-role-name { font-size: 13px; color: var(--text); }
.rp-role-item.active .rp-role-name { color: #1d6fd6; font-weight: 600; }
.rp-role-desc {
  font-size: 12px; color: var(--text-muted);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rp-role-ops {
  display: none; position: absolute; right: 8px; top: 50%;
  transform: translateY(-50%); align-items: center; flex-shrink: 0;
}
.rp-role-item:hover .rp-role-ops { display: flex; }
.rp-role-empty { padding: 3px 12px 6px 28px; font-size: 12px; color: #c0c4cc; }
.rp-desc { padding: 4px 0 12px; display: flex; flex-direction: column; gap: 14px; }
.rp-desc-hint { font-size: 13px; color: var(--text-muted); }
.rp-desc-role {
  background: #f7f8fa; border-radius: 8px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 6px;
}
.rp-desc-role-head { display: flex; align-items: center; gap: 8px; }
.rp-desc-role-name { font-size: 14px; font-weight: 700; color: var(--text); }
.rp-desc-role-desc { font-size: 13px; color: var(--text-secondary); }
.rp-desc-muted { font-size: 12px; color: var(--text-muted); }
.rp-desc-block { display: flex; flex-direction: column; gap: 4px; }
.rp-desc-title { font-size: 13px; font-weight: 600; color: var(--text); }
.rp-desc-text { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.rp-desc-tpl {
  display: flex; gap: 8px; font-size: 12px; padding: 5px 10px;
  background: #f7f8fa; border-radius: 6px;
}
.rp-desc-tpl-name { flex-shrink: 0; font-weight: 600; color: var(--text); min-width: 70px; }
.rp-desc-tpl-desc { color: var(--text-secondary); }
</style>
