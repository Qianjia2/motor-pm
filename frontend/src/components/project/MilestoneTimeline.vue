<template>
  <div class="timeline-wrap" ref="wrapRef">
    <div class="timeline-header">
      <div class="tl-name-col">里程碑</div>
      <div class="tl-scroll-area" ref="scrollHeader">
        <div
          v-for="m in months"
          :key="m.key"
          class="tl-month-col"
          :style="{ width: monthWidth + 'px' }"
        >
          <div class="tl-month-label">{{ m.label }}</div>
          <div class="tl-week-row">
            <div
              v-for="w in m.weeks"
              :key="w"
              class="tl-week-cell"
              :style="{ width: weekWidth + 'px' }"
            >
              W{{ w }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-for="item in milestones"
      :key="item.id"
      class="timeline-row"
    >
      <div class="tl-name-col">
        <span :class="'milestone-dot ' + item.status"></span>
        <span style="font-size:13px">{{ item.name }}</span>
        <el-tag v-if="item.is_key" size="small" type="danger" style="margin-left:4px">关键</el-tag>
      </div>
      <div class="tl-scroll-area" :style="{ position: 'relative' }">
        <div
          class="tl-bar"
          :style="barStyle(item)"
          @click="$emit('click', item)"
        >
          <span class="tl-bar-label">{{ (item.actual_date||item.planned_date||'').slice(5) }} {{ item.name.slice(0,8) }}</span>
        </div>
      </div>
    </div>

    <!-- 图例 -->
    <div style="margin-top:12px;font-size:12px;color:#909399;display:flex;gap:16px">
      <span><span class="milestone-dot completed" style="display:inline-block;vertical-align:middle"></span> 已完成</span>
      <span><span class="milestone-dot in-progress" style="display:inline-block;vertical-align:middle"></span> 进行中</span>
      <span><span class="milestone-dot pending" style="display:inline-block;vertical-align:middle"></span> 未开始</span>
      <span><span class="milestone-dot blocked" style="display:inline-block;vertical-align:middle"></span> 阻塞</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  milestones: { type: Array, default: () => [] },
  startDate: { type: String, default: '' },
  endDate: { type: String, default: '' },
})

defineEmits(['click'])

const weekWidth = 22
const weeksPerMonth = 4
const monthWidth = weekWidth * weeksPerMonth

const months = computed(() => {
  // Find min/max dates from actual milestones
  let minDate = null
  let maxDate = null
  if (props.milestones.length) {
    props.milestones.forEach(m => {
      const d = m.actual_date || m.planned_date
      if (d) {
        const dt = new Date(d)
        if (!minDate || dt < minDate) minDate = dt
        if (!maxDate || dt > maxDate) maxDate = dt
      }
    })
  }
  const start = minDate || new Date()
  start.setMonth(start.getMonth() - 1)
  const end = maxDate || new Date()
  end.setMonth(end.getMonth() + 2)

  const result = []
  const cur = new Date(start.getFullYear(), start.getMonth(), 1)
  while (cur <= end) {
    const y = cur.getFullYear()
    const m = cur.getMonth() + 1
    result.push({
      key: `${y}-${m}`,
      label: `${y}年${m}月`,
      weeks: [1, 2, 3, 4],
      start: new Date(cur),
    })
    cur.setMonth(cur.getMonth() + 1)
  }
  return result
})

const totalDays = computed(() => {
  const first = months.value[0]?.start || new Date()
  const last = months.value[months.value.length - 1]?.start || new Date()
  last.setMonth(last.getMonth() + 1)
  return Math.max(1, (last - first) / (1000 * 60 * 60 * 24))
})

const baseDate = computed(() => months.value[0]?.start || new Date())

function barStyle(item) {
  // Prefer actual_date if set, otherwise planned_date
  const dateStr = item.actual_date || item.actual_end_date || item.planned_date
  if (!dateStr) return { display: 'none' }
  const d = new Date(dateStr)
  const offsetDays = (d - baseDate.value) / (1000 * 60 * 60 * 24)
  const left = (offsetDays / totalDays.value) * months.value.length * monthWidth
  const colorMap = { completed: '#67c23a', in_progress: '#409eff', pending: '#c0c4cc', blocked: '#f56c6c' }
  return {
    left: Math.max(0, left) + 'px',
    width: '80px',
    background: colorMap[item.status] || '#c0c4cc',
  }
}
</script>

<style scoped>
.timeline-wrap {
  font-size: 12px;
  overflow-x: auto;
}
.timeline-header {
  display: flex;
  border-bottom: 2px solid #e4e7ed;
  padding-bottom: 4px;
}
.tl-name-col {
  width: 200px;
  flex-shrink: 0;
  font-weight: 600;
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.tl-scroll-area {
  flex: 1;
  display: flex;
  overflow-x: auto;
}
.tl-month-col {
  border-right: 1px solid #e4e7ed;
}
.tl-month-label {
  text-align: center;
  font-weight: 600;
  color: #606266;
  padding: 4px 0;
}
.tl-week-row {
  display: flex;
}
.tl-week-cell {
  text-align: center;
  color: #c0c4cc;
  font-size: 10px;
  border-left: 1px solid #f5f5f5;
}
.timeline-row {
  display: flex;
  border-bottom: 1px solid #f0f0f0;
  position: relative;
}
.timeline-row:hover {
  background: #f5f7fa;
}
.tl-bar {
  height: 20px;
  border-radius: 4px;
  position: absolute;
  top: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  padding: 0 6px;
  transition: box-shadow 0.2s;
}
.tl-bar:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
}
.tl-bar-label {
  color: #fff;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
