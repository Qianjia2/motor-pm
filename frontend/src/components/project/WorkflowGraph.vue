<template>
  <!-- 阶段流程图:4 个阶段并排成列,列内步骤竖排带连线。
       目的是一眼看清「整条流程走到哪、卡在谁那」,而不是一屏只能看一个阶段。
       div + CSS 实现(照 TrainingProcessView 的范式),不用 SVG——节点要放可点内容。 -->
  <div class="g-wrap">
    <div class="g">
      <div v-for="(ph, i) in phases" :key="ph.phase_code" class="lane">
        <div class="lane-head" :class="{ 'has-next': i < phases.length - 1 }">
          <div class="lh-top">
            <span class="lh-code">{{ ph.phase_code }}</span>
            <el-tag size="small" :type="gateType(ph.gate_state)" effect="dark">{{ ph.gate_state_label }}</el-tag>
          </div>
          <div class="lh-name" :title="ph.phase_name">{{ ph.phase_name }}</div>
          <div class="lh-meta">
            <span>{{ ph.progress.steps_done }}/{{ ph.steps.length }} 步</span>
            <span v-if="ph.gate" class="lh-gate">{{ ph.gate.code }}</span>
          </div>
          <el-progress :percentage="ph.progress.percent" :stroke-width="5" :show-text="false" />
        </div>

        <div class="lane-body">
          <div v-for="step in ph.steps" :key="step.seq"
            class="node" :class="nodeCls(step)" @click="open(ph, step)">
            <span class="n-badge" :class="{ diamond: step.kind === 'gate' }">{{ step.seq }}</span>
            <span class="n-text">
              <span class="n-name" :title="stepLabel(step)">{{ step.node.name }}</span>
              <span class="n-sub">{{ step.state_label }}</span>
            </span>
            <span v-if="step.assigned_to_me" class="n-me">你</span>
          </div>
        </div>
      </div>
    </div>

    <div class="g-legend">
      <span><i class="lg done" />已完成</span>
      <span><i class="lg in_progress" />进行中</span>
      <span><i class="lg pending_confirm" />待确认</span>
      <span><i class="lg blocked" />有驳回</span>
      <span><i class="lg not_started" />未开始</span>
      <span><i class="lg diamond" />阶段门禁</span>
      <span class="lg-tip">点任意步骤看详情</span>
    </div>

    <!-- 步骤详情:复用 ProcessNode,不重画一套 -->
    <el-drawer v-model="drawer" :title="title" size="560px" @closed="sel = null">
      <template v-if="sel">
        <div class="dw-head">
          <el-tag :type="tagType(sel.step.state)" effect="dark">{{ sel.step.state_label }}</el-tag>
          <span class="dw-src">依据：{{ srcLabel(sel.step) }}</span>
          <el-tag v-if="sel.step.assigned_to_me" type="success" effect="plain" size="small">我的角色</el-tag>
          <el-tag v-if="sel.step.confirm" type="success" effect="plain" size="small">
            {{ sel.step.confirm.confirmed_by }} 已确认
          </el-tag>
        </div>

        <ProcessNode :node="sel.step.node" :my-role="myRole" />

        <div v-if="sel.step.standards.length" class="dw-dels">
          <div class="dw-t">这一步要交的东西</div>
          <div v-for="st in sel.step.standards" :key="st.standard_name" class="d-row">
            <el-icon :color="st.satisfied ? '#22c55e' : '#d1d5db'">
              <component :is="st.satisfied ? CircleCheckFilled : CircleClose" />
            </el-icon>
            <span class="d-name">{{ st.standard_name }}</span>
            <el-tag size="small" :type="st.required ? 'danger' : 'info'" effect="plain">
              {{ st.required === null ? '未配置' : st.required ? '必交' : '选交' }}
            </el-tag>
            <el-tag size="small" :type="delTagType(st.status)" effect="plain">{{ delLabel(st.status) }}</el-tag>
            <span v-if="st.owner_name" class="d-owner">{{ st.owner_name }}</span>
          </div>
        </div>
        <div v-else class="dw-empty">这一步没有对应的交付物标准，完成情况以人工确认为准</div>

        <div v-if="sel.step.blocked_by_prev && sel.step.blocked_by.length" class="dw-block">
          <el-icon><WarningFilled /></el-icon>
          前面还有 {{ sel.step.blocked_by.length }} 步没完成：
          {{ sel.step.blocked_by.map(b => `第${b.seq}步 ${b.name}`).join('、') }}
        </div>

        <div class="dw-actions">
          <el-button v-if="sel.step.kind === 'gate' && sel.step.actions.can_initiate_signoff"
            type="primary" size="small" @click="$emit('goGate')">去发起门禁签署</el-button>
          <el-button v-else-if="sel.step.kind === 'deliverable'" type="primary" size="small"
            @click="$emit('goDeliverable', sel.step)">去交付物矩阵</el-button>
          <el-button v-if="sel.step.actions.can_confirm" type="primary" size="small"
            @click="$emit('confirm', sel.phase.phase_code, sel.step)">确认已完成</el-button>
          <el-popconfirm v-if="sel.step.actions.can_unconfirm" title="撤销这条确认?"
            @confirm="$emit('unconfirm', sel.phase.phase_code, sel.step)">
            <template #reference>
              <el-button type="danger" link size="small">撤销确认</el-button>
            </template>
          </el-popconfirm>
        </div>

        <div v-if="missing.length" class="dw-missing">
          <div class="dw-t">本阶段门禁还差 {{ missing.length }} 份必交</div>
          <div class="m-list"><span v-for="m in missing" :key="m" class="m-item">{{ m }}</span></div>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import {
  CircleCheckFilled, CircleClose, WarningFilled,
} from '@element-plus/icons-vue'
import ProcessNode from '../training/ProcessNode.vue'

