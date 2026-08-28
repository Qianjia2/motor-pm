import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

// ── Request: auto-attach JWT access token ──
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response: 401 → auto refresh → retry once ──
let isRefreshing = false
let refreshQueue = []

api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise(resolve => {
          refreshQueue.push(token => {
            original.headers.Authorization = `Bearer ${token}`
            original._retry = true
            resolve(api(original))
          })
        })
      }
      original._retry = true
      isRefreshing = true
      try {
        const refreshToken = localStorage.getItem('refresh_token')
        if (!refreshToken) throw new Error('no refresh token')
        const res = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
        const newToken = res.data.access_token
        localStorage.setItem('access_token', newToken)
        refreshQueue.forEach(cb => cb(newToken))
        refreshQueue = []
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch (e) {
        // 刷新失败：唤醒所有等待中的队列请求，避免永久挂起
        const queue = refreshQueue
        refreshQueue = []
        queue.forEach(cb => cb(null))
        localStorage.clear()
        if (window.location.pathname !== '/login') {
          window.location.href = '/login'
        }
        return Promise.reject(err)
      } finally {
        isRefreshing = false
      }
    }
    return Promise.reject(err)
  }
)

// ── Projects ──────────────────────────────
export const getProjects = (params) => api.get('/projects', { params })
export const getProject = (id) => api.get(`/projects/${id}`)
export const createProject = (data) => api.post('/projects', data)
export const updateProject = (id, data) => api.put(`/projects/${id}`, data)
export const deleteProject = (id) => api.delete(`/projects/${id}`)
export const copyProject = (id, data) => api.post(`/projects/${id}/copy`, data)
export const getProjectStats = (id) => api.get(`/projects/${id}/stats`)
export const searchGlobal = (q) => api.get('/projects/search', { params: { q } })
export const getResourceMatrix = () => api.get('/resource-matrix')

// ── Phase Gates ───────────────────────────
export const getPhaseGates = (pid) => api.get(`/projects/${pid}/phase-gates`)
export const updatePhaseGate = (id, data) => api.put(`/phase-gates/${id}`, data)
export const getActionItems = (pgId) => api.get(`/phase-gates/${pgId}/action-items`)
export const createActionItem = (pgId, data) => api.post(`/phase-gates/${pgId}/action-items`, data)
export const updateActionItem = (id, data) => api.put(`/action-items/${id}`, data)
export const deleteActionItem = (id) => api.delete(`/action-items/${id}`)

// ── Milestones ────────────────────────────
export const getMilestones = (pid, params) => api.get(`/projects/${pid}/milestones`, { params })
export const createMilestone = (pid, data) => api.post(`/projects/${pid}/milestones`, data)
export const updateMilestone = (id, data) => api.put(`/milestones/${id}`, data)
export const deleteMilestone = (id) => api.delete(`/milestones/${id}`)
export const getAllMilestones = (params) => api.get('/milestones/all', { params })

// ── Weekly Reports ────────────────────────
export const getReports = (pid, params) => api.get(`/projects/${pid}/reports`, { params })
export const getLatestReport = (pid) => api.get(`/projects/${pid}/reports/latest`)
export const createReport = (pid, data) => api.post(`/projects/${pid}/reports`, data)
export const updateReport = (id, data) => api.put(`/reports/${id}`, data)
export const getReport = (id) => api.get(`/reports/${id}`)

// ── Risks & Issues ────────────────────────
export const getRisks = (pid, params) => api.get(`/projects/${pid}/risks`, { params })
export const createRisk = (pid, data) => api.post(`/projects/${pid}/risks`, data)
export const updateRisk = (id, data) => api.put(`/risks/${id}`, data)
export const deleteRisk = (id) => api.delete(`/risks/${id}`)
export const closeRisk = (id, formData) => api.post(`/risks/${id}/close`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})

// ── Changes ───────────────────────────────
export const getChanges = (pid) => api.get(`/projects/${pid}/changes`)
export const createChange = (pid, data) => api.post(`/projects/${pid}/changes`, data)
export const updateChange = (id, data) => api.put(`/changes/${id}`, data)
export const deleteChange = (id) => api.delete(`/changes/${id}`)
export const approveChangeSignoff = (id, data) => api.post(`/changes/signoffs/${id}/approve`, data)
export const rejectChangeSignoff = (id, data) => api.post(`/changes/signoffs/${id}/reject`, data)

// ── Team ──────────────────────────────────
export const getTeamMembers = (params) => api.get('/team-members', { params })
export const createTeamMember = (data) => api.post('/team-members', data)
export const updateTeamMember = (id, data) => api.put(`/team-members/${id}`, data)
export const getProjectMembers = (pid) => api.get(`/projects/${pid}/members`)
export const addProjectMember = (pid, data) => api.post(`/projects/${pid}/members`, data)
export const updateProjectMember = (id, data) => api.put(`/project-members/${id}`, data)
export const removeProjectMember = (id) => api.delete(`/project-members/${id}`)

