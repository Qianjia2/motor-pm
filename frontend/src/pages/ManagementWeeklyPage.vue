<template>
  <div class="mw-page">
    <h2 style="margin:0 0 4px;font-size:18px">管理层周报</h2>
    <p style="margin:0 0 16px;font-size:13px;color:var(--text-muted)">AI 自动收集所有活跃项目的最新周报 → 聚合生成管理层汇报</p>

    <div class="ctrl-row">
      <span>年度</span><el-input-number v-model="rpYear" :min="2020" :max="2030" size="small" />
      <span style="margin-left:10px">周次</span><el-input-number v-model="rpWeek" :min="1" :max="53" size="small" />
      <span class="week-date">{{ weekRange }}</span>
      <el-button type="primary" size="small" @click="genWeekly" :loading="rpLoading" style="margin-left:12px">
        🤖 AI 生成管理层周报
      </el-button>
      <el-button v-if="rpContent" size="small" @click="downloadRpt('md')">📥 .md</el-button>
      <el-button v-if="rpContent" size="small" @click="downloadRpt('docx')">📄 .docx</el-button>
    </div>

    <div class="stat-row" v-if="rpStats">
      <div class="stat"><em class="blue">{{ rpStats.project_count }}</em>活跃项目</div>
      <div class="stat"><em class="green">{{ rpStats.completion_pct }}%</em>完成率</div>
      <div class="stat"><em class="red">{{ rpStats.high_risk_count }}</em>高风险</div>
      <div class="stat"><em class="orange">{{ rpStats.late_milestones }}</em>逾期</div>
    </div>

    <div v-if="rpLoading" style="text-align:center;padding:40px;color:var(--text-muted)">AI 正在聚合数据，预计 1-2 分钟...</div>

    <div v-if="rpContent" class="result-box">
      <div class="result-title">{{ rpTitle }}</div>
      <div class="result-body" v-html="renderMd(rpContent)"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/index.js'

function isoWeekNow() {
  const d = new Date()
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return { year: date.getUTCFullYear(), week: Math.ceil((((date - yearStart) / 86400000) + 1) / 7) }
}
const cw = isoWeekNow()
const rpYear = ref(cw.year)
const rpWeek = ref(cw.week)
const rpLoading = ref(false)
const rpContent = ref('')
const rpTitle = ref('')
const rpStats = ref(null)

// ISO 8601: Monday of given year/week
function getMonday(year, week) {
  const jan4 = new Date(year, 0, 4)
  const jan4Day = jan4.getDay() || 7
  const firstMonday = new Date(jan4)
  firstMonday.setDate(jan4.getDate() - jan4Day + 1)
  return new Date(firstMonday.getTime() + (week - 1) * 7 * 86400000)
}
const weekRange = computed(() => {
  const mon = getMonday(rpYear.value, rpWeek.value)
  const sun = new Date(mon.getTime() + 6 * 86400000)
  const fmt = d => `${d.getMonth()+1}月${d.getDate()}日`
  return `${fmt(mon)} — ${fmt(sun)}`
})

function renderMd(text) {
  if (!text) return ''
  let html = text
  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  // Table: split by newlines, detect |...| rows
  const lines = html.split('\n')
  let result = []; let inTable = false; let tableRows = []
  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      if (!inTable) { inTable = true; tableRows = [] }
      if (trimmed.includes('---')) continue  // skip separator
      tableRows.push(trimmed)
    } else {
      if (inTable) {
        inTable = false
        result.push(renderTable(tableRows))
        tableRows = []
      }
      if (trimmed.startsWith('- ')) {
        result.push('• ' + trimmed.slice(2))
      } else {
        result.push(line)
      }
    }
  }
  if (inTable && tableRows.length) result.push(renderTable(tableRows))
  html = result.join('<br>')
  return html
}

function renderTable(rows) {
  let t = '<table style=\"border-collapse:collapse;width:100%;font-size:13px;margin:8px 0\">'
  for (let i = 0; i < rows.length; i++) {
    const cells = rows[i].split('|').filter(c => c.trim()).map(c => c.trim())
    const tag = i === 0 ? 'th' : 'td'
    const style = i === 0 ? 'background:#f0f7ff;font-weight:600;padding:6px 8px;text-align:left;border:1px solid #e5e7eb'
      : (i % 2 === 0 ? 'background:#f9fafb' : 'background:#fff') + ';padding:6px 8px;border:1px solid #e5e7eb'
    t += '<tr>'
    for (const cell of cells) {
      t += `<${tag} style=\"${style}\">${cell}</${tag}>`
    }
    t += '</tr>'
  }
  t += '</table>'
  return t
}

async function genWeekly() {
  rpLoading.value = true; rpContent.value = ''; rpStats.value = null
  try {
    const res = await api.get('/report-gen/management-weekly', { params: { year: rpYear.value, week: rpWeek.value }, timeout: 180000 })
    const d = res.data
    rpContent.value = d.report || d.content || ''
    rpTitle.value = d.title || '管理层周报'
    rpStats.value = {
      project_count: d.project_count || 0, completion_pct: d.completion_pct || 0,
      high_risk_count: d.high_risk_count || 0, late_milestones: d.late_milestones || 0,
    }
    ElMessage.success('管理层周报已生成')
  } catch (e) {
    ElMessage.error('生成失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'))
  }
  rpLoading.value = false
}

function downloadRpt(fmt) {
  if (!rpContent.value) return
  const blob = new Blob([rpContent.value], { type: 'text/markdown' })
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
  a.download = (rpTitle.value || '周报') + '.' + fmt; a.click()
}

onMounted(() => {
  const now = new Date()
  const lastWeek = new Date(now.getTime() - 7 * 86400000)
  rpYear.value = lastWeek.getFullYear()
  const jan1 = new Date(lastWeek.getFullYear(), 0, 1)
  rpWeek.value = Math.ceil(((lastWeek - jan1) / 86400000 + jan1.getDay() + 1) / 7)
})
</script>

<style scoped>
.mw-page { max-width: 900px; }
.ctrl-row { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; font-size: 13px; }
.week-date { font-size: 12px; color: var(--text-muted); }
.stat-row { display: flex; gap: 24px; margin-bottom: 16px; }
.stat { font-size: 12px; color: var(--text-muted); }
.stat em { font-size: 22px; font-weight: 700; font-style: normal; display: block; }
.stat em.blue { color: #3b82f6; } .stat em.green { color: #22c55e; } .stat em.red { color: #ef4444; } .stat em.orange { color: #f59e0b; }
.result-box { background: var(--bg); border-radius: 8px; padding: 20px; }
.result-title { font-size: 16px; font-weight: 700; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.result-body { font-size: 14px; line-height: 1.8; max-height: 600px; overflow-y: auto; }
</style>
