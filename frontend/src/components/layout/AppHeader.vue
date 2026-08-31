<template>
  <div class="topbar-inner">
    <div class="topbar-left">
      <span class="topbar-greeting">{{ greeting }}</span>
    </div>
    <div class="topbar-right">
      <!-- Search -->
      <div class="global-search">
        <el-input v-model="searchQuery" placeholder="搜索项目、人员、文档..." size="small" style="width:220px"
          :prefix-icon="Search" clearable @focus="openSearch" @keyup.enter="doSearch" />
      </div>

      <!-- Notification bell -->
      <el-badge :value="unreadCount" :hidden="!unreadCount" :max="99">
        <el-button link @click="showNotices = true">
          <el-icon :size="20"><Bell /></el-icon>
        </el-button>
      </el-badge>

      <el-divider direction="vertical" />

      <!-- User -->
      <el-dropdown v-if="auth.isLoggedIn" @command="handleCommand" trigger="click">
        <span class="user-trigger">
          <el-avatar :size="32" :icon="UserFilled" style="background:var(--primary)" />
          <span class="user-name">{{ auth.currentMemberName || auth.username }}</span>
          <el-tag size="small" :type="auth.isAdmin ? 'danger' : auth.user?.role === 'biz' ? 'warning' : auth.isPM ? 'warning' : ''" effect="plain">
            {{ auth.isAdmin ? '管理员' : auth.user?.role === 'biz' ? '商务经理' : auth.isPM ? 'PM' : '成员' }}
          </el-tag>
        </span>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">
              <el-icon><User /></el-icon> 个人信息
            </el-dropdown-item>
            <el-dropdown-item command="chgpwd">
              <el-icon><Lock /></el-icon> 修改密码
            </el-dropdown-item>
            <el-dropdown-item v-if="auth.isAdmin" command="settings">
              <el-icon><Setting /></el-icon> 系统设置
            </el-dropdown-item>
            <el-dropdown-item command="mywork">
              <el-icon><HomeFilled /></el-icon> 我的工作台
            </el-dropdown-item>
            <el-dropdown-item command="logout" divided>
              <el-icon><SwitchButton /></el-icon> 退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

    <!-- Profile Dialog -->
    <el-dialog v-model="showProfile" title="个人信息" width="450px">
      <div style="text-align:center;margin-bottom:16px">
        <el-avatar :size="64" :icon="UserFilled" style="background:var(--primary);margin-bottom:8px" />
        <div style="font-size:18px;font-weight:600">{{ auth.myProfile?.name || auth.username }}</div>
        <div v-if="auth.myProfile?.department" style="font-size:13px;color:var(--text-muted)">{{ auth.myProfile.department }} {{ auth.myProfile.title }}</div>
        <div style="margin-top:8px">
          <el-tag size="small" :type="auth.isAdmin?'danger':'info'">{{ auth.isAdmin?'管理员':auth.user?.role==='biz'?'商务经理':auth.isPM?'PM':auth.username }}</el-tag>
        </div>
      </div>
      <div v-if="myPermList.length">
        <div style="font-size:14px;font-weight:600;margin-bottom:6px">模块权限</div>
        <el-table :data="myPermList" size="small" stripe>
          <el-table-column prop="module" label="模块" />
          <el-table-column label="权限" min-width="140">
            <template #default="{row}">
              <template v-if="row.actions.length">
                <el-tag v-for="a in row.actions" :key="a.value" size="small" :type="a.value==='delete'?'danger':a.value==='create'||a.value==='edit'?'warning':''" style="margin-right:4px">{{ a.label }}</el-tag>
              </template>
              <span v-else style="color:var(--text-muted)">无</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div style="text-align:center;margin-top:16px">
        <el-button size="small" @click="openPwd">修改密码</el-button>
      </div>
    </el-dialog>

    <!-- 修改密码 Dialog -->
    <el-dialog v-model="showPwd" title="修改密码" width="420px" :close-on-click-modal="false">
      <el-form label-width="90px" @submit.prevent>
        <el-form-item label="原密码" required>
          <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入当前密码" />
        </el-form-item>
        <el-form-item label="新密码" required>
          <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少3位" />
        </el-form-item>
        <el-form-item label="确认新密码" required>
          <el-input v-model="pwdConfirm" type="password" show-password placeholder="再次输入新密码" @keyup.enter="doChangePwd" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showPwd = false">取消</el-button>
        <el-button type="primary" :loading="pwdLoading" @click="doChangePwd">确认修改</el-button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth.js'
