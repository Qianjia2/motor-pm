<template>
  <div class="tm-page">
    <h2 style="margin:0 0 16px;font-size:18px">任务与里程碑</h2>
    <el-tabs v-model="tab" type="border-card">
      <el-tab-pane label="甘特图" name="gantt" lazy>
        <GanttPage />
      </el-tab-pane>
      <el-tab-pane label="里程碑全景" name="milestones">
        <MilestonePage />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import GanttPage from './GanttPage.vue'
import MilestonePage from './MilestonePage.vue'

const tab = ref('milestones')
</script>

<style scoped>
.tm-page { max-width: 100%; }
</style>
