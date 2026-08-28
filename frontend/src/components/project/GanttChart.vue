<template>
  <div class="gantt-container" ref="containerRef">
    <!-- Toolbar -->
    <div class="gantt-toolbar">
      <div class="gantt-legend">
        <span class="legend-item"><span class="dot" style="background:#3b82f6"></span> 进行中</span>
        <span class="legend-item"><span class="dot" style="background:#10b981"></span> 已完成</span>
        <span class="legend-item"><span class="dot" style="background:#f59e0b"></span> 待开始</span>
        <span class="legend-item"><span class="dot" style="background:#ef4444"></span> 超期</span>
        <span class="legend-item"><span class="l-arrow">→</span> 依赖关系</span>
      </div>
      <div class="gantt-actions">
        <el-button-group size="small">
          <el-button :type="viewMode==='month'?'primary':''" @click="viewMode='month'">月</el-button>
          <el-button :type="viewMode==='week'?'primary':''" @click="viewMode='week'">周</el-button>
        </el-button-group>
        <el-button size="small" @click="scrollToToday">今天</el-button>
        <el-button size="small" @click="$emit('add')" type="primary">+ 添加</el-button>
      </div>
    </div>

    <!-- Gantt chart -->
    <div class="gantt-chart" ref="chartRef">
      <!-- Left panel: milestone names -->
      <div class="gantt-left">
        <div class="gantt-left-header">里程碑</div>
        <div v-for="ms in milestones" :key="ms.id" class="gantt-row-label"
          @click="$emit('edit', ms)" :title="'点击编辑: ' + ms.name">
          <span class="row-dot" :class="statusClass(ms)"></span>
          <span class="row-name">{{ ms.name }}</span>
          <span v-if="ms.project_name" class="row-project">{{ ms.project_name }}</span>
        </div>
      </div>

      <!-- Right panel: timeline -->
      <div class="gantt-right" ref="scrollRef" @scroll="onScroll">
        <div class="gantt-timeline-header" ref="headerRef">
          <div v-for="col in columns" :key="col.key" class="tl-col"
            :style="{width:colWidth+'px', minWidth:colWidth+'px'}">
            <div class="tl-label">{{ col.label }}</div>
          </div>
        </div>

        <!-- SVG canvas for bars + arrows -->
        <svg :width="svgWidth" :height="svgHeight" class="gantt-svg" ref="svgRef"
          @mousedown="onSvgMouseDown" @mousemove="onSvgMouseMove" @mouseup="onSvgMouseUp" @mouseleave="onSvgMouseUp">
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#9ca3af" />
            </marker>
          </defs>
          <!-- Grid lines -->
          <line v-for="(x, i) in gridLines" :key="'g'+i"
            :x1="x" :y1="0" :x2="x" :y2="svgHeight"
            stroke="#f3f4f6" stroke-width="1" />

          <!-- Today line -->
          <line v-if="todayX > 0" :x1="todayX" :y1="0" :x2="todayX" :y2="svgHeight"
            stroke="#ef4444" stroke-width="2" stroke-dasharray="4,3" />
          <text v-if="todayX > 0" :x="todayX + 4" y="12" fill="#ef4444" font-size="11" font-weight="600">今天</text>

          <!-- Dependency arrows -->
          <g v-for="d in dependencyLines" :key="'dep'+d.from">
            <path :d="d.path" fill="none" stroke="#9ca3af" stroke-width="1.5"
              marker-end="url(#arrowhead)" />
          </g>

          <!-- Bars -->
          <g v-for="ms in milestones" :key="ms.id" @mousedown.stop @click.stop>
            <rect
              :x="barX(ms)" :y="barY(ms.id)"
              :width="barWidth(ms)" height="22" rx="4"
              :fill="barColor(ms)" :opacity="ms.id === dragId ? 0.7 : 1"
              :style="{cursor: dragId === ms.id ? 'grabbing' : 'grab'}"
              @mousedown.prevent.stop="onBarMouseDown($event, ms, 'move')"
            />
            <text
              :x="barX(ms) + 6" :y="barY(ms.id) + 15"
              fill="#fff" font-size="11" font-weight="600"
              style="pointer-events:none"
            >{{ ms.name.slice(0, 12) }}{{ ms.name.length > 12 ? '…' : '' }}</text>
            <!-- Right resize handle -->
            <rect
              :x="barX(ms) + barWidth(ms) - 6" :y="barY(ms.id)"
              width="8" height="22" rx="2" fill="transparent"
              style="cursor:ew-resize"
              @mousedown.prevent.stop="onBarMouseDown($event, ms, 'resize')"
            />
          </g>
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'

const props = defineProps({
  milestones: { type: Array, default: () => [] },
  projectId: { type: Number, default: null },
})

const emit = defineEmits(['update', 'edit', 'add'])

const viewMode = ref('month')
const containerRef = ref(null)
const chartRef = ref(null)
const scrollRef = ref(null)
const headerRef = ref(null)
const svgRef = ref(null)
const rowHeight = 44
const dragId = ref(null)
const dragMode = ref('move')
const dragStartX = ref(0)
const dragStartDate = ref('')
const dragStartEndDate = ref('')

