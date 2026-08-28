<template>
  <el-card shadow="hover">
    <template #header>
      <div class="card-header">
        <strong>汇总一：项目一览</strong>
        <div>
          <el-radio-group v-model="filter" size="small" @change="$emit('filter', filter)">
            <el-radio-button value="">全部 ({{ total }})</el-radio-button>
            <el-radio-button value="normal">正常 ({{ normalCount }})</el-radio-button>
            <el-radio-button value="risk">有风险 ({{ riskCount }})</el-radio-button>
            <el-radio-button value="blocked">阻塞 ({{ blockedCount }})</el-radio-button>
          </el-radio-group>
        </div>
      </div>
    </template>

    <el-table :data="filteredData" stripe @row-click="goProject" row-style="cursor:pointer" highlight-current-row>
      <el-table-column type="index" label="#" width="40" />
      <el-table-column prop="code" label="编号" width="130" />
      <el-table-column prop="name" label="项目名称" min-width="220" show-overflow-tooltip />
      <el-table-column prop="manager" label="PM" width="90" />
      <el-table-column prop="phase" label="当前阶段" width="110" />
      <el-table-column label="完成率" width="170">
        <template #default="{row}">
          <el-progress
            :percentage="row.completion_pct"
            :stroke-width="8"
            :color="row.completion_pct >= 80 ? '#67c23a' : row.completion_pct >= 40 ? '#409eff' : '#e6a23c'"
          />
        </template>
      </el-table-column>
      <el-table-column label="状态灯" width="80" align="center">
        <template #default="{row}">
          <div
            class="traffic-light"
            :style="{background: row.status === 'normal' ? '#67c23a' : row.status === 'risk' ? '#e6a23c' : '#f56c6c'}"
            :title="row.status === 'normal' ? '正常' : row.status === 'risk' ? '有风险' : '阻塞'"
          ></div>
        </template>
      </el-table-column>
      <el-table-column prop="planned_end_date" label="计划完成" width="110" />
      <el-table-column prop="member_count" label="团队" width="70" align="center" />
      <el-table-column label="风险项" width="80" align="center">
        <template #default="{row}">
          <el-tag v-if="row.open_issues > 0" type="danger" size="small" effect="dark">{{ row.open_issues }}</el-tag>
          <span v-else style="color:#c0c4cc">0</span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  data: { type: Array, default: () => [] },
})
defineEmits(['filter'])

const router = useRouter()
const filter = ref('')

const total = computed(() => props.data.length)
const normalCount = computed(() => props.data.filter(d => d.status === 'normal').length)
const riskCount = computed(() => props.data.filter(d => d.status === 'risk').length)
const blockedCount = computed(() => props.data.filter(d => d.status === 'blocked').length)

const filteredData = computed(() => {
  if (!filter.value) return props.data
  return props.data.filter(d => d.status === filter.value)
})

function goProject(row) {
  router.push(`/projects/${row.id}`)
}
</script>

<style scoped>
.traffic-light {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  margin: 0 auto;
  box-shadow: 0 0 6px rgba(0,0,0,0.2);
}
</style>
