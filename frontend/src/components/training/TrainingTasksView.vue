<template>
  <div class="tasks-view">
    <!-- 统计卡 -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total }}</div>
        <div class="stat-label">总任务数</div>
      </div>
      <div class="stat-card ok">
        <div class="stat-num">{{ stats.approved }}</div>
        <div class="stat-label">已完成</div>
      </div>
      <div class="stat-card wait">
        <div class="stat-num">{{ stats.submitted }}</div>
        <div class="stat-label">待审核</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.progress_pct }}%</div>
        <div class="stat-label">完成率</div>
        <el-progress :percentage="stats.progress_pct" :stroke-width="6" :show-text="false" :color="'#10b981'" />
      </div>
      <div class="stat-card point">
        <div class="stat-num">{{ stats.points_earned }}<span class="unit"> / {{ stats.points_total }}</span></div>
        <div class="stat-label">累计积分</div>
      </div>
    </div>

    <!-- 等级分布 -->
    <div v-if="stats.by_level?.length" class="level-bar">
      <div v-for="lv in stats.by_level" :key="lv.level" class="level-seg">
        <span class="level-name">{{ lv.level }}</span>
        <el-progress :percentage="lv.total ? Math.round(lv.approved * 100 / lv.total) : 0"
          :stroke-width="8" :show-text="true" :color="levelColor(lv.level)" style="flex:1" />
        <span class="level-count">{{ lv.approved }}/{{ lv.total }}</span>
      </div>
    </div>

    <!-- 管理员工具栏 -->
    <div v-if="auth.isAdmin" class="admin-bar">
      <el-button size="small" type="primary" plain icon="Plus" @click="openManage">管理任务</el-button>
      <el-badge :value="reviews.length" :hidden="reviews.length === 0">
        <el-button size="small" type="warning" plain @click="openReviews">审核任务</el-button>
      </el-badge>
    </div>

    <!-- 任务分组 -->
    <div v-loading="loading">
      <el-empty v-if="!loading && groups.length === 0" description="暂无任务，管理员可先配置培训任务" />
      <el-card v-for="g in groups" :key="g.category" class="group-card" shadow="never">
        <template #header>
          <div class="group-head">
            <span class="group-name">{{ g.category }}</span>
            <el-progress :percentage="groupPct(g)" :stroke-width="6" :show-text="false" :color="'#3b82f6'" class="group-progress" />
            <span class="group-count">{{ groupDone(g) }}/{{ g.tasks.length }} 完成</span>
          </div>
        </template>
        <div v-for="t in g.tasks" :key="t.id" class="task-row">
          <el-tag size="small" :type="levelColor(t.level)" effect="dark" class="level-tag">{{ t.level_name }}</el-tag>
          <div class="task-info">
            <div class="task-title">{{ t.title }}</div>
            <div class="task-desc">{{ t.description }}</div>
            <div v-if="t.required_target" class="task-required">
              <el-tag size="small" type="warning" effect="plain">需先进入「{{ t.required_target_name || t.category }}」实际操作后才可提交</el-tag>
            </div>
          </div>
          <span class="task-points">+{{ t.points }}分</span>
          <div class="task-action">
            <el-tag v-if="t.my_status === 'approved'" type="success" effect="plain" size="small">✓ 已通过</el-tag>
            <el-tag v-else-if="t.my_status === 'submitted'" type="info" effect="plain" size="small">待审核</el-tag>
            <el-button v-else-if="t.my_status === 'rejected'" size="small" type="danger" plain
              @click="openSubmit(t)">被驳回 · 重新提交</el-button>
            <el-button v-else size="small" type="primary" @click="openSubmit(t)">
              {{ t.required_target && !t.my_visited ? '去实操' : '提交完成' }}
            </el-button>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 提交完成弹窗 -->
    <el-dialog v-model="submitVisible" :title="`提交完成：${submitTask?.title || ''}`" width="520px" destroy-on-close>
      <el-alert v-if="submitTask?.my_review_note" type="warning" :closable="false" show-icon
        :title="`上次驳回原因：${submitTask.my_review_note}`" style="margin-bottom:12px" />
      <el-form label-width="90px">
        <el-form-item label="等级">
          <el-tag :type="levelColor(submitTask?.level)" size="small" effect="dark">{{ submitTask?.level_name }}</el-tag>
        </el-form-item>
        <el-form-item label="完成说明" required>
          <el-input v-model="submitNote" type="textarea" :rows="4"
            placeholder="请说明你是如何完成该任务的（如：已创建 3 个客户并录入沟通记录），便于审核" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="submitVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="doSubmit">提交审核</el-button>
      </template>
    </el-dialog>

    <!-- 管理员:任务管理弹窗 -->
    <el-dialog v-model="manageVisible" title="培训任务管理" width="860px" destroy-on-close>
      <div class="manage-head">
        <div class="manage-form">
          <el-input v-model="form.category" placeholder="所属模块" style="width:140px" />
          <el-select v-model="form.level" style="width:100px">
            <el-option label="基础" value="basic" />
            <el-option label="进阶" value="intermediate" />
            <el-option label="高级" value="advanced" />
          </el-select>
          <el-input v-model="form.title" placeholder="任务标题" style="width:200px" />
          <el-input v-model="form.description" placeholder="任务说明(怎么算完成)" style="width:260px" />
          <el-input-number v-model="form.points" :min="1" :max="999" style="width:90px" />
          <el-select v-model="form.required_target" placeholder="关联模块(提交前需实操)" clearable filterable
            allow-create default-first-option style="width:200px">
            <el-option v-for="(name, path) in moduleTargets" :key="path" :label="`${name} (${path})`" :value="path" />
          </el-select>
          <el-button type="primary" :loading="saving" @click="saveTask">{{ editingId ? '保存修改' : '＋ 新增' }}</el-button>
          <el-button v-if="editingId" @click="resetForm">取消编辑</el-button>
        </div>
      </div>
      <el-table :data="allTasks" size="small" max-height="380">
        <el-table-column prop="category" label="模块" width="120" />
        <el-table-column label="等级" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="levelColor(row.level)" effect="dark">{{ row.level_name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="title" label="任务" min-width="160" show-overflow-tooltip />
        <el-table-column prop="description" label="说明" min-width="200" show-overflow-tooltip />
        <el-table-column prop="points" label="分值" width="60" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link size="small" type="primary" @click="editTask(row)">编辑</el-button>
            <el-button link size="small" type="danger" @click="removeTask(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 管理员:审核弹窗 -->
    <el-dialog v-model="reviewVisible" title="审核任务提交" width="680px" destroy-on-close>
      <el-empty v-if="reviews.length === 0" description="暂无待审核的提交" />
      <div v-for="r in reviews" :key="r.progress_id" class="review-item">
        <div class="review-head">
          <el-tag size="small" :type="levelColor(r.level)" effect="dark">{{ r.level_name }}</el-tag>
          <span class="review-title">{{ r.title }}</span>
          <span class="review-points">+{{ r.points }}分</span>
          <span class="review-user">{{ auth.displayName(r.username) }}</span>
          <span class="review-time">{{ r.submitted_at }}</span>
        </div>
        <div class="review-note">{{ r.submit_note }}</div>
        <div class="review-actions">
          <el-button size="small" type="success" @click="doReview(r, 'approve')">通过</el-button>
          <el-button size="small" type="danger" @click="doReview(r, 'reject')">驳回</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../../stores/auth'
import api from '../../api'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const groups = ref([])
const stats = ref({ total: 0, approved: 0, submitted: 0, progress_pct: 0, points_earned: 0, points_total: 0, by_level: [] })
const reviews = ref([])

const submitVisible = ref(false)
const submitTask = ref(null)
const submitNote = ref('')
const submitting = ref(false)

const manageVisible = ref(false)
const allTasks = ref([])
const editingId = ref(null)
const saving = ref(false)
const form = ref({ category: '', level: 'basic', title: '', description: '', points: 10, required_target: '' })

const reviewVisible = ref(false)

// 可选关联模块(与后端 MODULE_TARGETS 保持一致)
const moduleTargets = {
  '/projects': '项目列表',
  '/management-weekly': '管理层周报',
  '/tasks-milestones': '任务与里程碑',
  '/gantt': '甘特图',
  '/milestones': '里程碑',
  '/clients': '客户管理',
  '/bom': 'BOM 管理',
  '/issue-risks': '问题风险管理',
  '/phase-gate-review': '阶段门评审',
  '/product-tech': '产品技术库',
  '/knowledge': '知识库',
  '/resources': '资源中心',
  '/training': '培训学习',
  '/reports': '报表中心',
  '/ai': 'AI 助手',
}

function levelColor(lv) {
  return { basic: 'success', intermediate: 'primary', advanced: 'warning' }[lv] || 'info'
}

async function loadAll() {
  loading.value = true
  try {
    const [s, t] = await Promise.all([
      api.get('/training/tasks/stats'),
      api.get('/training/tasks'),
    ])
    stats.value = s.data
    groups.value = t.data.items || []
    if (auth.isAdmin) {
      const r = await api.get('/training/tasks/reviews')
      reviews.value = r.data.items || []
    }
  } finally { loading.value = false }
}

function groupDone(g) { return g.tasks.filter(t => t.my_status === 'approved').length }
function groupPct(g) { return g.tasks.length ? Math.round(groupDone(g) * 100 / g.tasks.length) : 0 }

async function openSubmit(t) {
  // 任务配置了关联模块且 7 天内未访问过:先跳转实操,访问后(路由上报)再回来提交
  if (t.required_target && !t.my_visited) {
    try {
      await ElMessageBox.confirm(
        `该任务要求先在「${t.required_target_name || t.category}」页面实际操作后才能提交，现在前往该模块？`,
        '需要先实操',
        { confirmButtonText: '前往操作', cancelButtonText: '暂不', type: 'warning' }
      )
    } catch { return }
    router.push(t.required_target)
    return
  }
  submitTask.value = t
  submitNote.value = t.my_status === 'rejected' ? t.my_submit_note || '' : ''
  submitVisible.value = true
}

async function doSubmit() {
  if (!submitNote.value.trim()) { ElMessage.warning('请填写完成说明'); return }
  submitting.value = true
  try {
    await api.post(`/training/tasks/${submitTask.value.id}/submit`, { note: submitNote.value.trim() })
    ElMessage.success('已提交，等待管理员审核')
    submitVisible.value = false
    await loadAll()
  } catch (e) {
    const detail = e.response?.data?.detail
    if (detail && typeof detail === 'object') {
      // 后端校验实操痕迹失败:提示并跳转到关联模块
      ElMessage.warning(detail.message || '提交失败，请先在关联模块实际操作')
      if (detail.target) router.push(detail.target)
    } else {
      ElMessage.error(detail || '提交失败')
    }
  } finally { submitting.value = false }
}

async function openManage() {
  manageVisible.value = true
  const r = await api.get('/training/tasks')
  allTasks.value = r.data.items.flatMap(g => g.tasks)
}

function resetForm() {
  editingId.value = null
  form.value = { category: '', level: 'basic', title: '', description: '', points: 10, required_target: '' }
}
function editTask(row) {
  editingId.value = row.id
  form.value = {
    category: row.category, level: row.level, title: row.title, description: row.description,
    points: row.points, required_target: row.required_target || '',
  }
}
async function saveTask() {
  if (!form.value.category.trim() || !form.value.title.trim()) {
    ElMessage.warning('请填写所属模块和任务标题'); return
  }
  saving.value = true
  try {
    if (editingId.value) {
      await api.put(`/training/tasks/${editingId.value}`, form.value)
      ElMessage.success('已保存')
    } else {
      await api.post('/training/tasks', form.value)
      ElMessage.success('已新增')
    }
    resetForm()
    await openManage()
    await loadAll()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally { saving.value = false }
}
async function removeTask(row) {
  try {
    await ElMessageBox.confirm(`确定删除任务「${row.title}」？该任务的所有提交记录将一并删除。`, '删除确认', { type: 'warning' })
  } catch { return }
  await api.delete(`/training/tasks/${row.id}`)
  ElMessage.success('已删除')
  await openManage()
  await loadAll()
}

function openReviews() { reviewVisible.value = true }

async function doReview(r, action) {
  let note = ''
  if (action === 'reject') {
    try {
      const { value } = await ElMessageBox.prompt('请填写驳回原因（将反馈给提交人）', '驳回', {
        confirmButtonText: '确认驳回', cancelButtonText: '取消', inputPlaceholder: '如：截图未体现完整流程',
        inputValidator: v => (v && v.trim() ? true : '请填写驳回原因'),
      })
      note = value.trim()
    } catch { return }
  }
  await api.post(`/training/tasks/progress/${r.progress_id}/review`, { action, note })
  ElMessage.success(action === 'approve' ? `已通过「${r.title}」` : '已驳回')
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.tasks-view { min-height: 200px; }
.stat-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 14px; }
.stat-card {
  background: #fff; border: 1px solid var(--border, #e5e7eb); border-radius: 10px;
  padding: 14px 16px; text-align: center;
}
.stat-card .stat-num { font-size: 26px; font-weight: 800; color: #1f3a5f; line-height: 1.2; }
.stat-card .unit { font-size: 13px; color: #b0b3b8; font-weight: 400; }
.stat-card .stat-label { font-size: 12px; color: #909399; margin-top: 2px; }
.stat-card.ok .stat-num { color: #10b981; }
.stat-card.wait .stat-num { color: #e6a23c; }
.stat-card.point .stat-num { color: #8b5cf6; }

.level-bar { background: #fff; border: 1px solid var(--border, #e5e7eb); border-radius: 10px; padding: 12px 16px; margin-bottom: 14px; }
.level-seg { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.level-name { width: 48px; font-size: 13px; font-weight: 600; color: #4b5563; }
.level-count { width: 44px; font-size: 12px; color: #909399; text-align: right; }

.admin-bar { display: flex; gap: 12px; margin-bottom: 12px; }

.group-card { margin-bottom: 12px; border-radius: 10px; }
.group-card :deep(.el-card__header) { padding: 10px 16px; }
.group-head { display: flex; align-items: center; gap: 12px; }
.group-name { font-size: 14px; font-weight: 700; color: #1f3a5f; }
.group-progress { flex: 1; max-width: 260px; }
.group-count { font-size: 12px; color: #909399; }

.task-row { display: flex; align-items: center; gap: 12px; padding: 10px 4px; border-bottom: 1px solid #f4f5f7; }
.task-row:last-child { border-bottom: none; }
.level-tag { width: 44px; text-align: center; }
.task-info { flex: 1; min-width: 0; }
.task-title { font-size: 13px; font-weight: 600; color: #333; }
.task-desc { font-size: 12px; color: #909399; margin-top: 2px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.task-required { margin-top: 4px; }
.task-points { font-size: 12px; color: #8b5cf6; font-weight: 600; white-space: nowrap; }
.task-action { width: 120px; text-align: right; }

.manage-head { margin-bottom: 12px; }
.manage-form { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.review-item { border: 1px solid #f0f1f3; border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; }
.review-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.review-title { font-weight: 600; font-size: 14px; }
.review-points { font-size: 12px; color: #8b5cf6; }
.review-user { font-size: 12px; color: #3b82f6; }
.review-time { font-size: 12px; color: #b0b3b8; }
.review-note { font-size: 13px; color: #4b5563; background: #fafafa; border-radius: 8px; padding: 10px 12px; margin: 8px 0; }
.review-actions { text-align: right; }
</style>
