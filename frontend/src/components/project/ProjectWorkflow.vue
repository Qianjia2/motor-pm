<template>
  <!-- 项目工作流:把 PHASE_NODES 的步骤按本项目渲染成一条有状态的流程 -->
  <div class="pw">
    <div v-if="loading" style="padding:40px;text-align:center;color:var(--text-muted)">加载中…</div>

    <!-- 页签本身已经按项目开放过一轮,正常进不来这里;真进来就是有人直连接口 -->
    <el-empty v-else-if="!data.supported" description="本项目暂未开放工作流视图" />

    <template v-else>
      <!-- 我的工作台:进项目第一眼先回答「我该干什么」,两种视图下都在 -->
      <MyWorkbench :me="data.me || {}" :phases="data.phases"
        @go-deliverable="goDeliverable" @go-gate="goGate" @confirm="confirmStep" />

      <!-- 总览 + 视图切换 -->
      <div class="pw-summary">
        <div class="stat"><b>{{ data.summary.steps_done }}</b><span>/ {{ data.summary.steps_total }} 步已完成</span></div>
        <div class="stat"><b>{{ data.summary.required_approved }}</b><span>/ {{ data.summary.required_total }} 份必交已批准</span></div>
        <div class="stat"><b>{{ data.summary.phases_passed }}</b><span>/ {{ data.summary.phases_total }} 个阶段已放行</span></div>
        <div class="spacer" />
        <el-radio-group v-model="view" size="small">
          <el-radio-button value="graph">编排图</el-radio-button>
          <el-radio-button value="list">清单</el-radio-button>
        </el-radio-group>
        <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
      </div>

      <!-- 编排图:4 个阶段并排,一眼看全流程卡在哪 -->
      <WorkflowGraph v-if="view === 'graph'" :phases="data.phases" :my-role="myRole"
        @go-deliverable="goDeliverable" @go-gate="goGate"
        @confirm="confirmStep" @unconfirm="unconfirmStep" />

      <!-- 清单:按阶段逐个展开的详细列表 -->
      <el-tabs v-else v-model="activePhase" class="pw-tabs">
        <el-tab-pane v-for="ph in data.phases" :key="ph.phase_code" :name="ph.phase_code">
          <template #label>
            <span class="tab-label">
              {{ ph.phase_name }}
              <el-tag size="small" :type="gateTagType(ph.gate_state)" effect="dark" class="tab-tag">
                {{ ph.gate_state_label }}
              </el-tag>
            </span>
          </template>

          <div class="pw-phase">
            <!-- 阶段进度 + 门禁 -->
            <div class="pw-gate">
              <div class="gate-line">
                <span class="gate-title">{{ ph.phase_code }} 阶段进度</span>
                <el-progress :percentage="ph.progress.percent" :stroke-width="14" style="flex:1" />
                <span class="gate-cnt">{{ ph.progress.steps_done }}/{{ ph.progress.steps_total }} 步</span>
              </div>
              <div class="gate-line">
                <span class="gate-title">门径 {{ ph.gate?.name || '-' }}</span>
                <el-tag :type="gateTagType(ph.gate_state)" effect="dark">{{ ph.gate_state_label }}</el-tag>
                <span v-if="ph.signoff?.initiated_by" class="muted">发起人 {{ ph.signoff.initiated_by }}</span>
                <span v-if="ph.gate_review_date" class="muted">评审日期 {{ ph.gate_review_date }}</span>
              </div>

              <!-- 两级签核状态 -->
              <div v-if="ph.signoff?.l1 || ph.signoff?.l2" class="gate-line">
                <span class="gate-title">签核</span>
                <el-tag v-for="lv in [1, 2]" :key="lv" size="small"
                  :type="signTagType(ph.signoff['l' + lv])" effect="plain">
                  {{ lv }} 级 {{ ph.signoff['l' + lv]?.signer_name || '未指派' }} ·
                  {{ signLabel(ph.signoff['l' + lv]) }}
                </el-tag>
              </div>

              <!-- 缺件:门禁真正的卡点,逐条列出来(含不在任何步骤上的必交项) -->
              <div v-if="ph.progress.missing_required.length" class="gate-missing">
                <div class="missing-title">
                  <el-icon><WarningFilled /></el-icon>
                  还差 {{ ph.progress.missing_required.length }} 份必交交付物未批准,门禁不能发起
                </div>
                <div class="missing-list">
                  <span v-for="m in ph.progress.missing_required" :key="m" class="missing-item">{{ m }}</span>
                </div>
              </div>
              <div v-else class="gate-line">
                <el-icon color="#22c55e"><CircleCheckFilled /></el-icon>
                <span class="muted">必交交付物已齐,{{ ph.progress.can_initiate_signoff ? '可以发起门禁签署' : '门禁已发起或已放行' }}</span>
              </div>

              <div class="gate-line">
                <el-button v-if="ph.progress.can_initiate_signoff" type="primary" size="small"
                  @click="goGate">去发起门禁签署</el-button>
                <span v-else-if="!ph.progress.missing_required.length" class="muted">
                  签核流程在「阶段门径」页处理
                </span>
              </div>
            </div>

            <!-- 步骤 -->
            <div v-for="step in ph.steps" :key="step.seq" class="step"
              :class="['s-' + step.state, { 's-mine': isMine(step) }]">
              <div class="step-bar">
                <el-tag :type="stateTagType(step.state)" effect="dark" size="small">{{ step.state_label }}</el-tag>
                <span class="src" :title="srcTitle(step)">依据：{{ srcLabel(step) }}</span>
                <el-tag v-if="isMine(step)" size="small" type="success" effect="plain">我的角色</el-tag>
                <el-tag v-if="step.definition_gap" size="small" type="warning" effect="plain">
                  本库未配置对应交付物标准
                </el-tag>
                <!-- 线下步骤的人工确认只是留痕:有交付物标准的步骤,状态仍按交付物算 -->
                <el-tag v-if="step.confirm" size="small" type="success" effect="plain">
                  {{ step.confirm.confirmed_by }} 已确认
                  <template v-if="step.confirm.confirmed_at"> · {{ step.confirm.confirmed_at.slice(0, 10) }}</template>
                </el-tag>
                <el-tag v-if="step.confirm_with_pending" size="small" type="warning" effect="dark">
                  材料未批完，门禁仍会拦截
                </el-tag>
                <div class="step-actions">
                  <el-button v-if="step.actions.can_confirm" type="primary" link size="small"
                    @click="confirmStep(ph.phase_code, step)">确认已完成</el-button>
                  <el-popconfirm v-if="step.actions.can_unconfirm" title="撤销这条确认?"
                    @confirm="unconfirmStep(ph.phase_code, step)">
                    <template #reference>
                      <el-button type="danger" link size="small">撤销确认</el-button>
                    </template>
                  </el-popconfirm>
                </div>
              </div>

              <!-- 复用的流程节点卡片:谁做/做什么/产出什么/交给谁 -->
              <ProcessNode :node="step.node" :my-role="myRole" />

              <!-- 这一步的交付物 -->
              <div v-if="step.standards.length" class="dels">
                <div v-for="st in step.standards" :key="st.standard_name" class="del-row">
                  <el-icon :color="st.satisfied ? '#22c55e' : '#d1d5db'">
                    <component :is="st.satisfied ? CircleCheckFilled : CircleClose" />
                  </el-icon>
                  <span class="del-name">{{ st.standard_name }}</span>
                  <el-tag size="small" :type="st.required ? 'danger' : 'info'" effect="plain">
                    {{ st.required === null ? '未配置' : st.required ? '必交' : '选交' }}
                  </el-tag>
                  <el-tag size="small" :type="delTagType(st.status)" effect="plain">{{ delLabel(st.status) }}</el-tag>
                  <span v-if="st.owner_name" class="muted">{{ st.owner_name }}</span>
                  <span v-if="st.submitted_date" class="muted">{{ st.submitted_date }}</span>
                  <el-button link type="primary" size="small" @click="goDeliverable(step)">去处理</el-button>
                </div>
              </div>
              <div v-else class="dels-empty">
                这一步没有对应的交付物标准，完成情况以人工确认为准
              </div>
            </div>

            <!-- 不在任何步骤上的交付物标准:门禁照样认,不能藏起来 -->
            <div v-if="ph.unmapped_standards.length" class="unmapped">
              <div class="unmapped-title">
                <el-icon><InfoFilled /></el-icon>
                不挂在任何步骤上的交付物标准（{{ ph.unmapped_standards.length }} 条）
                <span class="muted">门禁仍然按它们判断,其中必交项没批准一样过不了</span>
              </div>
              <div v-for="u in ph.unmapped_standards" :key="u.standard_id" class="del-row">
                <el-icon :color="u.satisfied ? '#22c55e' : '#d1d5db'">
                  <component :is="u.satisfied ? CircleCheckFilled : CircleClose" />
                </el-icon>
                <span class="del-name">{{ u.name }}</span>
                <el-tag size="small" :type="u.required ? 'danger' : 'info'" effect="plain">
                  {{ u.required ? '必交' : '选交' }}
                </el-tag>
                <el-tag size="small" :type="delTagType(u.status)" effect="plain">{{ delLabel(u.status) }}</el-tag>
                <el-tag v-if="u.extra" size="small" type="warning" effect="plain">库里多出的一条</el-tag>
                <span v-if="!u.declared && !u.extra" class="muted">未归类</span>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Refresh, WarningFilled, CircleCheckFilled, CircleClose, InfoFilled,
} from '@element-plus/icons-vue'
import api from '../../api/index.js'
import ProcessNode from '../training/ProcessNode.vue'
import MyWorkbench from './MyWorkbench.vue'
import WorkflowGraph from './WorkflowGraph.vue'

