<template>
  <el-table :data="projects" class="ledger-table" :row-class-name="rowClass" @row-click="r => $emit('open', r)">
    <el-table-column label="项目名称" min-width="220">
      <template #default="{ row }">
        <div class="t-name link" @click.stop="goDetail(row)">{{ row.name }}</div>
        <div class="t-code">{{ row.code }}</div>
      </template>
    </el-table-column>
    <el-table-column label="客户" min-width="110">
      <template #default="{ row }">
        <span v-if="row.client?.name" class="t-link" @click.stop="router.push('/clients')">{{ row.client?.name }}</span>
        <span v-else class="t-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="项目经理" width="110">
      <template #default="{ row }">
        <span v-if="row.pm" class="t-pm link" title="项目团队（概览）" @click.stop="goTab(row, 'overview')">{{ row.pm }}</span>
        <span v-else class="t-muted">—</span>
      </template>
    </el-table-column>
    <el-table-column label="状态" width="90">
      <template #default="{ row }">
        <span class="t-status">
          <span class="dot" :class="'dot-' + res(row.overall_status)"></span>
          {{ statusLabel(row.overall_status) }}
        </span>
      </template>
    </el-table-column>
    <el-table-column label="优先级" width="80">
      <template #default="{ row }">
        <span v-if="row.priority === 'P0'" class="tag tag-red">P0</span>
        <span v-else-if="row.priority === 'P1'" class="tag tag-orange">P1</span>
        <span v-else class="t-muted">{{ row.priority }}</span>
      </template>
    </el-table-column>
    <el-table-column label="开始日期" width="105" prop="start_date" />
    <el-table-column label="计划截止" width="105" prop="planned_end_date" />
    <el-table-column label="实际结束" width="105" prop="actual_end_date" />
    <el-table-column label="完成率" width="130">
      <template #default="{ row }">
        <div class="t-pct link" @click.stop="goTab(row, 'milestones')">
          <el-progress :percentage="row.completion_pct || 0" :stroke-width="5"
            :color="row.completion_pct >= 80 ? '#10b981' : row.completion_pct >= 40 ? '#3b82f6' : '#f59e0b'" />
        </div>
      </template>
    </el-table-column>
    <el-table-column label="操作" width="90" fixed="right">
      <template #default="{ row }">
        <span class="t-actions" @click.stop>
          <el-button link size="small" @click="$emit('clone', row)" title="复制">📋</el-button>
          <el-button link size="small" type="danger" @click="$emit('delete', row)" title="删除">✕</el-button>
        </span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup>
import { useRouter } from 'vue-router'

const props = defineProps({
  projects: { type: Array, default: () => [] },
})
const emit = defineEmits(['open', 'clone', 'delete'])
const router = useRouter()

function res(s) { return s === 'blocked' ? 'blocked' : s === 'at_risk' ? 'risk' : 'normal' }
function statusLabel(s) { if (s === 'blocked') return '阻塞'; if (s === 'at_risk') return '有风险'; return '正常' }
function goDetail(row) { emit('open', row) }
function goTab(row, tab) { router.push({ path: `/projects/${row.id}`, query: { tab } }) }
function rowClass({ row }) {
  return row.overall_status === 'blocked' ? 'row-blocked' : row.overall_status === 'at_risk' ? 'row-risk' : ''
}
</script>

<style scoped>
.ledger-table { border-radius: var(--radius); }
.ledger-table :deep(.el-table__row) { cursor: pointer; }
.ledger-table :deep(.row-blocked td.el-table__cell) { background: #fef2f2; }
.ledger-table :deep(.row-risk td.el-table__cell) { background: #fffbeb; }
.ledger-table :deep(.row-blocked:hover td.el-table__cell) { background: #fef2f2; }
.ledger-table :deep(.row-risk:hover td.el-table__cell) { background: #fffbeb; }
.ledger-table :deep(.el-table__row:hover td.el-table__cell) { background: #f0f7ff; }
.t-name { font-size: 13px; font-weight: 600; color: var(--text); }
.t-code { font-size: 12px; color: var(--text-muted); font-family: monospace; }
.t-status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.t-pct { max-width: 110px; }
.t-actions { display: inline-flex; gap: 2px; }
.t-muted { color: var(--text-muted); font-size: 12px; }
.t-pm { font-size: 12px; color: var(--primary); font-weight: 500; }
.t-link { font-size: 12px; color: var(--primary); cursor: pointer; }
.t-link:hover { text-decoration: underline; }
.link { cursor: pointer; }
.link:hover { text-decoration: underline; }
.t-name.link:hover { color: var(--primary); }
</style>