// ── Dashboard ─────────────────────────────
export const getDashboard = () => api.get('/dashboard')
export const getDashboardAlerts = () => api.get('/dashboard/alerts')
export const getPendingReports = () => api.get('/dashboard/pending-reports')

// ── My Work ───────────────────────────────
export const getMyWork = () => api.get('/my-work')

// ── Deliverables ──────────────────────────
export const getDeliverables = (pid, params) => api.get(`/projects/${pid}/deliverables`, { params })
export const createDeliverable = (pid, data) => api.post(`/projects/${pid}/deliverables`, data)
export const updateDeliverable = (id, data) => api.put(`/deliverables/${id}`, data)
export const deleteDeliverable = (id) => api.delete(`/deliverables/${id}`)
export const deleteDeliverableFile = (id) => api.delete(`/deliverables/${id}/file`)

// ── Documents ─────────────────────────────
export const getDocuments = (pid, params) => api.get(`/projects/${pid}/docs`, { params })
export const createDocument = (pid, formData) => api.post(`/projects/${pid}/docs`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const updateDocument = (id, data) => api.put(`/docs/${id}`, data)
export const deleteDocument = (id) => api.delete(`/docs/${id}`)
export const deprecateDocument = (id) => api.post(`/docs/${id}/deprecate`)
export const replaceDocument = (id, formData) => api.post(`/docs/${id}/replace`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})

// ── Clients ───────────────────────────────
export const getClients = (params) => api.get('/clients', { params })
export const createClient = (data) => api.post('/clients', data)
export const updateClient = (id, data) => api.put(`/clients/${id}`, data)
export const deleteClient = (id) => api.delete(`/clients/${id}`)

// ── Lookups ───────────────────────────────
export const getPhases = (params) => api.get('/lookups/phases', { params })
export const getGates = () => api.get('/lookups/gates')
export const getLines = () => api.get('/lookups/technical-lines')
export const getRoles = () => api.get('/lookups/roles')
export const getDocTypes = () => api.get('/lookups/doc-types')

// ── Audit Logs ────────────────────────────
export const getAuditLogs = (params) => api.get('/audit-logs', { params })

// ── Export ────────────────────────────────
export const exportProjects = () => api.get('/export/projects', { responseType: 'blob' })
export const exportReports = (pid) => api.get(`/export/projects/${pid}/reports`, { responseType: 'blob' })
export const exportRisks = (pid) => api.get(`/export/projects/${pid}/risks`, { responseType: 'blob' })

// ── Files ─────────────────────────────────
export const uploadFile = (formData) => api.post('/files/upload', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const getStorageStats = () => api.get('/files/storage-stats')

// ── Departments & Permission Roles ────────
export const getDepartments = () => api.get('/departments')
export const createDepartment = (data) => api.post('/departments', data)
export const updateDepartment = (id, data) => api.put(`/departments/${id}`, data)
export const deleteDepartment = (id) => api.delete(`/departments/${id}`)
export const getPermissionRoles = () => api.get('/auth/permission-roles')
export const createPermissionRole = (data) => api.post('/auth/permission-roles', data)
export const updatePermissionRole = (id, data) => api.put(`/auth/permission-roles/${id}`, data)
export const deletePermissionRole = (id) => api.delete(`/auth/permission-roles/${id}`)

export default api

// ── 阶段门评审 ────────────────────────────
export const getStandards = (params) => api.get('/gate-deliverable-standards', { params })
export const createStandard = (data) => api.post('/gate-deliverable-standards', data)
export const updateStandard = (id, data) => api.put(`/gate-deliverable-standards/${id}`, data)
export const deleteStandard = (id) => api.delete(`/gate-deliverable-standards/${id}`)
export const uploadStandardTemplate = (id, formData) => api.post(`/gate-deliverable-standards/${id}/template`, formData)
export const deleteStandardTemplate = (id) => api.delete(`/gate-deliverable-standards/${id}/template`)
export const getChecklist = (params) => api.get('/gate-reviews/checklist', { params })
export const getCrossProjectActionItems = (params) => api.get('/gate-reviews/action-items', { params })
export const initiateSignoff = (pgId, data) => api.post(`/gate-reviews/${pgId}/initiate-signoff`, data)
export const getMySignoffs = () => api.get('/gate-reviews/my-signoffs')
export const getSignoffs = (params) => api.get('/gate-reviews/signoffs', { params })
export const approveSignoff = (id, data) => api.post(`/gate-reviews/signoffs/${id}/approve`, data)
export const rejectSignoff = (id, data) => api.post(`/gate-reviews/signoffs/${id}/reject`, data)
export const deleteSignoff = (id) => api.delete(`/gate-reviews/signoffs/${id}`)
export const getGateHistory = (params) => api.get('/gate-reviews/history', { params })
