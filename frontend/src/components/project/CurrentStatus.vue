<template>
  <el-card shadow="never">
    <template #header><strong>当前状态 (Section B)</strong></template>
    <el-row :gutter="16">
      <el-col :span="12">
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">完成率</div>
          <ProgressBar :percentage="project.completion_pct" />
        </div>
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">状态</div>
          <StatusBadge :status="project.overall_status" />
        </div>
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">人员</div>
          <span>{{ project.member_count || 0 }} 人</span>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">预算</div>
          <span v-if="project.budget_total">
            <el-progress :percentage="budgetPct" :stroke-width="8" style="width:150px;display:inline-block" />
            {{ (project.budget_spent || 0) / 10000 }}万 / {{ project.budget_total / 10000 }}万
          </span>
          <span v-else style="color:#c0c4cc">未设置</span>
        </div>
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">团队士气</div>
          <el-tag v-if="project.morale" :type="moraleType" size="small">{{ project.morale }}</el-tag>
          <span v-else style="color:#c0c4cc">未评估</span>
        </div>
        <div class="mb-md">
          <div style="color:#909399;font-size:12px;margin-bottom:4px">成功信心</div>
          <span>{{ project.success_confidence || '未评估' }}</span>
        </div>
      </el-col>
    </el-row>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from '../common/StatusBadge.vue'
import ProgressBar from '../common/ProgressBar.vue'

const props = defineProps({ project: { type: Object, default: () => ({}) } })

const budgetPct = computed(() => {
  if (!props.project.budget_total) return 0
  return Math.round((props.project.budget_spent || 0) / props.project.budget_total * 100)
})

const moraleType = computed(() => {
  const map = { '高': 'success', '中等': 'warning', '低': 'danger' }
  return map[props.project.morale] || 'info'
})
</script>
