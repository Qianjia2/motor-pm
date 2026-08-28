import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getProjects, getProject, createProject, updateProject, deleteProject, copyProject, getProjectStats,
} from '../api/index.js'

export const useProjectStore = defineStore('project', () => {
  const list = ref([])
  const current = ref(null)
  const total = ref(0)
  const loading = ref(false)
  const filters = ref({ page: 1, page_size: 20 })

  async function fetchList(params = {}) {
    loading.value = true
    filters.value = { ...filters.value, ...params }
    try {
      const res = await getProjects(filters.value)
      list.value = res.data.data || []
      total.value = res.data.total || 0
    } finally {
      loading.value = false
    }
  }

  async function fetchDetail(id) {
    const res = await getProject(id)
    current.value = res.data
    return current.value
  }

  async function create(data) {
    const res = await createProject(data)
    await fetchList()
    return res.data
  }

  async function update(id, data) {
    const res = await updateProject(id, data)
    if (current.value?.id === id) current.value = res.data
    return res.data
  }

  async function softDelete(id) {
    await deleteProject(id)
    if (current.value?.id === id) current.value = null
    await fetchList()
  }

  async function copy(id, newCode) {
    const res = await copyProject(id, { new_code: newCode })
    await fetchList()
    return res.data
  }

  const blockedProjects = computed(() => list.value.filter(p => p.overall_status === 'blocked'))
  const atRiskProjects = computed(() => list.value.filter(p => p.overall_status === 'at_risk'))

  return { list, current, total, loading, filters, fetchList, fetchDetail, create, update, softDelete, copy, blockedProjects, atRiskProjects }
})