const props = defineProps({
  phases: { type: Array, default: () => [] },
  myRole: { type: String, default: '' },
})
defineEmits(['goDeliverable', 'goGate', 'confirm', 'unconfirm'])

const GATE_TAG = {
  passed: 'success', waived: 'success', l1_pending: 'warning', l2_pending: 'warning',
  rejected: 'danger', not_initiated: 'info',
}
const STATE_TAG = {
  done: 'success', in_progress: 'primary', pending_confirm: 'warning',
  blocked: 'danger', not_started: 'info',
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

const gateType = s => GATE_TAG[s] || 'info'
const tagType = s => STATE_TAG[s] || 'info'
const delTagType = s => DEL_TAG[s] || 'info'
const delLabel = s => DEL_LABEL[s] || s
const srcLabel = s => SRC_LABEL[s.state_source] || s.state_source

// 门禁节点在名字前加个记号,光靠颜色区分度不够(色盲/投影仪都不行)
const stepLabel = s => (s.kind === 'gate' ? `◆ ${s.node.name}` : s.node.name)

function nodeCls(step) {
  return [
    's-' + step.state,
    {
      'n-gate': step.kind === 'gate',
      'n-current': step.is_current,
      'n-mine': step.assigned_to_me,
      'n-locked': step.blocked_by_prev,
    },
  ]
}

const drawer = ref(false)
const sel = ref(null)
function open(ph, step) {
  sel.value = { phase: ph, step }
  drawer.value = true
}
const title = computed(() => {
  if (!sel.value) return ''
  const { phase, step } = sel.value
  return `${phase.phase_code} ${phase.phase_name} · 第 ${step.seq} 步`
})
const missing = computed(() => {
  const s = sel.value
  return s && s.step.kind === 'gate' ? (s.step.actions.missing_required || []) : []
})
</script>

<style scoped>
.g-wrap { display: flex; flex-direction: column; gap: 10px; }
.g { display: flex; gap: 14px; overflow-x: auto; padding-bottom: 4px; }

.lane { flex: 1 1 0; min-width: 190px; display: flex; flex-direction: column; }

/* 阶段头之间的箭头:阶段之间的流转关系,放在头上比放在步骤之间更准(各列步数不等) */
.lane-head { position: relative; border: 1px solid var(--border); border-radius: 8px;
  padding: 9px 11px; background: var(--el-fill-color-lighter); display: flex;
  flex-direction: column; gap: 5px; margin-bottom: 12px; }
.lane-head.has-next::after {
  content: '▸'; position: absolute; right: -12px; top: 50%; transform: translateY(-50%);
  color: #c0c4cc; font-size: 15px; line-height: 1;
}
.lh-top { display: flex; align-items: center; gap: 6px; }
.lh-code { font-size: 13px; font-weight: 700; color: var(--primary); }
.lh-name { font-size: 13px; font-weight: 600; color: var(--text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lh-meta { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-muted); }
.lh-gate { margin-left: auto; }

/* 列内竖线:贯穿所有徽标,由徽标自身的不透明底色遮住穿过部分 */
.lane-body { position: relative; display: flex; flex-direction: column; gap: 6px; }
.lane-body::before {
  content: ''; position: absolute; left: 10px; top: 12px; bottom: 12px; width: 2px;
  background: var(--border); z-index: 0;
}

.node { position: relative; display: flex; align-items: center; gap: 9px; cursor: pointer;
  background: #fff; border: 1px solid var(--border); border-radius: 6px;
  padding: 6px 8px 6px 6px; transition: border-color .15s, box-shadow .15s; }
.node:hover { border-color: var(--primary); }
.node.n-mine { border-color: #22c55e; background: #f0fdf4; }

/* 序号徽标不透明,盖住竖线;门禁用菱形区分 */
.n-badge { position: relative; z-index: 1; flex-shrink: 0; width: 20px; height: 20px;
  border-radius: 50%; background: #e5e7eb; color: #4b5563; font-size: 11px; font-weight: 700;
  display: flex; align-items: center; justify-content: center; }
.n-badge.diamond { border-radius: 3px; transform: rotate(45deg); background: #fff;
  border: 2px solid #9ca3af; }
.n-badge.diamond::before { content: ''; }

.n-text { min-width: 0; display: flex; flex-direction: column; }
.n-name { font-size: 12.5px; color: var(--text); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
.n-sub { font-size: 11px; color: var(--text-muted); }
.n-me { margin-left: auto; flex-shrink: 0; font-size: 11px; font-weight: 700; color: #fff;
  background: #22c55e; border-radius: 3px; padding: 0 4px; }

/* 状态:徽标底色 + 左边框,两种信号,不单靠颜色 */
.node.s-done .n-badge { background: #22c55e; color: #fff; }
.node.s-in_progress .n-badge { background: var(--el-color-primary); color: #fff; }
.node.s-pending_confirm .n-badge { background: #f59e0b; color: #fff; }
.node.s-blocked .n-badge { background: #ef4444; color: #fff; }
.node.s-done { border-left: 3px solid #22c55e; }
.node.s-in_progress { border-left: 3px solid var(--el-color-primary); }
.node.s-pending_confirm { border-left: 3px solid #f59e0b; }
.node.s-blocked { border-left: 3px solid #ef4444; }
.node.s-not_started { border-left: 3px solid #e5e7eb; }

/* 当前步:外环高亮,一眼找到"现在卡在这" */
.node.n-current { box-shadow: 0 0 0 2px var(--primary-light), 0 0 0 3px var(--primary); }
/* 被前面挡住的步骤:压暗,别和"轮到我了"抢注意力 */
.node.n-locked .n-name { color: var(--text-muted); }
.node.n-gate { border-style: dashed; }

.g-legend { display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  font-size: 12px; color: var(--text-muted); padding-left: 2px; }
.g-legend span { display: inline-flex; align-items: center; gap: 5px; }
.lg { width: 9px; height: 9px; border-radius: 50%; display: inline-block; background: #e5e7eb; }
.lg.done { background: #22c55e; }
.lg.in_progress { background: var(--el-color-primary); }
.lg.pending_confirm { background: #f59e0b; }
.lg.blocked { background: #ef4444; }
.lg.diamond { border-radius: 2px; transform: rotate(45deg); background: #fff; border: 2px solid #9ca3af; }
.lg-tip { margin-left: auto; }

.dw-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.dw-src { font-size: 12px; color: var(--text-muted); }
.dw-t { font-size: 13px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
.dw-dels { margin-top: 12px; }
.d-row { display: flex; align-items: center; gap: 8px; font-size: 12.5px; padding: 3px 0; }
.d-name { color: var(--text-secondary); }
.d-owner { color: var(--text-muted); margin-left: auto; }
.dw-empty { margin-top: 12px; font-size: 12.5px; color: var(--text-muted); }
.dw-block { margin-top: 12px; display: flex; align-items: center; gap: 6px;
  font-size: 12.5px; color: #b45309; background: #fffbeb; border-radius: 6px; padding: 8px 10px; }
.dw-actions { margin-top: 16px; display: flex; gap: 8px; flex-wrap: wrap; }
.dw-missing { margin-top: 14px; background: #fef2f2; border: 1px solid #fecaca;
  border-radius: 6px; padding: 9px 11px; }
.dw-missing .dw-t { color: #b91c1c; }
.m-list { display: flex; flex-wrap: wrap; gap: 6px; }
.m-item { background: #fff; border: 1px solid #fecaca; color: #b91c1c;
  border-radius: 4px; padding: 1px 7px; font-size: 12px; }
</style>
