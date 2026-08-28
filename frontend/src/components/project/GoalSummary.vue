<template>
  <el-card shadow="never">
    <template #header>
      <div class="flex-between">
        <strong>目标与终点 (Section A)</strong>
        <el-button type="primary" link size="small" @click="$emit('edit')">编辑</el-button>
      </div>
    </template>
    <el-descriptions :column="2" border size="small">
      <el-descriptions-item label="最终交付物" :span="2">
        {{ project.final_deliverable || '未填写' }}
      </el-descriptions-item>
      <el-descriptions-item label="验收标准" :span="2">
        {{ project.acceptance_criteria || '未填写' }}
      </el-descriptions-item>
      <el-descriptions-item label="要解决的问题" :span="2">
        {{ project.problem_statement || '未填写' }}
      </el-descriptions-item>
      <el-descriptions-item label="对齐目标">
        {{ project.aligned_target || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="截止日期类型">
        <el-tag v-if="project.deadline_type" size="small">{{ project.deadline_type }}</el-tag>
        <span v-else>-</span>
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup>
defineProps({ project: { type: Object, default: () => ({}) } })
defineEmits(['edit'])
</script>