// Compute timeline range
const startDate = computed(() => {
  if (!props.milestones.length) return new Date(new Date().getFullYear(), 0, 1)
  let min = null
  props.milestones.forEach(ms => {
    const s = ms.planned_date ? new Date(ms.planned_date) : null
    if (s && (!min || s < min)) min = s
  })
  if (!min) min = new Date()
  return new Date(min.getFullYear(), min.getMonth() - 1, 1)
})

const endDate = computed(() => {
  if (!props.milestones.length) return new Date(new Date().getFullYear() + 1, 0, 1)
  let max = null
  props.milestones.forEach(ms => {
    const s = ms.planned_date ? new Date(ms.planned_date) : null
    const e = ms.planned_end_date ? new Date(ms.planned_end_date) : s
    if (e && (!max || e > max)) max = e
  })
  if (!max) max = new Date()
  return new Date(max.getFullYear(), max.getMonth() + 2, 1)
})

const colWidth = computed(() => viewMode.value === 'week' ? 40 : 100)
const labelColWidth = 180

const columns = computed(() => {
  const cols = []
  const cur = new Date(startDate.value)
  while (cur < endDate.value) {
    if (viewMode.value === 'week') {
      cols.push({ key: `W${cur.getFullYear()}-${weekNum(cur)}`, label: getWeekLabel(cur) })
      cur.setDate(cur.getDate() + 7)
    } else {
      cols.push({ key: `${cur.getFullYear()}-${cur.getMonth()+1}`, label: `${cur.getFullYear()}/${cur.getMonth()+1}` })
      cur.setMonth(cur.getMonth() + 1)
    }
  }
  return cols
})

const svgWidth = computed(() => columns.value.length * colWidth.value + 40)
const svgHeight = computed(() => Math.max(props.milestones.length * rowHeight, 200))

const gridLines = computed(() => {
  const lines = []
  for (let i = 0; i <= columns.value.length; i++) {
    lines.push(i * colWidth.value)
  }
  return lines
})

const todayX = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  if (today < startDate.value || today > endDate.value) return -1
  return dateToX(today)
})

const dependencyLines = computed(() => {
  const lines = []
  props.milestones.forEach(ms => {
    if (!ms.depends_on_id) return
    const dep = props.milestones.find(m => m.id === ms.depends_on_id)
    if (!dep) return
    const fromX = barX(dep) + barWidth(dep)
    const fromY = barY(dep.id) + 11
    const toX = barX(ms)
    const toY = barY(ms.id) + 11
    const midX = (fromX + toX) / 2
    const path = `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`
    lines.push({ from: ms.depends_on_id, to: ms.id, path })
  })
  return lines
})

// Date conversion utilities
function dateToX(d) {
  const totalDays = (endDate.value - startDate.value) / (1000 * 60 * 60 * 24)
  const offsetDays = (new Date(d) - startDate.value) / (1000 * 60 * 60 * 24)
  return (offsetDays / totalDays) * svgWidth.value
}

function xToDate(x) {
  const totalDays = (endDate.value - startDate.value) / (1000 * 60 * 60 * 24)
  const pct = x / svgWidth.value
  const ms = startDate.value.getTime() + pct * totalDays * 86400000
  const d = new Date(ms)
  return d.toISOString().slice(0, 10)
}

function barY(msId) {
  const idx = props.milestones.findIndex(m => m.id === msId)
  return idx * rowHeight + 11
}

function barWidth(ms) {
  if (!ms.planned_date && !ms.actual_date) return 60
  return Math.max(barEndX(ms) - barX(ms), 40)
}

function barX(ms) {
  // Use actual date for completed milestones, planned date otherwise
  const d = (ms.status === 'completed' && ms.actual_date) ? ms.actual_date : ms.planned_date
  return d ? dateToX(new Date(d)) : 0
}

function barEndX(ms) {
  const d = (ms.status === 'completed' && ms.actual_end_date) ? ms.actual_end_date : ms.planned_end_date
  return d ? dateToX(new Date(d)) : barX(ms) + 60
}

function barColor(ms) {
  if (ms.status === 'completed') return '#10b981'
  if (ms.status === 'overdue') return '#ef4444'
  if (ms.status === 'in_progress') return '#3b82f6'
  return '#f59e0b'
}

function statusClass(ms) {
  if (ms.status === 'completed') return 'dot-done'
  if (ms.status === 'overdue') return 'dot-overdue'
  if (ms.status === 'in_progress') return 'dot-progress'
  return 'dot-pending'
}

function weekNum(d) {
  const start = new Date(d.getFullYear(), 0, 1)
  return Math.ceil(((d - start) / 86400000 + start.getDay() + 1) / 7)
}

function getWeekLabel(d) {
  const start = new Date(d)
  const end = new Date(d); end.setDate(end.getDate() + 6)
  return `${start.getMonth()+1}/${start.getDate()}`
}

// Scroll sync
function onScroll() {
  if (headerRef.value && scrollRef.value) {
    headerRef.value.scrollLeft = scrollRef.value.scrollLeft
  }
}

