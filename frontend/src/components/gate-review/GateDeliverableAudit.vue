<template>
  <div class="gda" v-loading="loading">
    <div class="gda-title">
      阶段门交付物审核
      <el-tag :type="allOk ? 'success' : 'danger'" size="small" style="margin-left:8px">{{ allOk ? '达标' : '未达标' }}</el-tag>
    </div>
    <div v-if="!loading && !items.length" class="gda-empty">该阶段暂无必需交付物标准，可直接发起</div>
    <div v-for="it in items" :key="it.name" class="gda-row">
      <span class="gda-icon" :class="it.ok ? 'ok' : 'no'">{{ it.ok ? '✓' : '✗' }}</span>
      <span class="gda-name">{{ it.name }}</span>
      <span class="gda-state" :class="it.ok ? 'ok' : 'no'">{{ it.state }}</span>
    </div>
    <div class="gda-summary" :class="{ bad: !allOk }">
      {{ doneCount }}/{{ items.length }} 项必需交付物已批准{{ allOk ? '，可继续' : '，需补齐' }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { getStandards, getDeliverables } from '../../api/index.js'

const props = defineProps({
  projectId: { type: Number, default: null },
  phaseId: { type: Number, default: null },
})
const emit = defineEmits(['change'])

const loading = ref(false)
const items = ref([])

const allOk = computed(() => items.value.every(i => i.ok))
const doneCount = computed(() => items.value.filter(i => i.ok).length)

const STATE_LABEL = { approved: '已批准', submitted: '已提交', reviewed: '已评审', rejected: '已驳回', not_submitted: '未提交' }

async function load() {
  if (!props.projectId || !props.phaseId) { items.value = []; emit('change', true); return }
  loading.value = true
  try {
    const [s, d] = await Promise.all([getStandards(), getDeliverables(props.projectId)])
    const stds = (s.data || []).filter(x => x.phase_id === props.phaseId && x.is_active !== false && x.required)
    const dels = (d.data || []).filter(x => x.phase_id === props.phaseId)
    items.value = stds.map(st => {
      const dl = dels.find(x => x.name && (st.name.includes(x.name) || x.name.includes(st.name)))
      const ok = !!(dl && dl.status === 'approved')
      return { name: st.name, ok, state: ok ? '已批准' : (dl ? (STATE_LABEL[dl.status] || dl.status) : '缺失') }
    })
    emit('change', items.value.every(i => i.ok))
  } finally { loading.value = false }
}
watch(() => [props.projectId, props.phaseId], load, { immediate: true })
</script>

<style scoped>
.gda { border: 1px solid #e4e7ed; border-radius: 6px; padding: 8px 10px; max-height: 200px; overflow-y: auto; }
.gda-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.gda-empty { font-size: 12px; color: var(--text-muted); padding: 4px 0; }
.gda-row { display: flex; align-items: center; gap: 6px; padding: 3px 0; font-size: 12px; }
.gda-icon { width: 14px; text-align: center; font-weight: 700; }
.gda-icon.ok { color: #67c23a; }
.gda-icon.no { color: #f56c6c; }
.gda-name { flex: 1; }
.gda-state.ok { color: #67c23a; }
.gda-state.no { color: #f56c6c; }
.gda-summary { margin-top: 6px; font-size: 12px; color: #67c23a; border-top: 1px dashed #e4e7ed; padding-top: 6px; }
.gda-summary.bad { color: #f56c6c; }
</style>
