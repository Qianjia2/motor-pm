<template>
  <div class="progress-dashboard">
    <el-row :gutter="16" style="margin-bottom:16px">
      <el-col :span="6" v-for="m in metrics" :key="m.label">
        <div class="metric-card" :style="{borderLeftColor:m.color}">
          <div class="metric-value" :style="{color:m.color}">{{ m.value }}{{ m.unit }}</div>
          <div class="metric-label">{{ m.label }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <!-- Burndown -->
      <el-col :span="12">
        <div class="card" style="height:320px">
          <div class="card-title" style="margin-bottom:12px">里程碑燃尽图</div>
          <div class="chart-wrap">
            <svg viewBox="0 0 300 240" class="chart-svg">
              <polyline :points="plannedLine" fill="none" stroke="#9ca3af" stroke-width="2" stroke-dasharray="5,3" />
              <polyline :points="actualLine" fill="none" stroke="#3b82f6" stroke-width="3" />
              <circle v-for="(p, i) in actualPoints" :key="i" :cx="p.x" :cy="p.y" r="3" fill="#3b82f6" />
              <!-- Axis -->
              <line x1="40" y1="210" x2="280" y2="210" stroke="#e5e7eb" stroke-width="1" />
              <line x1="40" y1="10" x2="40" y2="210" stroke="#e5e7eb" stroke-width="1" />
              <!-- Labels -->
              <text x="150" y="230" text-anchor="middle" fill="#9ca3af" font-size="10">时间</text>
              <text x="16" y="115" text-anchor="middle" fill="#9ca3af" font-size="10" transform="rotate(-90,16,115)">剩余任务</text>
              <text x="40" y="220" fill="#9ca3af" font-size="9">起</text>
              <text x="280" y="220" text-anchor="end" fill="#9ca3af" font-size="9">终</text>
            </svg>
            <div style="display:flex;gap:16px;justify-content:center;margin-top:8px;font-size:11px">
              <span><span class="legend-dot" style="background:#9ca3af"></span> 计划</span>
              <span><span class="legend-dot" style="background:#3b82f6"></span> 实际</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- Task distribution -->
      <el-col :span="12">
        <div class="card" style="height:320px">
          <div class="card-title" style="margin-bottom:12px">任务状态分布</div>
          <div class="dist-bars">
            <div v-for="s in statusDist" :key="s.label" class="dist-row">
              <span class="dist-label">{{ s.label }}</span>
              <div class="dist-bar-bg"><div class="dist-bar-fill" :style="{width:s.pct+'%',background:s.color}"></div></div>
              <span class="dist-num">{{ s.count }}</span>
            </div>
          </div>
          <!-- Phase completion -->
          <div class="card-title" style="margin:16px 0 8px">阶段完成情况</div>
          <div v-for="ph in phaseProgress" :key="ph.name" class="phase-row">
            <span class="phase-name">{{ ph.name }}</span>
            <el-progress :percentage="ph.pct" :stroke-width="6" :color="ph.color" style="flex:1;margin:0 12px" />
            <span style="font-size:11px;color:var(--text-muted)">{{ ph.done }}/{{ ph.total }}</span>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
  milestones: { type: Array, default: () => [] },
  phases: { type: Array, default: () => [] },
})

const flatTasks = computed(() => {
  const r = []; function walk(l) { for (const t of l) { r.push(t); if (t.children) walk(t.children) } }; walk(props.tasks); return r
})

const totalTasks = computed(() => flatTasks.value.length)
const doneTasks = computed(() => flatTasks.value.filter(t => t.status === 'completed').length)
const blockedTasks = computed(() => flatTasks.value.filter(t => t.status === 'blocked').length)
const inProgressTasks = computed(() => flatTasks.value.filter(t => t.status === 'in_progress').length)

const msTotal = computed(() => props.milestones.length)
const msDone = computed(() => props.milestones.filter(m => m.status === 'completed').length)
const msInProgress = computed(() => props.milestones.filter(m => m.status === 'in_progress').length)
const msPending = computed(() => props.milestones.filter(m => m.status === 'pending').length)

const metrics = computed(() => [
  { label: '里程碑完成率', value: msTotal.value ? Math.round(msDone.value/msTotal.value*100) : 0, unit: '%', color: '#10b981' },
  { label: '已完成', value: msDone.value, unit: '', color: '#10b981' },
  { label: '进行中', value: msInProgress.value, unit: '', color: '#3b82f6' },
  { label: '待开始', value: msPending.value, unit: '', color: '#f59e0b' },
])

const statusDist = computed(() => {
  const colors = { completed: '#10b981', in_progress: '#3b82f6', pending: '#9ca3af' }
  const labels = { completed: '已完成', in_progress: '进行中', pending: '待开始' }
  const total = msTotal.value || 1
  return Object.entries(labels).map(([k, v]) => ({
    label: v, color: colors[k],
    count: props.milestones.filter(m => m.status === k).length,
    pct: Math.round(props.milestones.filter(m => m.status === k).length / total * 100),
  }))
})

// Burndown chart based on milestones
const actualPoints = computed(() => {
  const total = msTotal.value || 1
  const done = msDone.value
  return [
    { x: 40, y: 210 },
    { x: 160, y: 210 - (done/total)*190 },
    { x: 280, y: total > 0 ? 210 - (1)*190 : 210 },
  ]
})
const plannedLine = computed(() => '40,210 160,110 280,20')
const actualLine = computed(() => actualPoints.value.map(p => `${p.x},${p.y}`).join(' '))
</script>

<style scoped>
.metric-card { background:var(--bg-white); border-radius:8px; padding:16px; box-shadow:var(--shadow-sm); border-left:3px solid; }
.metric-value { font-size:24px; font-weight:700; }
.metric-label { font-size:12px; color:var(--text-secondary); margin-top:4px; }
.chart-wrap { text-align:center; }
.chart-svg { max-width:100%; height:220px; }
.dist-bars { display:flex; flex-direction:column; gap:8px; }
.dist-row { display:flex; align-items:center; gap:8px; font-size:12px; }
.dist-label { width:50px; text-align:right; color:var(--text-secondary); }
.dist-bar-bg { flex:1; height:16px; background:#f3f4f6; border-radius:4px; overflow:hidden; }
.dist-bar-fill { height:100%; border-radius:4px; transition:width .5s; }
.dist-num { width:24px; font-weight:600; color:var(--text); }
.phase-row { display:flex; align-items:center; margin-bottom:6px; font-size:12px; }
.phase-name { width:80px; color:var(--text-secondary); }
.legend-dot { display:inline-block; width:8px; height:8px; border-radius:50%; }
</style>
