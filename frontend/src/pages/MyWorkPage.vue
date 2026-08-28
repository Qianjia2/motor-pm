<template>
  <div class="my-work-page">
    <div class="page-header">
      <h2>我的工作台</h2>
      <p class="subtitle">当前用户：{{ username }} | 参与 {{ myProjects.length }} 个项目</p>
    </div>

    <!-- Alert: Pending Reports -->
    <el-alert
      v-if="pendingReports.length"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:16px"
    >
      <template #title>
        <span style="font-weight:700">本周还有 {{ pendingReports.length }} 个项目未填周报</span>
      </template>
      <div v-for="p in pendingReports" :key="p.id" style="margin-top:4px">
        <el-link type="warning" :href="`/projects/${p.id}`">{{ p.code }}</el-link>
        {{ p.name }}
      </div>
    </el-alert>

    <el-row :gutter="16">
      <!-- Left column -->
      <el-col :span="16">
        <!-- Pending approval tasks -->
        <el-card v-if="pendingTasks.length" class="section-card">
          <template #header><span class="card-title danger">待办任务 ({{ pendingTasks.length }})</span></template>
          <div v-for="t in pendingTasks" :key="t.type + t.id" class="item-row">
            <el-tag :type="t.type==='gate_signoff'?'primary':t.type==='change_signoff'?'warning':'info'" size="small">
              {{ t.type==='gate_signoff'?'阶段门签核':t.type==='change_signoff'?'变更签核':'整改行动' }}
            </el-tag>
            <span class="item-name" :title="t.title">{{ t.title }}</span>
            <span v-if="t.created_at" style="font-size:11px;color:#909399;white-space:nowrap">{{ formatTime(t.created_at) }}</span>
            <el-link v-if="t.project_id" type="primary" :href="`/projects/${t.project_id}`" :underline="false">{{ t.project_name || '' }}</el-link>
            <el-link
              type="danger"
              :underline="false"
              style="font-size:12px;white-space:nowrap"
              :href="t.type==='gate_signoff' ? '/phase-gate-review?tab=signoffs'
                : t.type==='review_action' ? '/phase-gate-review?tab=tasks'
                : t.type==='change_signoff' ? `/projects/${t.project_id}?tab=changes`
                : `/projects/${t.project_id}`"
            >去处理</el-link>
          </div>
        </el-card>

        <!-- This week's WBS tasks -->
        <el-card class="section-card">
          <template #header><span class="card-title primary">本周任务 ({{ myTasks.length }})</span></template>
          <div v-if="myTasks.length === 0" style="color:#909399;text-align:center;padding:20px">
            暂无本周任务，去 <el-link type="primary" href="/my-work">WBS</el-link> 分配
          </div>
          <div v-for="t in myTasks" :key="t.id" class="item-row">
            <el-tag :type="t.status==='blocked'?'danger':t.status==='in_progress'?'primary':''" size="small">
              {{ t.status === 'blocked' ? '阻塞' : t.status === 'in_progress' ? '进行中' : '待开始' }}
            </el-tag>
            <el-progress :percentage="t.progress_pct" :stroke-width="4" style="width:60px" :show-text="false"
              :color="t.progress_pct>=80?'#10b981':'#3b82f6'" />
            <span class="item-name">{{ t.name }}</span>
            <span v-if="t.end_date" style="font-size:11px;color:#909399;white-space:nowrap">{{ t.end_date }}</span>
            <el-link type="primary" :href="`/projects/${t.project_id}`" :underline="false">{{ t.project_name || '' }}</el-link>
          </div>
        </el-card>

        <!-- My Risks/Issues -->
        <el-card v-if="myRisks.length" class="section-card">
          <template #header><span class="card-title warning">我负责的风险/问题 ({{ myRisks.length }})</span></template>
          <div v-for="r in myRisks" :key="r.id" class="item-row">
            <el-tag :type="r.type === 'issue' ? 'danger' : 'warning'" size="small">{{ r.type === 'issue' ? '问题' : '风险' }}</el-tag>
            <el-tag size="small">{{ r.status }}</el-tag>
            <span class="item-name">{{ r.title }}</span>
            <el-link v-if="r.project_id" type="primary" :href="`/projects/${r.project_id}?tab=risks`" :underline="false">{{ r.project_name || '' }}</el-link>
            <span v-else class="t-muted">{{ r.project_name || '' }}</span>
          </div>
        </el-card>

        <!-- 近期里程碑:近期要完成 + 刚完成的重大节点 -->
        <el-card class="section-card">
          <template #header><span class="card-title">近期里程碑 ({{ milestones.length }})</span></template>
          <div v-if="milestones.length === 0" style="color:#909399;text-align:center;padding:20px">暂无近期里程碑</div>
          <div v-for="m in milestones" :key="m.id" class="item-row">
            <el-tag :type="m.kind === 'completed' ? 'success' : (m.status === 'in_progress' ? 'primary' : '')" size="small">{{ m.date }}</el-tag>
            <span class="item-name">{{ m.name }}</span>
            <el-tag v-if="m.phase_name" size="small" effect="plain" type="info">{{ m.phase_name }}</el-tag>
            <el-tag size="small" effect="plain" :type="m.kind === 'completed' ? 'success' : ''">{{ m.kind === 'completed' ? '已完成' : (m.status === 'in_progress' ? '进行中' : '待开始') }}</el-tag>
            <span v-if="m.deliverables && m.deliverables.length" class="ms-deliver" :title="m.deliverables.join('、')">交付:{{ m.deliverables.join('、') }}</span>
            <el-link v-if="m.project_id" type="primary" :href="`/projects/${m.project_id}?tab=milestones`" :underline="false">{{ m.project_name || '' }}</el-link>
            <span v-else class="t-muted">{{ m.project_name || '' }}</span>
          </div>
        </el-card>
      </el-col>

      <!-- Right column -->
      <el-col :span="8">
        <!-- Training -->
        <el-card class="section-card">
          <template #header>
            <span class="card-title">培训学习</span>
            <el-link type="primary" :href="'/training'" :underline="false" style="float:right;font-size:12px">进入学习 →</el-link>
          </template>
          <div v-if="trainingStats.total === 0" style="color:#909399;text-align:center;padding:20px">
            暂无培训素材，管理员可在「培训学习」页上传
          </div>
          <div v-else class="item-row">
            <span class="item-name">共 {{ trainingStats.total }} 个素材</span>
            <el-tag size="small" type="danger" effect="plain">{{ trainingStats.videos }} 视频</el-tag>
            <el-tag size="small" type="primary" effect="plain">{{ trainingStats.manuals }} 手册</el-tag>
          </div>
          <div v-if="trainingStats.categories.length" class="item-row" style="flex-wrap:wrap;gap:6px">
            <el-tag v-for="c in trainingStats.categories.slice(0, 8)" :key="c" size="small" effect="plain" style="border:none;background:var(--bg)">{{ c }}</el-tag>
          </div>
        </el-card>

        <!-- My Projects -->
        <el-card class="section-card">
          <template #header><span class="card-title">我的项目</span></template>
          <div v-for="p in myProjects" :key="p.id" class="project-card-item">
            <el-link :href="`/projects/${p.id}`">
              <strong>{{ p.code }}</strong>
            </el-link>
            <div style="font-size:12px;color:#909399">{{ p.name }}</div>
            <div style="margin-top:4px">
              <el-progress :percentage="p.completion_pct || 0" :stroke-width="6" :show-text="false" />
              <span style="font-size:11px;color:#909399">{{ p.completion_pct || 0 }}%</span>
            </div>
          </div>
          <div v-if="myProjects.length === 0" style="color:#909399;text-align:center;padding:20px">暂无参与项目</div>
        </el-card>

        <!-- Recent Activity -->
        <el-card class="section-card">
          <template #header><span class="card-title">最近动态</span></template>
          <div v-for="l in recentLogs" :key="l.id" class="log-item">
            <span style="font-size:11px;color:#909399">{{ formatTime(l.created_at) }}</span>
            <span style="font-size:12px;margin-left:4px">{{ auth.displayName(l.username) }}</span>
            <el-tag size="small" style="margin-left:4px">{{ l.summary }}</el-tag>
          </div>
          <div v-if="recentLogs.length === 0" style="color:#909399;text-align:center;padding:20px">暂无动态</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const auth = useAuthStore()
