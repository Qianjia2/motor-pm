<template>
  <el-tag :type="tagType" size="small" effect="dark">
    {{ label }}
  </el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'normal' }
})

const map = {
  normal: { type: 'success', label: '正常' },
  risk: { type: 'warning', label: '有风险' },
  blocked: { type: 'danger', label: '阻塞' },
  completed: { type: 'success', label: '已完成' },
  in_progress: { type: 'primary', label: '进行中' },
  not_started: { type: 'info', label: '未开始' },
  pending: { type: 'info', label: '待处理' },
  open: { type: 'warning', label: '未处理' },
  closed: { type: 'info', label: '已关闭' },
  resolved: { type: 'success', label: '已解决' },
  pending_review: { type: 'warning', label: '待审核' },
  passed: { type: 'success', label: '通过' },
  failed: { type: 'danger', label: '未通过' },
}

const tagType = computed(() => map[props.status]?.type || 'info')
const label = computed(() => map[props.status]?.label || props.status)
</script>
