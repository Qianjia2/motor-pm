<template>
  <el-card shadow="hover">
    <template #header><strong>汇总三：难点归类</strong></template>

    <div v-if="data.length === 0" style="text-align:center;padding:40px;color:#67c23a">
      <el-icon :size="32"><CircleCheck /></el-icon>
      <p>当前无开放风险项</p>
    </div>

    <div v-else>
      <div v-for="(cat, idx) in data" :key="cat.category" class="difficulty-row">
        <div class="flex-between" style="margin-bottom:4px">
          <span style="font-weight:500">{{ cat.category }}</span>
          <span style="font-size:12px;color:#909399">{{ cat.count }} 项</span>
        </div>
        <div class="bar-wrap">
          <div
            class="bar-critical"
            :style="{ width: barWidth(cat.critical, maxCount) + '%' }"
            v-if="cat.critical > 0"
          >
            <span>{{ cat.critical }}</span>
          </div>
          <div
            class="bar-high"
            :style="{ width: barWidth(cat.high, maxCount) + '%', marginLeft: barWidth(cat.critical, maxCount) + '%' }"
            v-if="cat.high > 0"
          >
            <span>{{ cat.high }}</span>
          </div>
          <div
            class="bar-rest"
            :style="{ width: barWidth(cat.count - cat.critical - cat.high, maxCount) + '%', marginLeft: barWidth(cat.critical + cat.high, maxCount) + '%' }"
            v-if="cat.count - cat.critical - cat.high > 0"
          >
          </div>
        </div>
      </div>

      <div class="flex-between" style="margin-top:12px;font-size:11px;color:#909399">
        <span><span class="legend-box" style="background:#f56c6c"></span> 严重</span>
        <span><span class="legend-box" style="background:#e6a23c"></span> 高</span>
        <span><span class="legend-box" style="background:#c0c4cc"></span> 中/低</span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  data: { type: Array, default: () => [] },
})

const maxCount = computed(() => {
  return Math.max(1, ...props.data.map(d => d.count))
})

function barWidth(val, max) {
  return Math.max(0, (val / max) * 100)
}
</script>

<style scoped>
.difficulty-row {
  margin-bottom: 16px;
}
.bar-wrap {
  height: 24px;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  overflow: hidden;
  position: relative;
}
.bar-critical {
  background: #f56c6c;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  min-width: 0;
}
.bar-high {
  background: #e6a23c;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  position: absolute;
  top: 0;
}
.bar-rest {
  background: #c0c4cc;
  height: 100%;
  position: absolute;
  top: 0;
}
.legend-box {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 2px;
  vertical-align: middle;
  margin-right: 2px;
}
</style>