import { ElMessage } from 'element-plus'
import api from '../../api/index.js'
import { UserFilled, Bell, Search, SwitchButton, User, HomeFilled, Setting, Lock } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const searchQuery = ref('')
const showNotices = ref(false)
const unreadCount = ref(0)

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 9) return '早上好'
  if (h < 12) return '上午好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const showProfile = ref(false)
function openProfile() {
  loadMyPerms()
  showProfile.value = true
}
const myPermList = ref([])
async function loadMyPerms() {
  try {
    const r = await api.get('/auth/my-permissions')
    const perms = r.data?.permissions || {}
    const labels = r.data?.labels || {}
    const actionLabels = r.data?.action_labels || { view: '查看', create: '新建', edit: '编辑', delete: '删除', export: '导出' }
    myPermList.value = Object.entries(perms)
      .map(([k, v]) => ({
        module: labels[k] || k,
        actions: (v && typeof v === 'object')
          ? Object.entries(v).filter(([, on]) => on).map(([value]) => ({ value, label: actionLabels[value] || value }))
          : [],
      }))
      .filter(item => item.actions.length || true)
  } catch(e) {}
}

function handleCommand(cmd) {
  if (cmd === 'logout') {
    auth.logout().then(() => router.push('/login'))
  } else if (cmd === 'mywork') {
    router.push('/my-work')
  } else if (cmd === 'profile') {
    openProfile()
  } else if (cmd === 'chgpwd') {
    openPwd()
  } else if (cmd === 'settings') {
    router.push('/settings')
  }
}

const showPwd = ref(false)
const pwdLoading = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '' })
const pwdConfirm = ref('')

function openPwd() {
  pwdForm.old_password = ''
  pwdForm.new_password = ''
  pwdConfirm.value = ''
  showPwd.value = true
}

async function doChangePwd() {
  if (!pwdForm.old_password) { ElMessage.warning('请输入原密码'); return }
  if (pwdForm.new_password.length < 3) { ElMessage.warning('新密码至少3位'); return }
  if (pwdForm.new_password !== pwdConfirm.value) { ElMessage.warning('两次输入的新密码不一致'); return }
  pwdLoading.value = true
  try {
    await api.put('/auth/password', { old_password: pwdForm.old_password, new_password: pwdForm.new_password })
    ElMessage.success('密码已修改')
    showPwd.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '修改失败')
  } finally { pwdLoading.value = false }
}

const emit = defineEmits(['openSearch'])

function openSearch() {
  emit('openSearch')
}

function doSearch() {
  if (searchQuery.value.trim()) {
    router.push({ path: '/projects', query: { q: searchQuery.value.trim() } })
  }
}
</script>

<style scoped>
.topbar-inner {
  display:flex; justify-content:space-between; align-items:center;
  height:100%; width:100%;
}
.topbar-left { display:flex; align-items:center; gap:16px; }
.topbar-greeting { font-size:14px; color:var(--text-secondary); font-weight:500; }
.topbar-right { display:flex; align-items:center; gap:12px; }

.user-trigger {
  display:flex; align-items:center; gap:8px; cursor:pointer;
  padding:4px 8px; border-radius:6px; transition:background .15s;
}
.user-trigger:hover { background:var(--bg); }
.user-name { font-size:13px; color:var(--text); font-weight:500; }
</style>
