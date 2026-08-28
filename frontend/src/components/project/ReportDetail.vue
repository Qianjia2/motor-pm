<template>
  <div>
    <el-page-header @back="$emit('back')" :content="`${report.year}年 第${report.week_number}周 周报`" style="margin-bottom:16px" />

    <el-descriptions :column="2" border size="small" style="margin-bottom:16px">
      <el-descriptions-item label="报告日期">{{ report.report_date || '-' }}</el-descriptions-item>
      <el-descriptions-item label="填写人">{{ report.reporter?.name || '-' }}</el-descriptions-item>
      <el-descriptions-item label="完成率">{{ report.completion_rate || '-' }}</el-descriptions-item>
      <el-descriptions-item label="关键成果">{{ report.key_accomplishments || '-' }}</el-descriptions-item>
    </el-descriptions>

    <div style="margin-bottom:16px;padding:12px;background:#f9fafb;border-radius:6px;border-left:3px solid #3b82f6">
      <div style="font-weight:600;font-size:13px;color:#374151;margin-bottom:6px">总体进展</div>
      <div style="font-size:13px;color:#4b5563;line-height:1.6">{{ report.overall_progress || '（无）' }}</div>
    </div>

    <el-table :data="report.line_items || []" border stripe size="small">
      <el-table-column prop="line.name" label="技术线" width="100">
        <template #default="{row}">
          <el-tag size="small">{{ row.line?.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="去哪里(本周目标)" width="120" show-overflow-tooltip>
        <template #default="{row}"><span style="font-size:12px;color:#6b7280">{{ row.goal || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="this_week" label="在哪里(进展)" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="80">
        <template #default="{row}">
          <el-tag :type="row.status === 'delayed' ? 'danger' : row.status === 'risk' ? 'warning' : row.status === 'completed' ? 'success' : 'info'" size="small">
            {{ statusMap[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="next_week" label="下周计划" min-width="200" show-overflow-tooltip />
      <el-table-column prop="blocker" label="难点/阻塞" min-width="150" show-overflow-tooltip>
        <template #default="{row}">
          <span v-if="row.blocker" style="color:#f56c6c">{{ row.blocker }}</span>
          <span v-else style="color:#c0c4cc">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="coordinator" label="协调人" width="80" />
    </el-table>

    <div style="margin-top:16px;text-align:right">
      <el-button type="primary" @click="$emit('edit', report)">编辑</el-button>
    </div>
  </div>
</template>

<script setup>
defineProps({
  report: { type: Object, default: () => ({}) },
})
defineEmits(['back', 'edit'])

const statusMap = {
  normal: '正常',
  delayed: '延期',
  risk: '有风险',
  completed: '已完成',
}
</script>
