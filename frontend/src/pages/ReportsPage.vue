<template>
  <div class="rp-page">
    <h2 style="margin:0 0 4px;font-size:18px">报告中心</h2>
    <p style="margin:0 0 16px;font-size:13px;color:var(--text-muted)">模板库 · 项目报告</p>

    <el-tabs v-model="tab" type="border-card">
      <!-- Tab 1: Templates -->
      <el-tab-pane label="模板库" name="templates">
        <div class="tab-content">
          <p class="desc">管理报告模板，AI 生成报告时自动选用匹配的模板</p>
          <div style="margin-bottom:12px">
            <input type="file" ref="tplInput" accept=".docx,.doc" @change="uploadTpl" style="display:none" />
            <el-button type="primary" size="small" @click="$refs.tplInput.click()">+ 上传模板 (.docx)</el-button>
          </div>
          <el-table :data="templates" size="small" v-loading="tplLoading">
            <el-table-column prop="name" label="模板名称" />
            <el-table-column label="匹配报告类型" width="140">
              <template #default="{row}">{{ matchType(row.name) }}</template>
            </el-table-column>
            <el-table-column prop="updated" label="更新时间" width="110" />
            <el-table-column label="操作" width="160">
              <template #default="{row}">
                <el-button link size="small" @click="useTemplate(row)">使用</el-button>
                <el-button link size="small" @click="delTemplate(row.name)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 3: Project Reports -->
      <el-tab-pane label="项目报告" name="projects">
        <div class="tab-content">
          <p class="desc">进入具体项目 → 使用 AI 生成技术协议 / 阶段报告 / 结题报告 / 验收报告等</p>
          <el-button type="primary" size="small" @click="$router.push('/projects')">进入项目列表</el-button>
          <p style="margin-top:12px;font-size:13px;color:var(--text-muted)">
            进入项目详情 → 报告生成 → 选择报告类型 → AI 自动生成 → 下载 .docx/.pptx
          </p>
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/index.js'

const tab = ref('templates')

// ── Templates ──
const tplInput = ref(null)
const templates = ref([])
const tplLoading = ref(false)

async function loadTemplates() {
  tplLoading.value = true
  try { const res = await api.get('/report-gen/templates'); templates.value = Array.isArray(res.data) ? res.data : (res.data?.templates || []) } catch { templates.value = [] }
  tplLoading.value = false
}

async function uploadTpl(e) {
  const file = e.target.files?.[0]; if (!file) return
  const fd = new FormData(); fd.append('file', file)
  try {
    await api.post('/report-gen/templates/upload', fd)
    ElMessage.success('模板已上传'); loadTemplates()
  } catch (e) {
    ElMessage.error('上传失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  e.target.value = ''
}

async function delTemplate(name) {
  try {
    await ElMessageBox.confirm('删除此模板？', '确认', { type: 'warning' })
    await api.delete(`/report-gen/templates/${encodeURIComponent(name)}`)
    ElMessage.success('已删除'); loadTemplates()
  } catch {}
}

function matchType(fname) {
  const n = (fname || '').toLowerCase()
  if (n.includes('技术协议')||n.includes('tech')) return '技术协议'
  if (n.includes('阶段')||n.includes('phase')) return '阶段报告'
  if (n.includes('结题')||n.includes('final')) return '结题报告'
  if (n.includes('验收')||n.includes('accept')) return '验收报告'
  if (n.includes('需求')||n.includes('require')) return '需求报告'
  return '通用'
}

function useTemplate(row) {
  ElMessage.info('进入具体项目 → 报告生成 → 上传模板填充')
}

onMounted(() => { loadTemplates() })
</script>

<style scoped>
.rp-page { max-width: 960px; margin: 0 auto; }
.tab-content { padding: 12px 0; }
.desc { font-size: 13px; color: var(--text-muted); margin: 0 0 12px; }
.ctrl-row { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; font-size: 13px; }
.week-date { color: var(--text-muted); font-size: 12px; white-space: nowrap; }
.stat-row { display: flex; gap: 24px; margin-bottom: 12px; }
.stat { font-size: 12px; color: var(--text-muted); }
.stat em { font-size: 22px; font-weight: 700; font-style: normal; display: block; }
.stat em.blue { color: #3b82f6; } .stat em.green { color: #22c55e; } .stat em.red { color: #ef4444; } .stat em.orange { color: #f59e0b; }
.result-box { background: var(--bg); border-radius: 8px; padding: 20px; }
.result-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.result-body { font-size: 14px; line-height: 1.8; max-height: 600px; overflow-y: auto; }
</style>
