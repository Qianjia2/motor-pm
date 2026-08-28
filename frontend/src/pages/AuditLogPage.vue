<template>
  <div class="audit-log-page">
    <div class="page-header">
      <h2>操作审计日志</h2>
      <p class="subtitle">记录所有关键操作，追溯"谁在何时做了什么"</p>
    </div>

    <!-- Filters -->
    <el-card class="filter-card">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select v-model="filterType" placeholder="操作类型" clearable @change="loadLogs">
            <el-option label="全部类型" value="" />
            <el-option label="创建" value="create" />
            <el-option label="编辑" value="update" />
            <el-option label="删除" value="delete" />
            <el-option label="关闭" value="close" />
            <el-option label="替换" value="replace" />
            <el-option label="失效" value="deprecate" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filterEntity" placeholder="操作对象" clearable @change="loadLogs">
            <el-option label="全部对象" value="" />
            <el-option label="项目" value="project" />
            <el-option label="里程碑" value="milestone" />
            <el-option label="风险/问题" value="risk" />
            <el-option label="变更" value="change" />
            <el-option label="交付物" value="deliverable" />
            <el-option label="文档" value="document" />
            <el-option label="周报" value="report" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-select v-model="filterUser" placeholder="操作人" clearable filterable @change="loadLogs">
            <el-option label="全部人员" value="" />
            <el-option v-for="u in uniqueUsers" :key="u" :label="displayName(u)" :value="u" />
          </el-select>
        </el-col>
        <el-col :span="6">
          <el-button type="primary" @click="loadLogs" :icon="RefreshRight">刷新</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- Log Table -->
    <el-card>
      <el-table :data="logs" stripe size="small" style="width:100%">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{row}">
            <span class="time-text">{{ formatTime(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作人" width="120">
          <template #default="{row}">
            <span :title="row.username">{{ displayName(row.username) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作" width="90">
          <template #default="{row}">
            <el-tag :type="actionColor(row.action)" size="small">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="entity_type" label="对象" width="110">
          <template #default="{row}">
            <el-tag :type="entityColor(row.entity_type)" size="small" effect="plain">{{ entityLabel(row.entity_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="entity_name" label="对象名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="project_name" label="所属项目" width="160" show-overflow-tooltip />
        <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="perPage"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { RefreshRight } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const authStore = useAuthStore()
const displayName = authStore.displayName

const logs = ref([])
const page = ref(1)
const perPage = ref(50)
const total = ref(0)

const filterType = ref('')
const filterEntity = ref('')
const filterUser = ref('')

const uniqueUsers = computed(() => [...new Set(logs.value.map(l => l.username))].sort())

const actionMap = { create:'创建', update:'编辑', delete:'删除', close:'关闭', replace:'替换', deprecate:'失效' }
const actionColorMap = { create:'success', update:'warning', delete:'danger', close:'info', replace:'primary', deprecate:'danger' }
const entityMap = { project:'项目', milestone:'里程碑', risk:'风险/问题', change:'变更', deliverable:'交付物', document:'文档', report:'周报' }
const entityColorMap = { project:'', milestone:'warning', risk:'danger', change:'info', deliverable:'success', document:'primary', report:'' }

function actionLabel(a) { return actionMap[a] || a }
function actionColor(a) { return actionColorMap[a] || 'info' }
function entityLabel(e) { return entityMap[e] || e }
function entityColor(e) { return entityColorMap[e] || '' }
function formatTime(t) { return t ? t.replace('T',' ').substring(0,19) : '' }

async function loadLogs() {
  const params = { page: page.value, per_page: perPage.value }
  if (filterType.value) params.entity_type = filterType.value === 'risk' ? 'risk' : filterType.value
  if (filterEntity.value) params.entity_type = filterEntity.value
  if (filterUser.value) params.username = filterUser.value
  const res = await api.get('/audit-logs', { params })
  logs.value = res.data.data
  total.value = res.data.total
}

onMounted(loadLogs)
</script>

<style scoped>
.audit-log-page { padding: 20px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px 0; font-size: 20px; }
.subtitle { color: #909399; font-size: 13px; margin: 0; }
.filter-card { margin-bottom: 12px; }
.time-text { font-family: monospace; font-size: 12px; color: #606266; }
.pagination-wrap { margin-top: 16px; display:flex; justify-content:center; }
</style>
