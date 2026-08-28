<template>
  <div class="phase-gate-review-page">
    <div class="page-header">
      <h1>阶段门评审</h1>
      <span class="head-sub">交付物标准 · 任务放行 · 签核审批 · 历史对比</span>
      <el-radio-group v-model="projectType" size="small" style="margin-left:auto">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="hardware">系统集成</el-radio-button>
        <el-radio-button value="software">软件开发</el-radio-button>
      </el-radio-group>
    </div>
    <el-tabs v-model="activeTab" class="pgr-tabs">
      <el-tab-pane label="交付物标准与检查" name="standards">
        <GateDeliverableStandardTab :phases="phases" :projects="projects" :is-admin="auth.isAdmin" :project-type="projectType" />
      </el-tab-pane>
      <el-tab-pane label="任务跟踪与放行" name="tasks">
        <GateTaskTrackingTab :phases="phases" :projects="projects" :members="members" />
      </el-tab-pane>
      <el-tab-pane label="阶段门签核审批" name="signoffs">
        <GateSignoffTab :projects="projects" :members="members" :current-member-id="auth.currentMemberId" :is-admin="auth.isAdmin" />
      </el-tab-pane>
      <el-tab-pane label="历史对比" name="history">
        <GateHistoryTab :projects="projects" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { getPhases, getGates, getProjects, getTeamMembers } from '../api/index.js'
import GateDeliverableStandardTab from '../components/gate-review/GateDeliverableStandardTab.vue'
import GateTaskTrackingTab from '../components/gate-review/GateTaskTrackingTab.vue'
import GateSignoffTab from '../components/gate-review/GateSignoffTab.vue'
import GateHistoryTab from '../components/gate-review/GateHistoryTab.vue'

const auth = useAuthStore()
const route = useRoute()
const activeTab = ref(route.query.tab || 'standards')
const projectType = ref('all')
const phases = ref([])
const gates = ref([])
const projects = ref([])
const members = ref([])

async function loadPhases() {
  const params = projectType.value === 'all' ? undefined : { project_type: projectType.value }
  phases.value = (await getPhases(params)).data || []
}

onMounted(async () => {
  try { await loadPhases() } catch (e) {}
  try { gates.value = (await getGates()).data || [] } catch (e) {}
  try { const pr = await getProjects(); projects.value = pr.data?.data || pr.data || [] } catch (e) {}
  try { members.value = (await getTeamMembers()).data || [] } catch (e) {}
})

// 切换项目类型时重载阶段,标准 tab 内部监听 project-type 同步重载标准
watch(projectType, () => { loadPhases() })
</script>

<style scoped>
.phase-gate-review-page { padding: 4px 0; }
.page-header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.page-header h1 { font-size: 18px; margin: 0; }
.head-sub { font-size: 12px; color: var(--text-muted); }
.pgr-tabs :deep(.el-tabs__item) { font-size: 14px; }
</style>
