<template>
  <div>
    <!-- 周报头部 -->
    <el-row :gutter="16" class="mb-md">
      <el-col :span="4">
        <div class="form-label">年度</div>
        <el-input-number v-model="form.year" :min="2020" :max="2030" size="small" style="width:100%" @change="() => weekRange" />
      </el-col>
      <el-col :span="4">
        <div class="form-label">周次</div>
        <el-input-number v-model="form.week_number" :min="1" :max="53" size="small" style="width:100%" />
      </el-col>
      <el-col :span="4">
        <div class="form-label" style="font-size:11px;color:var(--text-muted);line-height:1.6">{{ weekRange }}</div>
      </el-col>
      <el-col :span="5">
        <div class="form-label">报告日期</div>
        <el-date-picker v-model="form.report_date" type="date" placeholder="选择日期" size="small" style="width:100%" value-format="YYYY-MM-DD" />
      </el-col>
      <el-col :span="5">
        <div class="form-label">填写人</div>
        <el-select v-model="form.reporter_id" placeholder="选择" size="small" style="width:100%">
          <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-col>
    </el-row>

    <!-- 总体基线 -->
    <div style="background:#f0f7ff;padding:12px 16px;border-radius:6px;margin-bottom:16px;border-left:4px solid #3b82f6">
      <div style="font-weight:600;font-size:14px;color:#1e3a5f;margin-bottom:8px">
        项目基线一页纸
        <el-button size="small" type="primary" link @click="aiFillBaseline" :loading="aiFilling" style="margin-left:8px">
          AI 自动补充
        </el-button>
      </div>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="本周围绕目标(去哪里)" label-width="140px">
            <el-input v-model="form.overall_progress" type="textarea" :rows="2" placeholder="本周要达成的项目目标/里程碑" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="关键成果" label-width="100px">
            <el-input v-model="form.key_accomplishments" type="textarea" :rows="2" placeholder="本周产出的关键成果" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="完成率" label-width="80px">
            <el-input v-model="form.completion_rate" placeholder="如 85%" size="small" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="当前阶段" label-width="80px">
            <el-input v-model="form.current_stage" placeholder="如 详细设计" size="small" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="整体状态" label-width="80px">
            <el-select v-model="form.overall_status" size="small" style="width:100%">
              <el-option label="正常" value="normal" />
              <el-option label="有风险" value="risk" />
              <el-option label="延期" value="delayed" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
    </div>

    <el-divider content-position="left">
      各技术线周进展滚动记录
      <span style="font-size:12px;color:#909399;font-weight:400;margin-left:8px">去哪里 → 在哪里 → 下一步 → 难点</span>
      <el-button type="warning" size="small" style="margin-left:12px" @click="showSmartSplit = true">✨ 智能拆解</el-button>
    </el-divider>

    <!-- 四段式表格：去哪里/在哪里/下一步/难点 -->
    <el-table :data="lineItems" stripe border style="width:100%">
      <el-table-column prop="line.name" label="技术线" width="100" fixed>
        <template #default="{row}">
          <el-tag :type="lineTagType(row.line_id)" size="small">{{ row.line?.name }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="去哪里（本周目标）" min-width="180">
        <template #default="{row, $index}">
          <el-input v-model="lineItems[$index].goal" type="textarea" :rows="2" placeholder="本周该技术线要达成的目标" resize="none" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="在哪里（实际进展）" min-width="200">
        <template #default="{row, $index}">
          <el-input v-model="lineItems[$index].this_week" type="textarea" :rows="2" placeholder="本周实际完成的工作" resize="none" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{row, $index}">
          <el-select v-model="lineItems[$index].status" size="small" style="width:80px">
            <el-option label="正常" value="normal" />
            <el-option label="延期" value="delayed" />
            <el-option label="有风险" value="risk" />
            <el-option label="已完成" value="completed" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="下一步（下周计划）" min-width="200">
        <template #default="{row, $index}">
          <el-input v-model="lineItems[$index].next_week" type="textarea" :rows="2" placeholder="下周计划的关键行动" resize="none" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="难点 / 阻塞" min-width="180">
        <template #default="{row, $index}">
          <el-input v-model="lineItems[$index].blocker" type="textarea" :rows="2" placeholder="当前困难/阻碍/需要协助的事项" resize="none" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="负责人" width="90">
        <template #default="{row, $index}">
          <el-input v-model="lineItems[$index].coordinator" placeholder="负责人" size="small" />
        </template>
      </el-table-column>
    </el-table>

    <!-- 智能拆解弹窗 -->
    <el-dialog v-model="showSmartSplit" title="智能拆解 - 粘贴工作内容自动分配到各技术线" width="700px">
      <div style="margin-bottom:12px;font-size:13px;color:#606266">
        粘贴周报草稿（如会议纪要、聊天记录、工作日志），系统自动识别每句话属于哪个技术线并填入对应行。
      </div>
      <el-input
        v-model="smartText"
        type="textarea"
        :rows="10"
        placeholder="粘贴工作内容，每行一条...&#10;&#10;例如：&#10;完成电磁方案最终版，效率仿真收敛&#10;PCB布局完成，发厂制板&#10;底层驱动代码完成CAN通信调试&#10;结构3D图通过评审，开始强度分析&#10;算法SIL仿真通过，准备HIL&#10;台架测试大纲编写完成"
      />
      <div style="margin-top:12px;font-size:12px;color:#909399">
        系统将根据关键词自动识别技术线：电磁/磁路/绕组→电机电磁 | 结构/3D/图纸→电机结构 | PCB/原理图/硬件→控制硬件 | 算法/仿真/模型→控制算法 | 软件/代码/通信→控制软件 | 测试/台架/验证→测试验证
      </div>
      <template #footer>
        <el-button @click="showSmartSplit = false">取消</el-button>
        <el-button type="primary" @click="doSmartSplit">开始拆解</el-button>
      </template>
    </el-dialog>

    <div style="margin-top:16px;display:flex;justify-content:space-between;align-items:center">
      <el-button @click="autoFill" size="small">根据上次周报自动填充</el-button>
        <el-upload :action="ocrUrl" :headers="uploadHeaders" :show-file-list="false"
          accept=".png,.jpg,.jpeg,.gif,.bmp,.webp" :on-success="onOcrResult"
          style="display:inline-block;margin-left:8px">
          <el-button type="warning" size="small" :loading="ocrLoading">📷 上传截图识别</el-button>
        </el-upload>
      <div>
        <el-button @click="$emit('cancel')">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">
          {{ isEdit ? '保存修改' : '提交周报' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, onMounted, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getLines, getTeamMembers, getLatestReport } from '../../api/index.js'
import api from '../../api/index.js'

const props = defineProps({
  projectId: { type: Number, required: true },
  reportData: { type: Object, default: null },
})

const emit = defineEmits(['submit', 'cancel'])

const submitting = ref(false)
const members = ref([])
const isEdit = ref(false)
const showSmartSplit = ref(false)
const smartText = ref('')
const ocrLoading = ref(false)

const ocrUrl = '/api/ocr/parse-chat'
const uploadHeaders = computed(() => ({ Authorization: `Bearer ${localStorage.getItem('access_token')}` }))
function onOcrBefore() { ocrLoading.value = true; return true }
function onOcrResult(res) {
  ocrLoading.value = false
  if (!res.ok) { ElMessage.warning(res.message); return }
  ElMessage.success(res.message)
  const p = res.parsed
  if (!p) return
  // Fill overall progress
  if (p.summary) form.overall_progress = (form.overall_progress || '') + '\n' + p.summary
  // Fill weekly items by matching line names
  const items = p.weekly_items || []
  for (const item of items) {
    const key = item.line || ''
    const li = lineItems.find(x =>
      (x.line?.name || '').includes(key) || (x.line?.short_name || '').includes(key)
    )
    if (li) {
      if (item.this_week) li.this_week = (li.this_week || '') + (li.this_week ? '；' : '') + item.this_week
      if (item.next_week) li.next_week = (li.next_week || '') + (li.next_week ? '；' : '') + item.next_week
      if (item.blocker) li.blocker = (li.blocker || '') + (li.blocker ? '；' : '') + item.blocker
      if (item.status && item.status !== 'normal') li.status = item.status
    }
  }
  ElMessage.success(`已自动填充 ${items.length} 条工作项`)
}
// Keyword matching rules for each technical line
const lineKeywords = {
  2: ['代码', '软件', '嵌入式', '通信', '刷写', '上位机', '固件', 'CAN', 'SPI', 'I2C', 'UART', '协议', 'RTOS', '中断', '定时器', '算法', '控制策略', 'FOC', 'SVPWM', 'PID', '前馈', '辨识', '观测器', '弱磁', 'MTPA'],
  3: ['硬件', 'PCB', '原理图', '电路', '制板', 'EMC', '器件', '焊接', 'layout', '电源', '驱动', 'MOS', 'IGBT', '采样', '隔离', '接口', '功率模块'],
  4: ['结构', '3D', '图纸', '机械', '强度', '散热', '热', '模态', '振动', '公差', '装配', '轴承', '壳体', '密封', '冷却', '水冷', '风冷'],
  5: ['电磁', '磁路', '磁钢', '绕组', '齿槽', '转矩', '效率', '损耗', '反电势', 'Maxwell', '磁密', '气隙', '磁阻', '涡流', '温升', '仿真', '模型', '参数', '电感', '磁链'],
  6: ['测试', '试验', '验证', '台架', 'NVH', '耐久', '标定', '验收', '出厂', '型式', '负载', '功率', '电流', '电压', '效率MAP', '温升试验', '振动试验'],
}

// For scoring, loop over keys
function classifyLine(text) {
  const scores = {}
  for (const lid of [2,3,4,5,6]) {
    scores[lid] = 0
    for (const kw of lineKeywords[lid]) {
      if (text.includes(kw)) scores[lid] += 1
    }
  }
  const best = Object.entries(scores).sort((a, b) => b[1] - a[1])[0]
  return best[1] > 0 ? parseInt(best[0]) : 0
}

function doSmartSplit() {
  if (!smartText.value.trim()) {
    ElMessage.warning('请先粘贴工作内容')
    return
  }

  // Split by newlines, filter empty
  const lines = smartText.value.split('\n').map(s => s.trim()).filter(Boolean)
  const grouped = { 2: [], 3: [], 4: [], 5: [], 6: [], 0: [] }

  for (const line of lines) {
    const lineId = classifyLine(line)
    grouped[lineId].push(line)
  }

  // Fill into lineItems
  let totalClassified = 0
  for (const lineId of [2, 3, 4, 5, 6]) {
    const items = grouped[lineId]
    if (items.length > 0) {
      totalClassified += items.length
      const idx = lineItems.findIndex(item => item.line_id === lineId)
      if (idx >= 0) {
        const existing = lineItems[idx].this_week || ''
        const newContent = items.join('；')
        lineItems[idx].this_week = existing ? existing + '；' + newContent : newContent
      }
    }
  }

  const unmatched = grouped[0].length

  let msg = `已拆解 ${totalClassified} 条到对应技术线`
  if (unmatched > 0) {
    msg += `，${unmatched} 条未能识别`
  }
  ElMessage.success(msg)
  showSmartSplit.value = false
  smartText.value = ''
}

const thisFriday = () => {
  const d = new Date()
  d.setDate(d.getDate() - d.getDay() + 5)
  return d.toISOString().slice(0, 10)
}

// ISO 8601 week number: week containing the first Thursday
function isoWeek(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  return Math.ceil((((date - yearStart) / 86400000) + 1) / 7)
}

const currentWeek = () => isoWeek(new Date())

// Get Monday of a given ISO year/week (Monday = day 1)
function getMonday(year, week) {
  const jan4 = new Date(year, 0, 4) // Jan 4 is always in week 1
  const jan4Day = jan4.getDay() || 7
  const firstMonday = new Date(jan4)
  firstMonday.setDate(jan4.getDate() - jan4Day + 1)
  return new Date(firstMonday.getTime() + (week - 1) * 7 * 86400000)
}

const weekRange = computed(() => {
  const mon = getMonday(form.year, form.week_number)
  const sun = new Date(mon.getTime() + 6 * 86400000)
  const fmt = (d) => `${d.getMonth()+1}月${d.getDate()}日`
  return fmt(mon) + ' — ' + fmt(sun)
})

const form = reactive({
  year: new Date().getFullYear(),
  week_number: currentWeek(),
  report_date: thisFriday(),
  reporter_id: null,
  overall_progress: '',
  key_accomplishments: '',
  completion_rate: '',
  current_stage: '',
  overall_status: 'normal',
})

const lineItems = reactive([])

const lineColors = ['', 'warning', 'info', '', 'danger', 'primary', 'success']
function lineTagType(lineId) {
  return lineColors[lineId] || 'info'
}

onMounted(async () => {
  const [linesRes, membersRes] = await Promise.all([getLines(), getTeamMembers()])
  members.value = membersRes.data

  // Initialize line items
  for (const line of linesRes.data) {
    lineItems.push({
      line_id: line.id,
      line: line,
      goal: '',
      this_week: '',
      next_week: '',
      status: 'normal',
      blocker: '',
      coordinator: '',
    })
  }

  // If editing
  if (props.reportData) {
    isEdit.value = true
    Object.assign(form, {
      year: props.reportData.year,
      week_number: props.reportData.week_number,
      report_date: props.reportData.report_date,
      reporter_id: props.reportData.reporter_id,
      overall_progress: props.reportData.overall_progress || '',
      key_accomplishments: props.reportData.key_accomplishments || '',
      completion_rate: props.reportData.completion_rate || '',
    })
    if (props.reportData.line_items) {
      for (const li of props.reportData.line_items) {
        const idx = lineItems.findIndex(item => item.line_id === li.line_id)
        if (idx >= 0) {
          lineItems[idx].goal = li.goal || ''
          lineItems[idx].this_week = li.this_week || ''
          lineItems[idx].next_week = li.next_week || ''
          lineItems[idx].status = li.status || 'normal'
          lineItems[idx].blocker = li.blocker || ''
          lineItems[idx].coordinator = li.coordinator || ''
        }
      }
    }
  } else {
    // Try auto-fill from latest report
    try {
      const res = await getLatestReport(props.projectId)
      if (res.data) {
        form.reporter_id = res.data.reporter_id
        form.completion_rate = res.data.completion_rate
        if (res.data.line_items) {
          for (const li of res.data.line_items) {
            const idx = lineItems.findIndex(item => item.line_id === li.line_id)
            if (idx >= 0 && li.next_week) {
              lineItems[idx].this_week = '（承接上周计划）' + li.next_week
              lineItems[idx].coordinator = li.coordinator
            }
          }
        }
      }
    } catch (e) { /* no previous report */ }
  }
})

async function autoFill() {
  try {
    const res = await getLatestReport(props.projectId)
    const lastReport = res.data?.report
    if (lastReport) {
      form.reporter_id = form.reporter_id || lastReport.reporter_id
      form.completion_rate = lastReport.completion_rate || form.completion_rate
      if (lastReport.line_items) {
        let filled = 0
        for (const li of lastReport.line_items) {
          const idx = lineItems.findIndex(item => item.line_id === li.line_id)
          if (idx >= 0 && li.next_week) {
            if (!lineItems[idx].goal) {
              lineItems[idx].goal = li.next_week
              filled++
            }
            lineItems[idx].coordinator = lineItems[idx].coordinator || li.coordinator
            if (li.blocker) {
              lineItems[idx].blocker = lineItems[idx].blocker || '（上周遗留：' + li.blocker + '）'
            }
          }
        }
      }
      ElMessage.success(filled > 0 ? `已填充 ${filled} 条本周目标` : '上期周报无下周计划可继承')
    } else {
      ElMessage.info('暂无上期周报')
    }
  } catch (e) {
    ElMessage.info('暂无上期周报')
  }
}

const aiFilling = ref(false)
async function aiFillBaseline() {
  const items = lineItems.filter(li => li.this_week || li.goal || li.next_week)
  if (!items.length) { ElMessage.warning('请先填写各技术线的进展内容'); return }
  aiFilling.value = true
  try {
    const lines = items.map(li => {
      const lname = li.line?.name || ''
      return `[${lname}] 目标:${li.goal||'无'} 进展:${li.this_week||'无'} 计划:${li.next_week||'无'} 阻塞:${li.blocker||'无'}`
    }).join('\n')
    const res = await api.post('/report-gen/ai-fill-baseline', { lines, project_name: '' })
    if (res.data) {
      if (res.data.overall) form.overall_progress = res.data.overall
      if (res.data.accomplishments) form.key_accomplishments = res.data.accomplishments
      if (res.data.completion_rate) form.completion_rate = res.data.completion_rate
      if (res.data.stage) form.current_stage = res.data.stage
      if (res.data.status) form.overall_status = res.data.status
      ElMessage.success('基线已自动补充')
    }
  } catch(e) { ElMessage.error('AI补充失败') }
  aiFilling.value = false
}

function submit() {
  const data = {
    year: form.year,
    week_number: form.week_number,
    report_date: form.report_date || null,
    overall_progress: form.overall_progress || '',
    key_accomplishments: form.key_accomplishments || '',
    completion_rate: form.completion_rate || null,
    reporter_id: form.reporter_id || null,
    line_items: lineItems.map(li => ({
      line_id: li.line_id,
      goal: li.goal || '',
      this_week: li.this_week || '',
      next_week: li.next_week || '',
      status: li.status || 'normal',
      blocker: li.blocker || '',
      coordinator: li.coordinator || '',
    })),
  }
  emit('submit', data)
}
</script>

<style scoped>
.form-label { font-size: 12px; color: var(--text-secondary); margin-bottom: 4px; }
</style>
