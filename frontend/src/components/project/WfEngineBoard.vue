<template>
  <div class="wfe">
    <div v-if="loading" class="wfe-loading">加载中…</div>

    <el-empty v-else-if="!data.supported" description="该项目暂无工作流模板" />

    <template v-else>
      <!-- 抬头：模板 + 进度 + 当前节点 -->
      <div class="wfe-head">
        <div class="wfe-head-main">
          <el-tag type="primary" effect="dark" size="small">{{ data.template.code }}</el-tag>
          <span class="wfe-tpl">{{ data.template.name }}</span>
          <el-tag size="small" type="info">v{{ data.template.current_version_no }}</el-tag>
          <el-tag v-if="data.template.is_migrated" size="small" type="warning">
            已从 v{{ data.template.base_version_no }} 迁移
          </el-tag>
        </div>
        <div class="wfe-head-side">
          <span class="wfe-me">我的角色：{{ (data.me.roles || []).join(' / ') || '非项目成员' }}</span>
          <el-tag v-if="data.me.is_pm" type="danger" size="small" effect="dark">项目经理 · 可强制拖拽</el-tag>
        </div>
      </div>

      <div class="wfe-bar">
        <el-progress :percentage="data.summary.percent" :stroke-width="14" style="flex:1">
          <span class="wfe-bar-txt">
            {{ data.summary.completed }} / {{ data.summary.total }} 个状态已完成
            <template v-if="data.summary.blocked"> · <b style="color:#f56c6c">{{ data.summary.blocked }} 个阻塞</b></template>
          </span>
        </el-progress>
      </div>

      <el-alert type="info" :closable="false" show-icon class="wfe-hint">
        <template #title>
          拖拽卡片到其它状态即可<span v-if="data.me.is_pm">强制流转</span><span v-else class="wfe-warn">（仅项目经理可强制拖拽）</span>；
          跳过必经验证节点时必须填写原因，全程留痕可回退。
        </template>
      </el-alert>

      <!-- 泳道 -->
      <div class="wfe-lanes">
        <div v-for="lane in data.lanes" :key="lane.lane" class="wfe-lane">
          <div class="wfe-lane-head">
            <span class="wfe-lane-code">{{ lane.lane }}</span>
            <span class="wfe-lane-name">{{ lane.lane_name }}</span>
            <span class="wfe-lane-cnt">{{ laneDone(lane) }}/{{ lane.states.length }}</span>
          </div>
          <div class="wfe-lane-body">
            <div
              v-for="s in lane.states"
              :key="s.state_code"
              class="wfe-node"
              :class="[`st-${s.runtime_status}`, { 'is-cur': s.state_code === data.current_state_code, 'is-gate': s.is_gate }]"
              :draggable="data.me.is_pm"
              @dragstart="onDragStart($event, s)"
              @dragover.prevent
              @drop="onDrop($event, s)"
              @click="open(s)"
            >
              <div class="wfe-node-top">
                <span class="wfe-seq">{{ s.node_seq }}</span>
                <span class="wfe-name">{{ s.name }}</span>
                <span v-if="s.is_gate" class="wfe-gate">门禁</span>
              </div>
              <div class="wfe-node-bot">
                <el-tag size="small" :type="tagOf(s.runtime_status)">{{ s.runtime_label }}</el-tag>
                <span class="wfe-sem">标准语义：{{ s.semantic_label }}</span>
              </div>
              <div v-if="s.assigned_roles && s.assigned_roles.length" class="wfe-roles">
                {{ s.assigned_roles.join(' · ') }}
              </div>
              <div v-if="s.last_changed_by" class="wfe-who">
                {{ s.last_changed_by }} · {{ fmt(s.last_changed_at) }}
                <el-tag v-if="s.status_source === 'force'" size="small" type="danger" effect="plain">强制</el-tag>
                <el-tag v-else-if="s.status_source === 'revert'" size="small" type="warning" effect="plain">已回退</el-tag>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 强制拖拽台账 -->
      <div class="wfe-logs">
        <div class="wfe-logs-head">
          <span>强制拖拽台账</span>
          <el-button size="small" text @click="loadLogs">刷新</el-button>
        </div>
        <el-table v-if="logs.length" :data="logs" size="small" max-height="260">
          <el-table-column prop="created_at" label="时间" width="160">
            <template #default="{ row }">{{ fmt(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="operator" label="操作人" width="110" />
          <el-table-column label="路径" min-width="220">
            <template #default="{ row }">
              {{ row.from_state_name || '—' }} → <b>{{ row.to_state_name }}</b>
            </template>
          </el-table-column>
          <el-table-column label="跳过" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.skipped_states.length" size="small" type="warning">{{ row.skipped_states.length }} 个</el-tag>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160" show-overflow-tooltip />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag v-if="row.is_reverted" size="small" type="warning">已回退</el-tag>
              <el-tag v-else size="small" type="success">生效中</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="110">
            <template #default="{ row }">
              <el-button
                v-if="!row.is_reverted && data.me.is_pm"
                size="small" type="danger" text
                @click="revert(row)"
              >回退</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无强制拖拽记录" :image-size="60" />
      </div>

      <!-- 节点详情抽屉 -->
      <el-drawer v-model="drawer" :title="cur ? cur.name : ''" size="460px">
        <div v-if="cur" class="wfe-drawer">
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="状态码">{{ cur.state_code }}</el-descriptions-item>
            <el-descriptions-item label="标准语义">
              <el-tag size="small">{{ cur.semantic_label }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="当前运行态">
              <el-tag size="small" :type="tagOf(cur.runtime_status)">{{ cur.runtime_label }}</el-tag>
              <span class="wfe-src">（{{ sourceLabel(cur.status_source) }}）</span>
            </el-descriptions-item>
            <el-descriptions-item label="负责角色">
              {{ (cur.assigned_roles || []).join(' · ') || '未配置' }}
            </el-descriptions-item>
            <el-descriptions-item label="最近变更">
              {{ cur.last_changed_by ? `${cur.last_changed_by} · ${fmt(cur.last_changed_at)}` : '—' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="wfe-perm">
            <div class="wfe-perm-title">我在这个状态上的权限</div>
            <div class="wfe-perm-atoms">
              <el-tag
                v-for="atom in permAtoms" :key="atom"
                :type="cur.can[atom] ? 'success' : 'info'"
                :effect="cur.can[atom] ? 'dark' : 'plain'"
                size="small"
              >{{ data.perm_labels[atom] }}{{ cur.can[atom] ? '✓' : '✗' }}</el-tag>
            </div>
            <div class="wfe-perm-reason">判定依据：{{ cur.perm_reason }}</div>
          </div>

          <div class="wfe-actions">
            <el-button
              v-if="nextOf(cur)" type="primary" :disabled="!cur.can.can_exit"
              @click="advance(cur, nextOf(cur))"
            >流转到「{{ nextOf(cur).name }}」</el-button>
            <el-button :disabled="!cur.can.can_exit" @click="setStatus(cur, 'blocked')">标记阻塞</el-button>
            <el-button :disabled="!cur.can.can_exit" @click="setStatus(cur, 'cancelled')">取消</el-button>
            <el-button v-if="cur.runtime_status === 'blocked'" type="success" :disabled="!cur.can.can_exit"
              @click="setStatus(cur, 'in_progress', '阻塞解除，恢复推进')">解除阻塞</el-button>
          </div>
          <div v-if="!cur.can.can_exit" class="wfe-noperm">
            你没有这个状态的退出权限，按钮已禁用——这是服务端强制的，前端只是提前显示。
          </div>
        </div>
      </el-drawer>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api/index.js'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  project: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['refresh'])

const loading = ref(true)
const data = ref({ supported: false, lanes: [], states: [], summary: {}, me: {}, template: {} })
const logs = ref([])
const drawer = ref(false)
const cur = ref(null)
const dragState = ref(null)

const permAtoms = computed(() => Object.keys(data.value.perm_labels || {}))

const TAG = {
  not_started: 'info', in_progress: 'primary', pending_review: 'warning',
  pending_verify: 'warning', completed: 'success', blocked: 'danger', cancelled: 'info',
}
const tagOf = s => TAG[s] || 'info'
const SRC = { auto: '自动推导', manual: '人工推进', force: '强制拖拽', revert: '回退还原' }
const sourceLabel = s => SRC[s] || s
const fmt = t => (t ? String(t).replace('T', ' ').slice(0, 16) : '—')
const laneDone = lane => lane.states.filter(s => s.runtime_status === 'completed').length

async function load() {
  loading.value = true
  try {
    const r = await api.get(`/projects/${props.projectId}/wf-engine`)
    data.value = r.data
    await loadLogs()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || e.message)
  } finally {
    loading.value = false
  }
}

async function loadLogs() {
  try {
    const r = await api.get(`/projects/${props.projectId}/wf-engine/force-drag-logs`)
    logs.value = r.data || []
  } catch (e) { /* 台账拉不到不影响主视图 */ }
}

function open(s) { cur.value = s; drawer.value = true }

// 下一个状态 = sort_order 紧邻的下一个。一期主干是线性链，按位置取即可。
function nextOf(s) {
  const ordered = [...(data.value.states || [])].sort((a, b) => a.sort_order - b.sort_order)
  const i = ordered.findIndex(x => x.state_code === s.state_code)
  return i >= 0 && i < ordered.length - 1 ? ordered[i + 1] : null
}

async function advance(s, to) {
  if (!to) return
  try {
    await api.post(`/projects/${props.projectId}/wf-engine/states/${s.state_code}/transition`,
      { to_state_code: to.state_code })
    ElMessage.success(`已流转到「${to.name}」`)
    drawer.value = false
    await load(); emit('refresh')
  } catch (e) { ElMessage.error(e?.response?.data?.detail || e.message) }
}

async function setStatus(s, status, presetReason) {
  let reason = presetReason || ''
  if (status === 'blocked' || status === 'cancelled') {
    try {
      const r = await ElMessageBox.prompt(
        status === 'blocked' ? '阻塞原因（必填，会进审计）' : '取消原因（必填，会进审计）',
        status === 'blocked' ? '标记阻塞' : '取消该状态',
        { inputPlaceholder: '例如：等客户确认接口定义', inputValidator: v => !!String(v || '').trim() || '必须填写原因' },
      )
      reason = r.value
    } catch (e) { return }
  }
  try {
    await api.post(`/projects/${props.projectId}/wf-engine/states/${s.state_code}/status`,
      { to_status: status, reason })
    ElMessage.success('已更新')
    drawer.value = false
    await load(); emit('refresh')
  } catch (e) { ElMessage.error(e?.response?.data?.detail || e.message) }
}

function onDragStart(e, s) {
  dragState.value = s
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

async function onDrop(e, target) {
  const src = dragState.value
  dragState.value = null
  if (!src || src.state_code === target.state_code) return
  if (!data.value.me.is_pm) {
    ElMessage.warning('只有项目经理可以强制拖拽')
    return
  }
  let reason = ''
  try {
    const r = await ElMessageBox.prompt(
      `强制把「${src.name}」拖到「${target.name}」需要填写原因——跳过的节点会被记录，并可回退。`,
      '强制拖拽',
      {
        inputPlaceholder: '例如：客户催进度，先过；已安排下周补验证',
        inputValidator: v => !!String(v || '').trim() || '必须填写原因',
      },
    )
    reason = r.value
  } catch (err) { return }

  try {
    const r = await api.post(`/projects/${props.projectId}/wf-engine/force-drag`,
      { to_state_code: target.state_code, reason })
    const n = (r.data.skipped || []).length
    ElMessage.success(n ? `已强制流转，跳过 ${n} 个节点（已记审计）` : '已强制流转')
    await load(); emit('refresh')
  } catch (err) { ElMessage.error(err?.response?.data?.detail || err.message) }
}

async function revert(row) {
  let reason = ''
  try {
    const r = await ElMessageBox.prompt(
      `回退这次强制拖拽（${row.from_state_name || '—'} → ${row.to_state_name}）？超 24 小时需填原因。`,
      '回退强制拖拽',
      { inputPlaceholder: '回退原因（可选）' },
    )
    reason = r.value
  } catch (e) { return }
  try {
    await api.post(`/projects/${props.projectId}/wf-engine/force-drag/${row.id}/revert`, { reason })
    ElMessage.success('已回退')
    await load(); emit('refresh')
  } catch (e) { ElMessage.error(e?.response?.data?.detail || e.message) }
}

onMounted(load)
watch(() => props.projectId, load)
</script>

<style scoped>
.wfe { padding: 4px 0; min-height: 320px; }
.wfe-loading { padding: 40px; text-align: center; color: #909399; }
.wfe-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
.wfe-head-main { display: flex; align-items: center; gap: 8px; }
.wfe-tpl { font-weight: 600; }
.wfe-me { color: #606266; font-size: 13px; margin-right: 8px; }
.wfe-bar { margin-bottom: 10px; }
.wfe-bar-txt { font-size: 12px; color: #606266; }
.wfe-hint { margin-bottom: 14px; }
.wfe-warn { color: #f56c6c; }

.wfe-lanes { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 8px; align-items: flex-start; }
.wfe-lane { min-width: 232px; flex: 1 0 232px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 8px; }
.wfe-lane-head { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border-bottom: 1px solid #ebeef5; }
.wfe-lane-code { font-family: monospace; font-size: 12px; color: #909399; }
.wfe-lane-name { font-weight: 600; font-size: 13px; flex: 1; }
.wfe-lane-cnt { font-size: 12px; color: #909399; }
.wfe-lane-body { padding: 8px; display: flex; flex-direction: column; gap: 8px; min-height: 60px; }

.wfe-node { background: #fff; border: 1px solid #e4e7ed; border-left: 3px solid #c0c4cc; border-radius: 6px; padding: 8px 10px; cursor: pointer; transition: box-shadow .15s, border-color .15s; }
.wfe-node:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }
.wfe-node[draggable="true"] { cursor: grab; }
.wfe-node.is-cur { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64,158,255,.18); }
.wfe-node.is-gate { border-style: dashed; }
.wfe-node.st-completed { border-left-color: #67c23a; }
.wfe-node.st-in_progress { border-left-color: #409eff; }
.wfe-node.st-pending_review, .wfe-node.st-pending_verify { border-left-color: #e6a23c; }
.wfe-node.st-blocked { border-left-color: #f56c6c; }
.wfe-node.st-cancelled { border-left-color: #909399; opacity: .65; }

.wfe-node-top { display: flex; align-items: center; gap: 6px; }
.wfe-seq { font-size: 11px; color: #fff; background: #c0c4cc; border-radius: 8px; padding: 0 6px; }
.wfe-name { font-size: 13px; font-weight: 500; flex: 1; line-height: 1.35; }
.wfe-gate { font-size: 11px; color: #e6a23c; border: 1px solid #e6a23c; border-radius: 3px; padding: 0 4px; }
.wfe-node-bot { display: flex; align-items: center; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
.wfe-sem { font-size: 11px; color: #909399; }
.wfe-roles { font-size: 11px; color: #606266; margin-top: 4px; }
.wfe-who { font-size: 11px; color: #a8abb2; margin-top: 4px; display: flex; align-items: center; gap: 4px; }

.wfe-logs { margin-top: 18px; }
.wfe-logs-head { display: flex; align-items: center; justify-content: space-between; font-weight: 600; font-size: 14px; margin-bottom: 8px; }

.wfe-drawer { display: flex; flex-direction: column; gap: 14px; }
.wfe-src { font-size: 12px; color: #909399; margin-left: 6px; }
.wfe-perm-title { font-weight: 600; font-size: 13px; margin-bottom: 6px; }
.wfe-perm-atoms { display: flex; gap: 6px; flex-wrap: wrap; }
.wfe-perm-reason { font-size: 12px; color: #909399; margin-top: 6px; }
.wfe-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.wfe-noperm { font-size: 12px; color: #f56c6c; }
</style>
