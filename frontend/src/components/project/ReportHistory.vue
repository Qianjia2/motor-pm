<template>
  <div>
    <div v-if="reports.length === 0" style="text-align:center;padding:60px;color:var(--text-muted)">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" stroke-width="1.5"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      <p style="margin-top:8px">暂无周报记录</p>
    </div>

    <el-timeline v-else>
      <el-timeline-item
        v-for="r in reports"
        :key="r.id"
        :timestamp="r.year + '年 第' + r.week_number + '周 (' + weekToRange(r.year, r.week_number) + ') | ' + (r.report_date || '')"
        placement="top"
        :type="r.line_items?.some(li => li.status === 'delayed' || li.status === 'risk') ? 'warning' : 'primary'"
      >
        <el-card shadow="hover" style="cursor:pointer">
          <div class="flex-between mb-sm" @click="$emit('view', r)">
            <div>
              <el-tag v-if="r.reporter" size="small" type="info">{{ r.reporter.name }}</el-tag>
              <span v-if="r.completion_rate" style="margin-left:8px;font-size:13px;color:#909399">完成率：{{ r.completion_rate }}</span>
            </div>
            <div>
              <el-tag v-for="li in r.line_items?.filter(x => x.status !== 'normal').slice(0, 3)" :key="li.id"
                size="small" :type="li.status==='delayed'?'danger':li.status==='risk'?'warning':'info'" style="margin-left:4px">
                {{ li.line?.short_name || li.line_id }}
              </el-tag>
            </div>
          </div>
          <div style="font-size:13px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin-bottom:8px"
            @click="$emit('view', r)">
            {{ r.overall_progress || '（无概述）' }}
          </div>
          <div style="display:flex;gap:4px" @click.stop>
            <el-button size="small" @click="$emit('edit', r)">编辑</el-button>
            <el-popconfirm title="确认删除该周报?" @confirm="$emit('delete', r)">
              <template #reference><el-button size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </div>
        </el-card>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup>
function weekToRange(year, week) {
  const jan4 = new Date(year, 0, 4)
  const jan4Day = jan4.getDay() || 7
  const firstMonday = new Date(jan4)
  firstMonday.setDate(jan4.getDate() - jan4Day + 1)
  const mon = new Date(firstMonday.getTime() + (week - 1) * 7 * 86400000)
  const sun = new Date(mon.getTime() + 6 * 86400000)
  return `${mon.getMonth()+1}/${mon.getDate()}-${sun.getMonth()+1}/${sun.getDate()}`
}

defineProps({ reports: { type: Array, default: () => [] } })
defineEmits(['view', 'edit', 'delete'])
</script>
