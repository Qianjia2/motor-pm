<template>
  <div class="tree-container">
    <!-- SVG 树状图 -->
    <svg :width="svgWidth" :height="svgHeight" style="font-family: 'Microsoft YaHei', sans-serif">
      <!-- 背景网格线 -->
      <defs>
        <filter id="shadow">
          <feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.15" />
        </filter>
        <marker id="arrow-green" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#67c23a" />
        </marker>
        <marker id="arrow-blue" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#409eff" />
        </marker>
        <marker id="arrow-gray" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <path d="M0,0 L8,3 L0,6 Z" fill="#dcdfe6" />
        </marker>
      </defs>

      <!-- 主干连接线 -->
      <line :x1="getPhaseX(0)" :y1="centerY" :x2="getPhaseX(5) + phaseW" :y2="centerY"
            stroke="#c0c4cc" stroke-width="3" stroke-dasharray="8,4" />

      <!-- 阶段节点 -->
      <g v-for="(pg, pIdx) in phaseGates" :key="pg.phase_id">
        <rect :x="getPhaseX(pIdx)" :y="centerY - 22" :width="phaseW" :height="44" rx="8"
              :fill="phaseColor(pg)" :filter="'url(#shadow)'" stroke="#fff" stroke-width="2" />

        <text :x="getPhaseX(pIdx) + phaseW / 2" :y="centerY - 4"
              text-anchor="middle" :fill="phaseTextColor(pg)" font-size="12" font-weight="600">
          {{ pg.phase?.name || 'Phase ' + pg.phase_id }}
        </text>
        <text :x="getPhaseX(pIdx) + phaseW / 2" :y="centerY + 12"
              text-anchor="middle" :fill="phaseTextColor(pg)" font-size="10">
          {{ phaseStatusText(pg) }}
        </text>

        <!-- 阶段间箭头 -->
        <line v-if="pIdx < 5"
              :x1="getPhaseX(pIdx) + phaseW" :y1="centerY"
              :x2="getPhaseX(pIdx + 1)" :y2="centerY"
              :stroke="pg.status === 'completed' ? '#67c23a' : pg.status === 'in_progress' ? '#409eff' : '#dcdfe6'"
              stroke-width="2"
              :marker-end="'url(#arrow-' + (pg.status === 'completed' ? 'green' : pg.status === 'in_progress' ? 'blue' : 'gray') + ')'" />

        <!-- 门径标签 -->
        <rect v-if="pg.gate" :x="getPhaseX(pIdx) + phaseW - 45" :y="centerY - 36" :width="40" :height="16" rx="3"
              :fill="pg.gate_status === 'passed' ? '#e1f3d8' : '#f0f0f0'" stroke="#ccc" stroke-width="0.5" />
        <text v-if="pg.gate" :x="getPhaseX(pIdx) + phaseW - 25" :y="centerY - 25"
              text-anchor="middle" font-size="9"
              :fill="pg.gate_status === 'passed' ? '#67c23a' : '#909399'">
          {{ pg.gate.code }}
        </text>

        <!-- 技术线分支 -->
        <line v-for="(line, lIdx) in lines" :key="'br' + pIdx + '-' + lIdx"
              :x1="getPhaseX(pIdx) + phaseW / 2" :y1="centerY + 22"
              :x2="getPhaseX(pIdx) + phaseW / 2" :y2="lineTop + lIdx * lineH"
              stroke="#e4e7ed" stroke-width="1" />

        <!-- 技术线叶子节点 -->
        <rect v-for="(line, lIdx) in lines" :key="'leaf' + pIdx + '-' + lIdx"
              :x="getLeafX(pIdx, lIdx)" :y="lineTop + lIdx * lineH - 12"
              :width="leafW" :height="24" rx="4"
              :fill="leafColor(pIdx, line.id)" stroke="#fff" stroke-width="1"
              :filter="'url(#shadow)'"
              style="cursor:pointer"
              @click="handleLeafClick(pg.phase_id, line.id)"
              @mouseenter="hoverLeaf(pg.phase_id, line.id)"
              @mouseleave="hoveredLeaf = null">
          <title>{{ getLeafTooltip(pg.phase_id, line.id) }}</title>
        </rect>
        <text v-for="(line, lIdx) in lines" :key="'leaf-t' + pIdx + '-' + lIdx"
              :x="getLeafX(pIdx, lIdx) + leafW / 2" :y="lineTop + lIdx * lineH + 3"
              text-anchor="middle" font-size="10" :font-weight="isHovered(pg.phase_id, line.id) ? 700 : 400"
              :fill="leafTextColor(pIdx, line.id)"
              style="pointer-events:none">
          {{ line.short_name || line.name }}
        </text>
      </g>

      <!-- 左侧技术线标签 -->
      <text v-for="(line, lIdx) in lines" :key="'label' + lIdx"
            :x="20" :y="lineTop + lIdx * lineH + 3"
            text-anchor="start" font-size="11" fill="#606266" font-weight="500">
        {{ line.name }}
      </text>

      <!-- 图例 -->
      <rect x="20" :y="svgHeight - 30" width="10" height="10" rx="2" fill="#67c23a" />
      <text x="34" :y="svgHeight - 20" font-size="10" fill="#909399">已完成</text>
      <rect x="80" :y="svgHeight - 30" width="10" height="10" rx="2" fill="#409eff" />
      <text x="94" :y="svgHeight - 20" font-size="10" fill="#909399">进行中</text>
      <rect x="140" :y="svgHeight - 30" width="10" height="10" rx="2" fill="#e4e7ed" />
      <text x="154" :y="svgHeight - 20" font-size="10" fill="#909399">未开始</text>
      <rect x="200" :y="svgHeight - 30" width="10" height="10" rx="2" fill="#f56c6c" />
      <text x="214" :y="svgHeight - 20" font-size="10" fill="#909399">阻塞</text>
    </svg>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { getLines, getDeliverables } from '../../api/index.js'