const username = computed(() => auth.currentMemberName || auth.user?.username || '')
const myProjects = ref([])
const milestones = ref([])
const myRisks = ref([])
const pendingReports = ref([])
const myTasks = ref([])
const recentLogs = ref([])
const pendingTasks = ref([])
const trainingStats = ref({ total: 0, videos: 0, manuals: 0, categories: [] })

function formatTime(t) { return t ? t.replace('T',' ').substring(5,16) : '' }

onMounted(async () => {
  try {
    const res = await api.get('/my-work')
    const d = res.data
    myProjects.value = d.my_projects || []
    milestones.value = d.milestones || []
    myRisks.value = d.my_risks || []
    pendingReports.value = d.pending_reports || []
    myTasks.value = d.my_tasks || []
    recentLogs.value = d.recent_logs || []
    pendingTasks.value = d.pending_tasks || []
  } catch (e) {
    console.error('Failed to load my work', e)
  }
  try {
    const res = await api.get('/training/categories')
    const items = res.data.items || []
    trainingStats.value = {
      total: items.reduce((s, c) => s + c.count, 0),
      videos: items.reduce((s, c) => s + c.videos, 0),
      manuals: items.reduce((s, c) => s + c.manuals, 0),
      categories: items.map(c => c.category),
    }
  } catch (e) { /* 培训模块加载失败不影响工作台 */ }
})
</script>

<style scoped>
.my-work-page { padding: 20px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px 0; font-size: 20px; }
.subtitle { color: #909399; font-size: 13px; }
.section-card { margin-bottom: 12px; }
.card-title { font-weight: 700; font-size: 14px; }
.card-title.danger { color: #f56c6c; }
.card-title.warning { color: #e6a23c; }
.item-row { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid #f0f0f0; font-size:13px; }
.item-row:last-child { border-bottom:none; }
.item-name { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.ms-deliver { max-width:200px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#909399; font-size:12px; background:#f5f7fa; border-radius:4px; padding:1px 6px; }
.project-card-item { padding:8px 0; border-bottom:1px solid #f0f0f0; }
.project-card-item:last-child { border-bottom:none; }
.log-item { padding:4px 0; border-bottom:1px solid #fafafa; }
.log-item:last-child { border-bottom:none; }
</style>
