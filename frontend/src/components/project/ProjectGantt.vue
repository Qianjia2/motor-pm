<template>
  <div class="pg-wrap">
    <div class="pg-toolbar">
      <div style="display:flex;gap:8px;align-items:center">
        <el-radio-group v-model="scale" size="small">
          <el-radio-button label="month">月</el-radio-button>
          <el-radio-button label="week">周</el-radio-button>
        </el-radio-group>
        <span style="font-size:12px;color:var(--text-muted)">共 {{ milestones.length }} 条</span>
      </div>
      <div style="display:flex;gap:10px;align-items:center">
        <span class="pg-tip">拖动计划条调整日期，拖右边缘调整时长</span>
        <span class="pg-legend"><span class="pg-dot" style="background:#10b981"></span> 已完成</span>
        <span class="pg-legend"><span class="pg-dot" style="background:#3b82f6"></span> 进行中</span>
        <span class="pg-legend"><span class="pg-dot" style="background:#f59e0b"></span> 待开始</span>
        <span class="pg-legend"><span class="pg-dot" style="background:#ef4444"></span> 已逾期</span>
      </div>
    </div>

    <div v-if="!milestones.length" style="text-align:center;padding:40px;color:var(--text-muted)">暂无里程碑</div>

    <div v-else class="pg-body">
      <div class="pg-header">
        <div class="pg-label-col">里程碑</div>
        <div class="pg-time-header">
          <div v-if="todayPx !== null" class="pg-today-hdr" :style="{left:todayPx+'px'}">今天</div>
          <div v-for="col in timeColumns" :key="col.key"
            class="pg-time-col" :style="{width:col.width+'px',minWidth:col.width+'px'}">
            {{ col.label }}
          </div>
        </div>
      </div>

      <template v-for="grp in grouped" :key="grp.key">
        <div class="pg-phase-hdr">{{ grp.label }}</div>
        <div v-for="ms in grp.items" :key="ms.id" class="pg-row">
          <div class="pg-label-col">
            <span class="pg-dot" :style="{background:statusColor(ms)}"></span>
            <span class="pg-name" :title="ms.name">{{ ms.name }}</span>
            <span class="pg-line" v-if="ms._lineName">{{ ms._lineName }}</span>
          </div>
          <div class="pg-bar-area" :style="{minWidth:totalPx+'px'}">
            <div v-if="todayPx !== null" class="pg-today-line" :style="{left:todayPx+'px'}"></div>
            <div v-if="effMs(ms).planned_date" class="pg-bar pg-planned"
              :class="{dragging: drag && drag.id===ms.id}"
              :style="barStyle(ms,'planned')"
              :title="'计划: '+effMs(ms).planned_date+(effMs(ms).planned_end_date?' ~ '+effMs(ms).planned_end_date:'')+'（拖动调整日期）'"
              @mousedown="startDrag($event, ms, 'move')">
              <span v-if="barPx(ms) >= 40" class="pg-bar-text">{{ ms.name.slice(0,10) }}</span>
              <span v-if="barPx(ms) >= 24" class="pg-resize" title="拖动调整时长" @mousedown.stop.prevent="startDrag($event, ms, 'resize')"></span>
            </div>
            <div v-if="effMs(ms).actual_date" class="pg-bar pg-actual"
              :style="barStyle(ms,'actual')"
              :title="'实际: '+effMs(ms).actual_date+(effMs(ms).actual_end_date?' ~ '+effMs(ms).actual_end_date:'')">
            </div>
          </div>
        </div>
      </template>
    </div>

    <el-dialog v-model="detailVisible" :title="detailMs?.name || '里程碑详情'" width="460px" destroy-on-close>
      <div v-if="detailMs" class="ms-detail">
        <div class="ms-detail-row">
          <span class="lbl">状态</span>
          <span class="ms-tag" :style="{background:statusColor(detailMs)}">{{ statusText(detailMs) }}</span>
        </div>
        <div class="ms-detail-row">
          <span class="lbl">所属阶段</span>
          <span>{{ detailMs.phase_name || detailMs.phase?.name || '未分配阶段' }}</span>
        </div>
        <div class="ms-detail-row" v-if="detailMs.line?.name || detailMs._lineName">
          <span class="lbl">技术线</span>
          <span>{{ detailMs.line?.name || detailMs._lineName }}</span>
        </div>
        <div class="ms-detail-row">
          <span class="lbl">计划时间</span>
          <span>{{ detailMs.planned_date }} ~ {{ detailMs.planned_end_date || detailMs.planned_date }}</span>
        </div>
        <div class="ms-detail-row" v-if="detailMs.actual_date">
          <span class="lbl">实际时间</span>
          <span>{{ detailMs.actual_date }} ~ {{ detailMs.actual_end_date || detailMs.actual_date }}</span>
        </div>
        <div class="ms-detail-row" v-if="detailMs.is_key">
          <span class="lbl">关键节点</span>
          <span>是</span>
        </div>
        <div class="ms-detail-desc" v-if="detailMs.description">
          <span class="lbl">说明</span>
          <div>{{ detailMs.description }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { updateMilestone } from '../../api/index.js'

const props = defineProps({
  milestones: { type: Array, default: () => [] },
})
const emit = defineEmits(['changed'])

const scale = ref('month')
// 天 → 像素换算:周视图 32px/周,月视图 80px/30.44天(基准月宽,实际列宽按当月天数)
const pxPerDay = computed(() => scale.value === 'week' ? 32 / 7 : 80 / 30.44)

// 纯日期解析(本地时区),避免 ISO 字符串按 UTC 解析产生 ±8h 偏移
function parseDate(s) {
  const [y, m, d] = String(s).split('-').map(Number)
  return new Date(y, (m || 1) - 1, d || 1)
}

const timeRange = computed(() => {
  let min = null, max = null
  props.milestones.forEach(m => {
    [m.planned_date, m.planned_end_date, m.actual_date, m.actual_end_date].forEach(d => {
      if (d) { const dt = parseDate(d); if (!min || dt < min) min = dt; if (!max || dt > max) max = dt }
    })
  })
  if (!min) min = new Date()
  if (!max) max = new Date()
  min = new Date(min); min.setDate(1); min.setMonth(min.getMonth() - 1)
  max = new Date(max); max.setMonth(max.getMonth() + 1)
  return { min, max }
})

const timeColumns = computed(() => {
  const cols = []
  const cur = new Date(timeRange.value.min)
  while (cur <= timeRange.value.max) {
    const y = cur.getFullYear(), m = cur.getMonth() + 1
    if (scale.value === 'week') {
      const wn = Math.ceil(((cur - new Date(y,0,1)) / 86400000 + new Date(y,0,1).getDay() + 1) / 7)
      cols.push({ key: `${y}-W${wn}`, label: `${m}/${cur.getDate()}`, width: 32 })
      cur.setDate(cur.getDate() + 7)
    } else {
      const days = new Date(y, m, 0).getDate()
      cols.push({ key: `${y}-${m}`, label: `${y}/${m}月`, width: Math.round(days * pxPerDay.value) })
      cur.setMonth(cur.getMonth() + 1)
    }
  }
  return cols
})

const totalPx = computed(() => timeColumns.value.reduce((s, c) => s + c.width, 0))

// "今天"竖线位置(超出时间轴范围则不显示)
const todayPx = computed(() => {
  const t = new Date(); t.setHours(0, 0, 0, 0)
  const px = (t - timeRange.value.min) / 86400000 * pxPerDay.value
  return px >= 0 && px <= totalPx.value ? px : null
})

const grouped = computed(() => {
  const map = new Map()
  props.milestones.forEach(m => {
    const k = m.phase_id || 0
    const label = m.phase_name || m.phase?.name || '未分配阶段'
    if (!map.has(k)) map.set(k, { key: k, label, items: [] })
    map.get(k).items.push({
      ...m,
      _lineName: m.line?.short_name || m.line?.name || '',
    })
  })
  return [...map.values()].sort((a, b) => a.key - b.key)
})

// ── 点击条查看详情 ──
const detailVisible = ref(false)
const detailMs = ref(null)
const STATUS_TEXT = { completed: '已完成', in_progress: '进行中', pending: '待开始' }
function statusText(ms) { return STATUS_TEXT[ms.status] || ms.status || '待开始' }
function showDetail(ms) {
  detailMs.value = ms
  detailVisible.value = true
}

// ── 拖拽调整计划日期 ──
const drag = ref(null)      // {id, mode: 'move'|'resize', startX, startY, origStart, durDays}
const overrides = ref({})   // { [msId]: {planned_date, planned_end_date} } 拖拽中的临时日期

function fmt(dt) {
  const y = dt.getFullYear(), m = String(dt.getMonth()+1).padStart(2,'0'), d = String(dt.getDate()).padStart(2,'0')
  return `${y}-${m}-${d}`
}
function effMs(ms) {
  const o = overrides.value[ms.id]
  return o ? { ...ms, ...o } : ms
}
function startDrag(e, ms, mode) {
  if (e.button !== 0) return
  const base = effMs(ms)
  const origStart = base.planned_date ? new Date(base.planned_date) : null
  if (!origStart) return
  const origEnd = base.planned_end_date ? new Date(base.planned_end_date) : origStart
  drag.value = { id: ms.id, mode, startX: e.clientX, startY: e.clientY, origStart, durDays: Math.max(0, Math.round((origEnd - origStart) / 86400000)) }
  document.body.classList.add('pg-dragging')
}
function onMove(e) {
  if (!drag.value) return
  const d = drag.value
  const delta = Math.round((e.clientX - d.startX) / pxPerDay.value)
  const start = new Date(d.origStart); start.setDate(start.getDate() + delta)
  const end = new Date(start)
  end.setDate(start.getDate() + (d.mode === 'resize' ? Math.max(1, d.durDays + delta) : d.durDays))
  overrides.value = { ...overrides.value, [d.id]: { planned_date: fmt(start), planned_end_date: fmt(end) } }
}
async function onUp(e) {
  if (!drag.value) return
  const d = drag.value
  const o = overrides.value[d.id]
  const moved = Math.hypot(e.clientX - d.startX, e.clientY - d.startY) >= 5
  drag.value = null
  document.body.classList.remove('pg-dragging')
  if (!moved && d.mode === 'move') {
    const ms = props.milestones.find(x => x.id === d.id)
    if (ms) { showDetail(ms); return }
  }
  const clear = () => { const { [d.id]: _, ...rest } = overrides.value; overrides.value = rest }
  if (!o) return
  if (o.planned_date === fmt(d.origStart) && o.planned_end_date === fmt(new Date(d.origStart.getTime() + d.durDays * 86400000))) { clear(); return }
  try {
    await updateMilestone(d.id, { planned_date: o.planned_date, planned_end_date: o.planned_end_date })
    clear()
    emit('changed')
  } catch (e) {
    clear()
    alert('保存失败: ' + (e?.response?.data?.detail || '请重试'))
  }
}
onMounted(() => {
  window.addEventListener('mousemove', onMove)
  window.addEventListener('mouseup', onUp)
})
onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMove)
  window.removeEventListener('mouseup', onUp)
  document.body.classList.remove('pg-dragging')
})

