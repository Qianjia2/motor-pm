<template>
  <el-card shadow="never">
    <template #header>
      <div class="flex-between">
        <strong>下一步行动 (Section C)</strong>
        <el-button type="primary" link size="small" @click="$emit('edit')">编辑</el-button>
      </div>
    </template>

    <div v-if="!hasData" style="text-align:center;color:#c0c4cc;padding:20px">暂无数据，点击编辑添加</div>

    <div v-else>
      <div v-if="project.main_blocker" class="mb-md" style="padding:10px;background:#fef0f0;border-radius:6px">
        <div style="font-size:12px;color:#f56c6c;font-weight:600">近期行动</div>
        <div style="margin-top:4px">{{ project.main_blocker }}</div>
      </div>

      <el-table v-if="nextSteps.length" :data="nextSteps" size="small" stripe>
        <el-table-column type="index" label="#" width="40" />
        <el-table-column prop="action" label="行动项" min-width="200" />
        <el-table-column prop="owner" label="负责人" width="80" />
        <el-table-column prop="deadline" label="截止" width="100" />
        <el-table-column label="状态" width="80">
          <template #default="{row}">
            <StatusBadge :status="row.status" />
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import StatusBadge from '../common/StatusBadge.vue'

const props = defineProps({ project: { type: Object, default: () => ({}) } })
defineEmits(['edit'])

const hasData = computed(() => props.project.main_blocker)

const nextSteps = computed(() => {
  return []
})
</script>
