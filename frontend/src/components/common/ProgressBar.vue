<template>
  <el-progress
    :percentage="pct"
    :color="color"
    :stroke-width="10"
    :show-text="showText"
  />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  percentage: { type: Number, default: 0 },
  showText: { type: Boolean, default: true },
})

const pct = computed(() => Math.round(props.percentage || 0))
const color = computed(() => {
  if (pct.value >= 80) return '#67c23a'
  if (pct.value >= 40) return '#409eff'
  return '#e6a23c'
})
</script>
