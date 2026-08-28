<template>
  <el-card shadow="never">
    <template #header>
      <div class="flex-between">
        <strong>当前阻碍 (Section D)</strong>
        <el-button type="primary" link size="small" @click="$emit('edit')">编辑</el-button>
      </div>
    </template>

    <div v-if="!project.main_blocker" style="text-align:center;color:#67c23a;padding:20px">
      <el-icon :size="32"><CircleCheck /></el-icon>
      <p>当前无阻塞项</p>
    </div>

    <div v-else>
      <el-alert
        :title="'最大阻碍：' + project.main_blocker"
        type="error"
        :closable="false"
        show-icon
      />
      <el-descriptions v-if="project.blocker_duration" :column="2" border size="small" style="margin-top:12px">
        <el-descriptions-item label="持续时间">
          {{ project.blocker_duration }}
        </el-descriptions-item>
        <el-descriptions-item label="士气">
          <el-tag v-if="project.morale" :type="project.morale === '高' ? 'success' : project.morale === '中等' ? 'warning' : 'danger'" size="small">
            {{ project.morale }}
          </el-tag>
          <span v-else>-</span>
        </el-descriptions-item>
        <el-descriptions-item v-if="project.common_complaint" label="团队反馈" :span="2">
          {{ project.common_complaint }}
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- 关联风险项 -->
    <div v-if="risks.length" style="margin-top:12px">
      <div style="font-size:13px;font-weight:600;margin-bottom:8px">关联风险/问题</div>
      <div v-for="r in risks" :key="r.id" class="flex-between mb-sm" style="padding:8px;background:#f5f7fa;border-radius:4px">
        <div>
          <el-tag :type="r.type === 'risk' ? 'warning' : 'danger'" size="small" style="margin-right:6px">
            {{ r.type === 'risk' ? '风险' : '问题' }}
          </el-tag>
          <span style="font-size:13px">{{ r.title }}</span>
        </div>
        <StatusBadge :status="r.status" />
      </div>
    </div>
  </el-card>
</template>

<script setup>
import StatusBadge from '../common/StatusBadge.vue'

defineProps({
  project: { type: Object, default: () => ({}) },
  risks: { type: Array, default: () => [] },
})
defineEmits(['edit'])
</script>