const props = defineProps({
  phaseGates: { type: Array, default: () => [] },
  projectId: { type: Number, required: true },
})

const emit = defineEmits(['clickLine'])

const lines = ref([])
const deliverables = ref([])
const hoveredLeaf = ref(null)

function handleLeafClick(phaseId, lineId) {
  emit('clickLine', { phaseId, lineId })
}

function hoverLeaf(phaseId, lineId) {
  hoveredLeaf.value = { phaseId, lineId }
}

function isHovered(phaseId, lineId) {
  return hoveredLeaf.value?.phaseId === phaseId && hoveredLeaf.value?.lineId === lineId
}

function getLeafTooltip(phaseId, lineId) {
  const items = deliverables.value.filter(d => d.phase_id === phaseId && d.line_id === lineId)
  const phase = props.phaseGates.find(pg => pg.phase_id === phaseId)
  const line = lines.value.find(l => l.id === lineId)
  if (items.length === 0) return `${phase?.phase?.name || ''} - ${line?.name || ''}：暂无交付物`
  const statusMap = { not_submitted: '未提交', submitted: '已提交', reviewed: '已评审', approved: '已批准', rejected: '已驳回' }
  return items.map(d => `${d.name}（${statusMap[d.status] || d.status}）`).join('；')
}

// Layout constants
const phaseW = 130
const phaseGap = 20
const leafW = 100
const lineH = 28
const lineTop = 110
const centerY = 70
const leftMargin = 100
const leafGap = 5  // gap between leaves within a phase

const svgWidth = computed(() => leftMargin + 6 * (phaseW + phaseGap) + 40)
const svgHeight = computed(() => lineTop + 6 * lineH + 60)

function getPhaseX(idx) { return leftMargin + idx * (phaseW + phaseGap) }
function getLeafX(pIdx, lIdx) {
  // Center the 6 leaves under each phase
  const totalWidth = 6 * leafW + 5 * leafGap
  const startX = getPhaseX(pIdx) + (phaseW - totalWidth) / 2
  return startX + lIdx * (leafW + leafGap)
}

// Colors
function phaseColor(pg) {
  if (pg.status === 'completed') return '#e1f3d8'
  if (pg.status === 'in_progress') return '#d9ecff'
  return '#f5f5f5'
}
function phaseTextColor(pg) {
  if (pg.status === 'completed') return '#67c23a'
  if (pg.status === 'in_progress') return '#409eff'
  return '#909399'
}
function phaseStatusText(pg) {
  const map = { completed: '✓ 已完成', in_progress: '● 进行中', not_started: '未开始' }
  return map[pg.status] || pg.status
}

function leafColor(pIdx, lineId) {
  // Check deliverables for this phase+line
  const items = deliverables.value.filter(d => d.phase_id === props.phaseGates[pIdx]?.phase_id && d.line_id === lineId)
  if (items.length === 0) return '#f5f7fa'
  const hasApproved = items.some(d => d.status === 'approved')
  const hasSubmitted = items.some(d => d.status === 'submitted' || d.status === 'reviewed')
  if (hasApproved) return '#e1f3d8'
  if (hasSubmitted) return '#d9ecff'
  return '#fef0e6'
}

function leafTextColor(pIdx, lineId) {
  const items = deliverables.value.filter(d => d.phase_id === props.phaseGates[pIdx]?.phase_id && d.line_id === lineId)
  if (items.length === 0) return '#c0c4cc'
  const hasApproved = items.some(d => d.status === 'approved')
  const hasSubmitted = items.some(d => d.status === 'submitted' || d.status === 'reviewed')
  if (hasApproved) return '#67c23a'
  if (hasSubmitted) return '#409eff'
  return '#e6a23c'
}

onMounted(async () => {
  const [linesRes, deliRes] = await Promise.all([
    getLines(),
    getDeliverables(props.projectId),
  ])
  lines.value = linesRes.data
  deliverables.value = deliRes.data
})
</script>

<style scoped>
.tree-container {
  overflow-x: auto;
  padding: 10px 0;
}
</style>
