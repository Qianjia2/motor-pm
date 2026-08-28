<template>
  <div class="phase-stepper">
    <div class="steps-track">
      <div
        v-for="(pg, idx) in phaseGates"
        :key="pg.phase_id"
        class="step-node"
        :class="stepClass(pg)"
        @click="$emit('select', pg)"
      >
        <div class="step-circle">
          <el-icon v-if="pg.status === 'completed'" :size="16"><Check /></el-icon>
          <el-icon v-else-if="pg.status === 'in_progress'" :size="16"><Loading /></el-icon>
          <span v-else>{{ idx + 1 }}</span>
        </div>
        <div class="step-label">
          <div class="step-name">{{ pg.phase?.name || 'Phase '+pg.phase_id }}</div>
          <div class="step-status">{{ statusText(pg) }}</div>
          <div v-if="pg.gate" class="step-gate">
            <el-tag :type="gateTagType(pg)" size="small" effect="plain">
              {{ pg.gate.code }} {{ pg.gate.name }}
            </el-tag>
          </div>
        </div>
        <div v-if="idx < phaseGates.length - 1" class="step-connector" :class="connectorClass(pg)"></div>
      </div>
    </div>

    <!-- 选中阶段详情 -->
    <el-dialog
      v-model="showDetail"
      :title="selectedPhase?.phase?.name + ' - 阶段详情'"
      width="560px"
    >
      <PhaseGatePanel
        v-if="selectedPhase"
        :phase-gate="selectedPhase"
        :project-id="projectId"
        :members="members"
        @save="handleSave"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Check, Loading } from '@element-plus/icons-vue'
import PhaseGatePanel from '../project/PhaseGatePanel.vue'

const props = defineProps({
  phaseGates: { type: Array, default: () => [] },
  projectId: { type: [Number, String], default: null },
  members: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'update'])

const showDetail = ref(false)
const selectedPhase = ref(null)

function stepClass(pg) {
  if (pg.status === 'completed') return 'is-completed'
  if (pg.status === 'in_progress') return 'is-active'
  return 'is-pending'
}
function connectorClass(pg) {
  return pg.status === 'completed' ? 'is-done' : 'is-pending'
}
function statusText(pg) {
  const map = { not_started: '未开始', in_progress: '进行中', completed: '已完成', skipped: '已跳过' }
  return map[pg.status] || pg.status
}
function gateTagType(pg) {
  if (pg.gate_status === 'passed') return 'success'
  if (pg.gate_status === 'failed') return 'danger'
  return 'info'
}

function handleSave(data) {
  emit('update', { phase_id: selectedPhase.value.phase_id, ...data })
  showDetail.value = false
}

defineExpose({
  openDetail(pg) {
    selectedPhase.value = pg
    showDetail.value = true
  }
})
</script>

<style scoped>
.phase-stepper {
  padding: 20px 0;
  overflow-x: auto;
}
.steps-track {
  display: flex;
  align-items: flex-start;
  min-width: 900px;
}
.step-node {
  display: flex;
  flex-direction: column;
  align-items: center;
  position: relative;
  flex: 1;
  cursor: pointer;
  min-width: 120px;
}
.step-circle {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  z-index: 1;
  transition: all 0.3s;
}
.is-completed .step-circle {
  background: #67c23a;
  color: #fff;
}
.is-active .step-circle {
  background: #409eff;
  color: #fff;
  box-shadow: 0 0 0 4px rgba(64,158,255,0.2);
}
.is-pending .step-circle {
  background: #e4e7ed;
  color: #909399;
}
.step-label {
  text-align: center;
  margin-top: 10px;
}
.step-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  margin-bottom: 2px;
}
.step-status {
  font-size: 11px;
  color: #909399;
}
.step-gate {
  margin-top: 4px;
}
.step-connector {
  position: absolute;
  top: 18px;
  left: 60%;
  width: 80%;
  height: 2px;
}
.step-connector.is-done {
  background: #67c23a;
}
.step-connector.is-pending {
  background: #e4e7ed;
}
</style>
