<template>
  <div class="page">
    <div class="page-header">
      <h2>模版资料库</h2>
      <p class="sub">报告生成模板管理 — 上传模板后，AI 生成对应类型报告时自动匹配使用</p>
    </div>

    <div class="toolbar">
      <el-upload
        :http-request="handleUpload"
        :show-file-list="false"
        accept=".docx"
      >
        <el-button type="primary">+ 上传模板</el-button>
      </el-upload>
      <span style="margin-left:12px;font-size:13px;color:var(--text-muted)">
        已有 {{ templates.length }} 个模板
      </span>
    </div>

    <el-table :data="templates" style="margin-top:16px" v-loading="loading" empty-text="暂无模板，请上传 .docx 文件">
      <el-table-column prop="name" label="模板名称" min-width="200">
        <template #default="{row}">
          <span style="font-weight:500">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column label="匹配报告类型" width="280">
        <template #default="{row}">
          <el-tag
            v-for="rt in getMatchedTypes(row.name)"
            :key="rt"
            size="small"
            style="margin-right:4px"
            type="info"
          >{{ rt }}</el-tag>
          <span v-if="!getMatchedTypes(row.name).length" style="color:var(--text-muted);font-size:12px">未匹配（将作为通用模板）</span>
        </template>
      </el-table-column>
      <el-table-column label="文件大小" width="120">
        <template #default="{row}">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column prop="updated" label="上传时间" width="170" />
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{row}">
          <el-button type="danger" text size="small" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />
    <div class="matching-rules">
      <h4>自动匹配规则</h4>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
        模板文件名包含以下关键词时，AI 生成对应类型报告将自动使用该模板
      </p>
      <el-table :data="matchingRules" size="small" max-height="340">
        <el-table-column prop="type" label="报告类型" width="160" />
        <el-table-column prop="keywords" label="匹配关键词（文件名含任一即匹配）">
          <template #default="{row}">
            <el-tag v-for="kw in row.keywords" :key="kw" size="small" style="margin-right:4px">{{ kw }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const templates = ref([])
const loading = ref(false)

const matchingRules = [
  { type: '技术协议', keywords: ['技术协议', 'tech', 'agreement'] },
  { type: '阶段报告', keywords: ['阶段报告', '阶段', 'stage'] },
  { type: '结题报告', keywords: ['结题报告', '结题', 'final'] },
  { type: '验收报告', keywords: ['验收报告', '验收', 'acceptance'] },
  { type: '风险分析报告', keywords: ['风险分析', '风险', 'risk'] },
  { type: '周报汇总', keywords: ['周报汇总', '周报', 'weekly'] },
  { type: '需求报告', keywords: ['需求报告', '需求', 'requirement'] },
]

function getMatchedTypes(name) {
  const n = name.toLowerCase()
  return matchingRules.filter(r => r.keywords.some(k => n.includes(k.toLowerCase()))).map(r => r.type)
}

function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

async function loadTemplates() {
  loading.value = true
  try {
    const r = await api.get('/report-gen/templates')
    templates.value = r.data || []
  } catch (e) {
    ElMessage.error('加载模板列表失败')
  } finally { loading.value = false }
}

async function handleUpload({ file }) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    await api.post('/report-gen/templates/upload', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success(`模板 "${file.name}" 已保存`)
    await loadTemplates()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '上传失败，请确认是 .docx 格式')
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除模板 "${row.name}"？`, '确认删除', { type: 'warning' })
    await api.delete(`/report-gen/templates/${row.name}`)
    ElMessage.success('已删除')
    await loadTemplates()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

onMounted(() => { loadTemplates() })
</script>

<style scoped>
.page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; }
.sub { color: var(--text-secondary); font-size: 13px; margin: 0; }
.toolbar { display: flex; align-items: center; margin-top: 16px; }
.matching-rules { background: #f9fafb; padding: 16px; border-radius: 8px; }
.matching-rules h4 { margin: 0 0 4px; }
</style>