// 计划条的实际像素宽度(用于决定是否显示 resize 手柄,窄条全部视为移动)
function barPx(ms) {
  const m = effMs(ms)
  if (!m.planned_date) return 0
  const ed = m.planned_end_date || m.planned_date
  return Math.max(3, (parseDate(ed) - parseDate(m.planned_date)) / 86400000) * pxPerDay.value
}

function barStyle(ms, type) {
  const m = effMs(ms)
  const sd = type === 'actual' ? (m.actual_date || m.planned_date) : m.planned_date
  const ed = type === 'actual' ? (m.actual_end_date || m.actual_date || m.planned_end_date) : (m.planned_end_date || m.planned_date)
  if (!sd) return { display: 'none' }
  const left = (parseDate(sd) - timeRange.value.min) / 86400000 * pxPerDay.value
  const w = Math.max(2, (parseDate(ed) - parseDate(sd)) / 86400000) * pxPerDay.value
  if (type === 'actual') return { left: left + 'px', width: Math.max(w, 2) + 'px', background: '#10b981' }
  return { left: left + 'px', width: Math.max(w, 2) + 'px', background: statusColor(ms) }
}

function statusColor(ms) {
  const m = effMs(ms)
  const today = new Date(); today.setHours(0,0,0,0)
  if (m.status === 'completed') return '#10b981'
  if (m.status === 'in_progress') return '#3b82f6'
  if (m.planned_end_date && parseDate(m.planned_end_date) < today) return '#ef4444'
  return '#f59e0b'
}
</script>