const props = defineProps({
  projectId: { type: [Number, String], required: true },
  project: { type: Object, default: () => ({}) },
  currentMemberId: { type: [Number, String], default: null },
})
const emit = defineEmits(['refresh', 'goDeliverable', 'goGate'])

const loading = ref(true)
const data = ref({ supported: false, phases: [], summary: {} })
const activePhase = ref('')
const projectMembers = ref([])
// 默认编排图:进项目先看全局"卡在哪",再决定要不要翻清单
const view = ref('graph')

// 我的项目角色(可能挂多个),用于把"我负责的步骤"标出来。
// 注意:项目详情页透传的 members 是人员档案(getTeamMembers),不带项目角色,
// 所以这里单独取项目成员。
const myRoles = computed(() => {
  const id = props.currentMemberId
  if (!id) return []
  return projectMembers.value
    .filter(m => Number(m.member_id) === Number(id))
    .map(m => m.role?.name)
    .filter(Boolean)
})
const myRole = computed(() => myRoles.value[0] || '')
function isMine(step) {
  const roles = step.node?.roles || []
  return myRoles.value.some(r => roles.includes(r))
}

const STATE_TAG = {
  done: 'success', in_progress: 'primary', pending_confirm: 'warning',
  blocked: 'danger', not_started: 'info',
}
const GATE_TAG = {
  passed: 'success', waived: 'success', l1_pending: 'warning', l2_pending: 'warning',
  rejected: 'danger', not_initiated: 'info',
}
const DEL_TAG = {
  approved: 'success', submitted: 'primary', reviewed: 'primary',
  rejected: 'danger', missing: 'info', not_submitted: 'info',
}
const DEL_LABEL = {
  approved: '已批准', submitted: '已提交', reviewed: '已审核',
  rejected: '已驳回', missing: '未提交', not_submitted: '未提交',
}
const SRC_LABEL = { deliverable: '交付物状态', gate: '签核记录', manual: '人工确认' }
const SRC_TITLE = {
  deliverable: '这一步有没有做完，看的是它对应的交付物批准情况',
  gate: '这一步是阶段门禁，状态来自两级签核记录',
  manual: '平台没有这一步的数据，由人确认后留痕',
}

