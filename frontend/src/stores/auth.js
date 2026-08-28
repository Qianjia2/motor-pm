import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../api/index.js'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref(localStorage.getItem('access_token') || '')
  const refreshToken = ref(localStorage.getItem('refresh_token') || '')
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const myPermissions = ref(JSON.parse(localStorage.getItem('my_permissions') || 'null') || {})
const myProfile = ref(JSON.parse(localStorage.getItem('my_profile') || 'null') || {})

  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const isPM = computed(() => user.value?.role === 'admin' || user.value?.role === 'pm')
  const username = computed(() => user.value?.username || '')
  const currentMemberId = computed(() => user.value?.member_id)
  const currentMemberName = computed(() => myProfile.value?.name || user.value?.name || username.value)

  // 账号(拼音)→中文姓名映射,全平台显示中文名
  const displayNames = ref({})
  let nameMapPromise = null
  async function ensureNameMap() {
    if (Object.keys(displayNames.value).length || nameMapPromise) return
    nameMapPromise = (async () => {
      try {
        const res = await api.get('/auth/name-map')
        displayNames.value = res.data || {}
      } catch (e) { /* 映射加载失败时回退显示账号 */ }
    })()
    await nameMapPromise
    nameMapPromise = null
  }
  function displayName(u) {
    if (!u) return ''
    return displayNames.value[u] || u
  }

  const LEVEL_RANK = { none: 0, view: 1, edit: 2, admin: 3 }
  // 新格式：{"projects": {"view":true,...}}；旧格式兼容：字符串级别
  function hasPermission(module, action = 'view') {
    const perms = (myPermissions.value && myPermissions.value.permissions) || myPermissions.value || {}
    const v = perms[module]
    if (v && typeof v === 'object') return v[action] === true
    // 旧 localStorage 字符串格式（部署瞬间兼容）
    const userLevel = v || 'none'
    if (action === 'view') return (LEVEL_RANK[userLevel] || 0) >= 1
    if (action === 'export') return (LEVEL_RANK[userLevel] || 0) >= 1
    if (action === 'create') return (LEVEL_RANK[userLevel] || 0) >= 2
    if (action === 'delete') return (LEVEL_RANK[userLevel] || 0) >= 2
    return (LEVEL_RANK[userLevel] || 0) >= 2
  }
  function canView(module) { return hasPermission(module, 'view') }
  function canEdit(module) { return hasPermission(module, 'edit') }
  function canCreate(module) { return hasPermission(module, 'create') }
  function canDelete(module) { return hasPermission(module, 'delete') }
  function canExport(module) { return hasPermission(module, 'export') }

  async function login(username, password) {
    const res = await api.post('/auth/login', { username, password })
    const { access_token, refresh_token, user: u } = res.data
    accessToken.value = access_token
    refreshToken.value = refresh_token
    user.value = u
    localStorage.setItem('access_token', access_token)
    localStorage.setItem('refresh_token', refresh_token)
    localStorage.setItem('user', JSON.stringify(u))
    try { await Promise.all([fetchMyPermissions(), fetchMyProfile(), ensureNameMap()]) } catch(e) {}
    return res.data
  }

  async function fetchMyPermissions() {
    try {
      const res = await api.get('/auth/my-permissions')
      myPermissions.value = res.data || {}
      localStorage.setItem('my_permissions', JSON.stringify(res.data || {}))
    } catch(e) { myPermissions.value = {} }
  }

  async function fetchMyProfile() {
    try {
      const res = await api.get('/auth/me')
      const mid = res.data?.user?.member_id || user.value?.member_id
      if (mid) {
        const r2 = await api.get('/team-members')
        const members = r2.data || []
        const me = members.find(m => m.id === mid)
        if (me) {
          myProfile.value = { name: me.name, department: me.department, title: me.title }
          localStorage.setItem('my_profile', JSON.stringify(myProfile.value))
          return
        }
      }
      // 账号未关联成员档案：清空残留的旧用户资料，避免右上角张冠李戴
      myProfile.value = {}
      localStorage.removeItem('my_profile')
    } catch(e) {}
  }

  async function register(username, password, memberName) {
    const res = await api.post('/auth/register', { username, password, member_name: memberName })
    return res.data
  }

  async function logout() {
    try { await api.post('/auth/logout') } catch (e) { /* ignore */ }
    accessToken.value = ''
    refreshToken.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user')
    localStorage.removeItem('my_profile')
    localStorage.removeItem('my_permissions')
  }

  async function fetchMe() {
    try {
      const res = await api.get('/auth/me')
      user.value = res.data.user
      localStorage.setItem('user', JSON.stringify(res.data.user))
    } catch (e) {
      accessToken.value = ''
      refreshToken.value = ''
      user.value = null
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
    }
  }

  return { accessToken, refreshToken, user, myPermissions, myProfile, isLoggedIn, isAdmin, isPM, username, currentMemberId, currentMemberName, displayName, ensureNameMap, hasPermission, canView, canEdit, canCreate, canDelete, canExport, login, register, logout, fetchMe, fetchMyPermissions, fetchMyProfile }
})