<style scoped>
.pg-wrap { background:#fff; border-radius:8px; border:1px solid #f0f0f0; overflow:hidden; }
.pg-toolbar { display:flex; justify-content:space-between; align-items:center; padding:10px 14px; border-bottom:1px solid #f0f0f0; flex-wrap:wrap; gap:6px; }
.pg-tip { font-size:11px; color:#6b7280; }
.pg-legend { font-size:11px; color:var(--text-muted); display:flex; align-items:center; gap:4px; }
.pg-dot { width:10px; height:10px; border-radius:2px; flex-shrink:0; }
.pg-body { overflow-x:auto; overflow-y:visible; }
.pg-header { display:flex; position:sticky; top:0; z-index:2; background:#fff; }
.pg-label-col { width:220px; min-width:220px; padding:6px 10px; font-weight:600; font-size:12px; border-right:1px solid #f0f0f0; display:flex; align-items:center; gap:6px; position:sticky; left:0; background:#fff; z-index:1; }
.pg-header .pg-label-col { z-index:3; }
.pg-time-header { display:flex; flex:1; position:relative; }
.pg-time-col { text-align:center; font-size:10px; color:#6b7280; padding:6px 0; border-right:1px solid #f5f5f5; }
.pg-phase-hdr { padding:5px 14px; font-size:12px; font-weight:600; color:#6b7280; background:#f9fafb; border-bottom:1px solid #f0f0f0; position:sticky; left:0; }
.pg-row { display:flex; border-bottom:1px solid #fafafa; align-items:center; min-height:30px; }
.pg-row:hover { background:#f9fafb; }
.pg-today-hdr { position:absolute; top:0; bottom:0; width:0; border-left:1px solid #ef4444; font-size:9px; color:#ef4444; white-space:nowrap; padding-left:3px; z-index:4; pointer-events:none; line-height:14px; }
.pg-today-line { position:absolute; top:0; bottom:0; width:0; border-left:1px dashed #fca5a5; z-index:1; pointer-events:none; }
.pg-name { font-size:12px; color:#1f2937; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; }
.pg-line { font-size:10px; color:#9ca3af; background:#f3f4f6; padding:0 4px; border-radius:2px; white-space:nowrap; }
.pg-bar-area { flex:1; position:relative; height:24px; min-width:200px; }
.pg-bar { position:absolute; top:3px; height:18px; border-radius:3px; min-width:3px; display:flex; align-items:center; padding:0 4px; overflow:hidden; }
.pg-planned { opacity:0.9; cursor:move; user-select:none; }
.pg-planned:hover { opacity:1; }
.pg-planned.dragging { opacity:.7; box-shadow:0 0 0 1px #2563eb; z-index:2; }
.pg-actual { top:14px; height:5px; border-radius:1px; pointer-events:none; }
.pg-bar-text { color:#fff; font-size:9px; white-space:nowrap; overflow:hidden; pointer-events:none; }
.pg-resize { position:absolute; right:0; top:0; bottom:0; width:8px; cursor:ew-resize; }
.pg-resize:hover { background:rgba(255,255,255,.35); }
:global(body.pg-dragging) { cursor:col-resize; user-select:none; }
.ms-detail { display:flex; flex-direction:column; gap:10px; font-size:13px; }
.ms-detail-row { display:flex; align-items:flex-start; gap:10px; line-height:1.6; }
.ms-detail-row .lbl, .ms-detail-desc .lbl { color:#9ca3af; width:70px; flex-shrink:0; }
.ms-detail-desc { display:flex; gap:10px; line-height:1.6; }
.ms-detail-desc div { background:#f9fafb; border-radius:4px; padding:6px 10px; flex:1; white-space:pre-wrap; }
.ms-tag { color:#fff; font-size:12px; padding:1px 10px; border-radius:10px; }
</style>