const stateTagType = s => STATE_TAG[s] || 'info'
const gateTagType = s => GATE_TAG[s] || 'info'
const delTagType = s => DEL_TAG[s] || 'info'
const delLabel = s => DEL_LABEL[s] || s
const srcLabel = s => SRC_LABEL[s.state_source] || s.state_source
const srcTitle = s => SRC_TITLE[s.state_source] || ''

function signLabel(r) {
  if (!r) return '未指派'
  return { pending: '待签', approved: '已签', rejected: '已驳回' }[r.status] || r.status
}
function signTagType(r) {
  if (!r) return 'info'
  return { pending: 'warning', approved: 'success', rejected: 'danger' }[r.status] || 'info'
}

async function load() {
  loading.value = true
  try {
    const [r] = await Promise.all([
      api.get(`/projects/${props.projectId}/workflow`),
      api.get(`/projects/${props.projectId}/members`)
        .then(m => { projectMembers.value = m.data || [] })
        .catch(() => { projectMembers.value = [] }),
    ])
    data.value = r.data || { supported: false, phases: [] }
    const codes = (data.value.phases || []).map(p => p.phase_code)
    if (!codes.includes(activePhase.value)) {
      // 默认停在第一个还没放行的阶段,其次最后一个
      const cur = data.value.phases.find(
        p => !['passed', 'waived'].includes(p.gate_state) && p.progress.steps_done < p.progress.steps_total)
      activePhase.value = cur ? cur.phase_code : (codes[codes.length - 1] || '')
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '工作流加载失败')
  } finally {
    loading.value = false
  }
}

