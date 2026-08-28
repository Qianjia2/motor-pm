import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getPhases, getGates, getLines, getRoles, getDocTypes } from '../api/index.js'

export const useLookupStore = defineStore('lookup', () => {
  const phases = ref([])
  const gates = ref([])
  const lines = ref([])
  const roles = ref([])
  const docTypeGroups = ref([])
  const loaded = ref(false)
  const loading = ref(false)

  async function fetchAll() {
    if (loaded.value) return
    if (loading.value) return
    loading.value = true
    try {
      const [p, g, l, r, d] = await Promise.all([
        getPhases(), getGates(), getLines(), getRoles(), getDocTypes()
      ])
      phases.value = p.data
      gates.value = g.data
      lines.value = l.data
      roles.value = r.data
      docTypeGroups.value = Array.isArray(d.data) ? d.data : (d.data?.groups || [])
      loaded.value = true
    } catch (e) {
      console.error('Failed to load lookups:', e)
    } finally {
      loading.value = false
    }
  }

  const phaseById = computed(() => {
    const map = {}
    phases.value.forEach(p => { map[p.id] = p })
    return map
  })

  const lineById = computed(() => {
    const map = {}
    lines.value.forEach(l => { map[l.id] = l })
    return map
  })

  const roleById = computed(() => {
    const map = {}
    roles.value.forEach(r => { map[r.id] = r })
    return map
  })

  const docTypeLabel = computed(() => {
    const map = {}
    docTypeGroups.value.forEach(g => {
      g.types.forEach(t => { map[t.value] = t.label })
    })
    return map
  })

  return { phases, gates, lines, roles, docTypeGroups, loaded, loading, phaseById, lineById, roleById, docTypeLabel, fetchAll }
})