function scrollToToday() {
  if (todayX.value > 0 && scrollRef.value) {
    scrollRef.value.scrollLeft = todayX.value - 200
  }
}

// Drag handling
function onBarMouseDown(e, ms, mode) {
  dragId.value = ms.id
  dragMode.value = mode
  dragStartX.value = e.clientX
  dragStartDate.value = ms.planned_date || ''
  dragStartEndDate.value = ms.planned_end_date || ''
  document.addEventListener('mousemove', onDocMouseMove)
  document.addEventListener('mouseup', onDocMouseUp)
}

function onDocMouseMove(e) {
  if (!dragId.value) return
  const dx = e.clientX - dragStartX.value
  const dayShift = Math.round(dx / colWidth.value * (viewMode.value === 'week' ? 7 : 30))

  const ms = props.milestones.find(m => m.id === dragId.value)
  if (!ms) return

  const newStart = new Date(dragStartDate.value || ms.planned_date)
  const newEnd = dragStartEndDate.value ? new Date(dragStartEndDate.value) : null

  if (dragMode.value === 'move') {
    newStart.setDate(newStart.getDate() + dayShift)
    if (newEnd) newEnd.setDate(newEnd.getDate() + dayShift)
  } else if (dragMode.value === 'resize') {
    const baseDate = newStart
    const durationDays = newEnd ? Math.round((newEnd - baseDate) / 86400000) : 14
    const newDuration = Math.max(1, durationDays + dayShift)
    newEnd = new Date(baseDate)
    newEnd.setDate(newEnd.getDate() + newDuration)
  }

  // Auto-schedule dependents
  autoSchedule(ms.id, newEnd || newStart)

  emit('update', {
    id: ms.id,
    planned_date: newStart.toISOString().slice(0, 10),
    planned_end_date: newEnd ? newEnd.toISOString().slice(0, 10) : null,
  })
}

function autoSchedule(fromMsId, fromEndDate) {
  // Find all milestones that depend on this one
  const dependents = props.milestones.filter(m => m.depends_on_id === fromMsId)
  dependents.forEach(dep => {
    const newStart = new Date(fromEndDate)
    newStart.setDate(newStart.getDate() + 1)
    const oldStart = dep.planned_date ? new Date(dep.planned_date) : newStart
    const duration = dep.planned_end_date
      ? Math.round((new Date(dep.planned_end_date) - oldStart) / 86400000)
      : 14
    const newEnd = new Date(newStart)
    newEnd.setDate(newEnd.getDate() + Math.max(1, duration))

    emit('update', {
      id: dep.id,
      planned_date: newStart.toISOString().slice(0, 10),
      planned_end_date: newEnd.toISOString().slice(0, 10),
    })

    // Recurse for chain dependencies
    autoSchedule(dep.id, newEnd)
  })
}

function onDocMouseUp() {
  dragId.value = null
  document.removeEventListener('mousemove', onDocMouseMove)
  document.removeEventListener('mouseup', onDocMouseUp)
}

function onSvgMouseDown() {}
function onSvgMouseMove() {}
function onSvgMouseUp() { if (dragId.value) onDocMouseUp() }

onMounted(() => {
  nextTick(() => scrollToToday())
})
</script>

<style scoped>
.gantt-container {
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.gantt-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
}
.gantt-legend { display: flex; gap: 16px; font-size: 12px; color: var(--text-secondary); }
.legend-item { display: flex; align-items: center; gap: 4px; }
.l-arrow { color: #9ca3af; font-weight: 700; }
.gantt-actions { display: flex; gap: 6px; }

.gantt-chart {
  display: flex;
  max-height: 500px;
  overflow: hidden;
}

.gantt-left {
  width: 180px; flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: #fafafa;
}

.gantt-left-header {
  padding: 8px 12px; font-size: 12px; font-weight: 600;
  color: var(--text-secondary); border-bottom: 1px solid var(--border);
  background: #f5f5f5; height: 36px; display: flex; align-items: center;
}

.gantt-row-label {
  padding: 10px 12px; font-size: 12px; height: 44px;
  display: flex; align-items: center; gap: 6px;
  border-bottom: 1px solid #f3f4f6;
  cursor: pointer; transition: background .15s;
  overflow: hidden;
}
.gantt-row-label:hover { background: var(--primary-light); }
.row-name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.row-project { font-size: 10px; color: var(--text-muted); margin-left: auto; white-space: nowrap; }

.row-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot-done { background: #10b981; }
.dot-overdue { background: #ef4444; }
.dot-progress { background: #3b82f6; }
.dot-pending { background: #f59e0b; }

.gantt-right {
  flex: 1; overflow-x: auto; overflow-y: hidden;
}

.gantt-timeline-header {
  display: flex; height: 36px;
  border-bottom: 1px solid var(--border);
  background: #f5f5f5; position: sticky; top: 0; z-index: 3;
}
.tl-col {
  display: flex; align-items: center; justify-content: center;
  border-right: 1px solid #e5e7eb; flex-shrink: 0;
}
.tl-label { font-size: 11px; color: var(--text-secondary); font-weight: 500; }

.gantt-svg {
  display: block;
}

.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
</style>