// 收 phase_code 而不是整个阶段对象:工作台和编排图都只拿得到一个步骤,
// 让它们各自去凑阶段对象不如直接把阶段码传进来。
async function confirmStep(phaseCode, step) {
  try {
    const { value } = await ElMessageBox.prompt(
      `确认「${step.node.name}」已完成？可填写说明（选填）`,
      '确认步骤完成',
      { confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：已于 9/10 现场完成，纪要见附件' })
    await api.post(`/projects/${props.projectId}/workflow/steps/${phaseCode}/${step.seq}/confirm`,
      { note: value || null })
    ElMessage.success('已确认')
    await load()
    emit('refresh')
  } catch (e) {
    if (e === 'cancel' || e === 'close') return
    ElMessage.error(e?.response?.data?.detail || '确认失败')
  }
}

async function unconfirmStep(phaseCode, step) {
  try {
    await api.delete(`/projects/${props.projectId}/workflow/steps/${phaseCode}/${step.seq}/confirm`)
    ElMessage.success('已撤销确认')
    await load()
    emit('refresh')
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '撤销失败')
  }
}

function goDeliverable(step) {
  emit('goDeliverable', step)
}
function goGate() {
  emit('goGate')
}

watch(() => props.projectId, load)
onMounted(load)
defineExpose({ load })
</script>

<style scoped>
.pw { display: flex; flex-direction: column; gap: 12px; }
.pw-summary { display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  padding: 10px 14px; background: var(--el-fill-color-lighter); border-radius: 8px; }
.pw-summary .stat { font-size: 13px; color: var(--text-muted); }
.pw-summary .stat b { font-size: 17px; color: var(--el-color-primary); margin-right: 3px; }
.pw-summary .spacer { flex: 1; }
.tab-label { display: inline-flex; align-items: center; gap: 6px; }
.tab-tag { transform: scale(.85); }

.pw-gate { border: 1px solid var(--el-border-color-lighter); border-radius: 8px;
  padding: 12px 14px; margin-bottom: 14px; display: flex; flex-direction: column; gap: 9px; }
.gate-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 13px; }
.gate-title { font-weight: 700; color: #374151; min-width: 96px; }
.gate-cnt { font-size: 12.5px; color: var(--text-muted); }
.muted { color: var(--text-muted); font-size: 12.5px; }

.gate-missing { background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; padding: 8px 10px; }
.missing-title { display: flex; align-items: center; gap: 6px; color: #b91c1c;
  font-size: 13px; font-weight: 600; margin-bottom: 6px; }
.missing-list { display: flex; flex-wrap: wrap; gap: 6px; }
.missing-item { background: #fff; border: 1px solid #fecaca; color: #b91c1c;
  border-radius: 4px; padding: 1px 7px; font-size: 12px; }

.step { border-left: 3px solid var(--el-border-color); padding-left: 12px; margin-bottom: 6px; }
.step.s-done { border-left-color: #22c55e; }
.step.s-in_progress { border-left-color: var(--el-color-primary); }
.step.s-pending_confirm { border-left-color: #f59e0b; }
.step.s-blocked { border-left-color: #ef4444; }
.step.s-mine { background: #f0fdf4; border-radius: 0 6px 6px 0; }
.step-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 5px 0; }
.step-bar .src { font-size: 12px; color: var(--text-muted); }
.step-actions { margin-left: auto; display: flex; gap: 4px; }

.dels { margin: -4px 0 12px; padding: 6px 10px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.dels-empty { margin: -4px 0 12px; padding: 6px 10px; font-size: 12.5px; color: var(--text-muted); }
.del-row { display: flex; align-items: center; gap: 8px; font-size: 12.5px; padding: 3px 0; }
.del-name { color: #374151; }

.unmapped { margin-top: 16px; border-top: 1px dashed var(--el-border-color); padding-top: 12px; }
.unmapped-title { display: flex; align-items: center; gap: 6px; font-size: 13px;
  font-weight: 600; color: #374151; margin-bottom: 6px; flex-wrap: wrap; }
</style>
