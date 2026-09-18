<template>
  <!-- 我的工作台:进项目第一眼回答「我现在该干什么」。
       四种状态互斥,不并列——并列等于没重点。 -->
  <div class="wb" :class="adminBrowsing ? 'wb-admin' : 'wb-' + state">
    <div class="wb-head">
      <el-icon class="wb-ico" :size="20"><component :is="ico" /></el-icon>
      <div class="wb-title">
        <div class="t1">{{ title }}</div>
        <div class="t2">{{ subtitle }}</div>
      </div>
      <div v-if="me.has_role" class="wb-prog">
        <span class="p-label">我的 {{ me.mine_total }} 步</span>
        <div class="p-bar"><i :style="{ width: pct + '%' }" /></div>
        <span class="p-num">{{ me.mine_done }}/{{ me.mine_total }}</span>
      </div>
    </div>

    <!-- ① 轮到你了:把这一步的四要素摊开,不用再点进去找。
         这里必须判 state==='todo' 而不是 nextStep:「先等前面」时 me.next 也是非空的
         (next 就是那个"轮到我了但前面没做完"的步),用 nextStep 会让下面的等待分支
         永远轮不到,被挡着的人反而看到"去交东西"的按钮。 -->
    <div v-if="state === 'todo'" class="wb-body">
      <div class="n-head">
        <span class="n-idx">{{ nextStep.seq }}</span>
        <span class="n-name">{{ nextStep.node.name }}</span>
        <el-tag v-if="nextStep.node.venue" size="small" effect="plain">
          {{ nextStep.node.venue }}
        </el-tag>
        <el-tag size="small" :type="tagType(nextStep.state)" effect="dark">
          {{ nextStep.state_label }}
        </el-tag>
      </div>
      <div class="n-grid">
        <div class="n-cell"><span class="k">做什么</span><span class="v">{{ nextStep.node.actions }}</span></div>
        <div class="n-cell"><span class="k">产出什么</span><span class="v">{{ nextStep.node.output }}</span></div>
        <div class="n-cell"><span class="k">交给谁</span><span class="v handoff">{{ nextStep.node.handoff }}</span></div>
        <div class="n-cell"><span class="k">在哪办</span><span class="v">{{ nextStep.node.module }}</span></div>
      </div>
      <div v-if="nextStep.node.tip" class="n-tip">注意：{{ nextStep.node.tip }}</div>

      <!-- 这一步要交的东西 + 卡点 -->
      <div v-if="nextStep.standards.length" class="n-dels">
        <div v-for="st in nextStep.standards" :key="st.standard_name" class="d-row">
          <el-icon :color="st.satisfied ? '#22c55e' : '#d1d5db'">
            <component :is="st.satisfied ? CircleCheckFilled : CircleClose" />
          </el-icon>
          <span class="d-name">{{ st.standard_name }}</span>
          <el-tag size="small" :type="st.required ? 'danger' : 'info'" effect="plain">
            {{ st.required === null ? '未配置' : st.required ? '必交' : '选交' }}
          </el-tag>
          <el-tag size="small" :type="delTagType(st.status)" effect="plain">{{ delLabel(st.status) }}</el-tag>
        </div>
      </div>

      <div class="n-actions">
        <el-button v-if="nextStep.kind === 'gate'" type="primary" size="small" @click="$emit('goGate')">
          去门禁签核
        </el-button>
        <el-button v-else-if="nextStep.kind === 'deliverable'" type="primary" size="small"
          @click="$emit('goDeliverable', nextStep)">
          去交付物矩阵
        </el-button>
        <el-button v-if="nextStep.actions.can_confirm" type="primary" size="small"
          @click="$emit('confirm', me.next.phase_code, nextStep)">
          确认已完成
        </el-button>
        <span class="a-hint">{{ actionHint }}</span>
      </div>
    </div>

    <!-- ② 先等前面:说清卡在谁那,不催人开工 -->
    <div v-else-if="state === 'waiting'" class="wb-body">
      <div class="w-title">你在等这 {{ waitFor.length }} 步做完：</div>
      <div v-for="w in waitFor" :key="w.seq" class="w-row">
        <span class="w-dot" :class="'d-' + w.state" />
        <span class="w-seq">第 {{ w.seq }} 步</span>
        <span class="w-name">{{ w.name }}</span>
        <span class="w-roles">{{ w.roles.join(' / ') || '未指定角色' }}</span>
        <el-tag size="small" :type="tagType(w.state)" effect="plain">{{ w.state_label }}</el-tag>
      </div>
    </div>

    <!-- ③/⑤ 你的活干完了 / 有角色但没你的步骤 / 管理员在看一个他不必参与的项目:
         都给出「项目当前卡点」——比甩一句"你没角色"有用。管理员那种情况不是配置
         缺失,所以并到这条分支,而不是走下面 no_role 的提示文案。 -->
    <div v-else-if="state === 'all_done' || state === 'no_steps' || adminBrowsing" class="wb-body">
      <div v-if="bottleneck" class="bn">
        <span class="bn-k">项目当前卡在</span>
        <span class="bn-v">{{ bottleneck.phase_code }} 第 {{ bottleneck.seq }} 步「{{ bottleneck.name }}」</span>
        <span class="bn-r">{{ bottleneck.roles.join(' / ') || '未指定角色' }}</span>
        <el-tag size="small" :type="tagType(bottleneck.state)" effect="plain">{{ bottleneck.state_label }}</el-tag>
      </div>
      <div v-else class="bn"><span class="bn-v">所有阶段的门禁都已放行</span></div>
    </div>

    <!-- ④ 没角色:直接把后端 hint 原文给人,并指出正确的入口 -->
    <div v-else-if="state === 'no_role'" class="wb-body">
      <div class="nr-text">{{ me.hint }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../../stores/auth.js'
import {
  CircleCheckFilled, CircleClose, Loading, Clock, CircleCheck, RemoveFilled, InfoFilled,
} from '@element-plus/icons-vue'

const auth = useAuthStore()

const props = defineProps({
  me: { type: Object, default: () => ({}) },
  phases: { type: Array, default: () => [] },
})
defineEmits(['goDeliverable', 'goGate', 'confirm'])

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
const tagType = s => STATE_TAG[s] || 'info'
const delTagType = s => DEL_TAG[s] || 'info'
const delLabel = s => DEL_LABEL[s] || s

function findStep(phaseCode, seq) {
  const ph = props.phases.find(p => p.phase_code === phaseCode)
  return ph ? ph.steps.find(s => s.seq === seq) : null
}

// me.next 只给 (phase_code, seq),节点详情在本页已有数据里自查,不额外请求
const nextStep = computed(() => {
  const n = props.me.next
  if (!n) return null
  return findStep(n.phase_code, n.seq)
})

const pct = computed(() => {
  const t = props.me.mine_total || 0
  return t ? Math.round((props.me.mine_done || 0) * 100 / t) : 0
})

// 五态互斥。顺序要紧:先判「有没有角色」,再判「有没有我的活」,最后才轮到进度。
const state = computed(() => {
  const m = props.me
  if (!m.has_role) return 'no_role'
  if (!m.mine_total) return 'no_steps'
  if (m.next && !m.next_waiting_on_prev) return 'todo'
  if (m.next && m.next_waiting_on_prev) return 'waiting'
  return 'all_done'
})

const NEXT_HEAD = {
  S0: 'S0 需求分析阶段', S1: 'S1 软件开发阶段',
  S2: 'S2 测试验证阶段', S3: 'S3 发布交付阶段',
}

// 管理员看一个自己没参与的项目:他没角色是对的,不是配置缺失。后端的 hint
// ("请联系项目经理把你加进来")对普通成员合适,对管理员就像在报错——而管理员
// 恰恰是天天要翻各个项目的人。所以单独一种看法,文案换成说明性的。
const adminBrowsing = computed(() => state.value === 'no_role' && auth.isAdmin)

const title = computed(() => {
  if (adminBrowsing.value) return '你是管理员，未参与本项目'
  return {
    todo: '轮到你了',
    waiting: '先等前面这几步做完',
    all_done: '你的活都干完了',
    no_steps: '本项目没有安排到你名下的步骤',
    no_role: '你在本项目没有分配角色',
  }[state.value] || ''
})

const subtitle = computed(() => {
  const m = props.me, n = m.next
  if (adminBrowsing.value) return '下方是全流程视图，按阶段查看每一步'
  if (state.value === 'todo' || state.value === 'waiting') {
    const ph = props.phases.find(p => p.phase_code === n.phase_code)
    const total = ph ? ph.steps.length : null
    return `${NEXT_HEAD[n.phase_code] || n.phase_name} · 第 ${n.seq} 步${total ? ` / 共 ${total} 步` : ''}`
  }
  if (state.value === 'all_done') return `你的 ${m.mine_total} 步已全部完成`
  if (state.value === 'no_steps') return `你的角色：${(m.roles || []).join(' / ')}`
  if (state.value === 'no_role') return '所以看不到「该我做什么」'
  return ''
})

const ico = computed(() => {
  if (adminBrowsing.value) return InfoFilled
  return {
    todo: Loading, waiting: Clock, all_done: CircleCheck,
    no_steps: RemoveFilled, no_role: RemoveFilled,
  }[state.value] || RemoveFilled
})

// 「先等前面」:blocked_by 只有 seq/name/状态,角色要回本阶段的数据里取
const waitFor = computed(() => {
  const n = props.me.next
  if (!n || !n.blocked_by) return []
  const ph = props.phases.find(p => p.phase_code === n.phase_code)
  return n.blocked_by.map(b => {
    const st = ph ? ph.steps.find(s => s.seq === b.seq) : null
    return {
      seq: b.seq, name: b.name || (st && st.node.name) || '',
      state: (st && st.state) || 'not_started',
      state_label: b.state_label || (st && st.state_label) || '',
      roles: (st && st.node && st.node.roles) || [],
    }
  })
})

// 项目当前卡点 = 第一个没放行的阶段里,第一个没完成的步骤
const bottleneck = computed(() => {
  for (const ph of props.phases) {
    if (['passed', 'waived'].includes(ph.gate_state)) continue
    const seq = ph.progress && ph.progress.current_step_seq
    if (seq == null) continue
    const st = ph.steps.find(s => s.seq === seq)
    if (!st) continue
    return {
      phase_code: ph.phase_code, seq, name: st.node.name,
      state: st.state, state_label: st.state_label,
      roles: (st.node && st.node.roles) || [],
    }
  }
  return null
})

const actionHint = computed(() => {
  const s = nextStep.value
  if (!s) return ''
  if (s.kind === 'gate') return '两级签核在「阶段门径」页完成'
  if (s.kind === 'deliverable') return '上传与提交在这一步对应的交付物上完成'
  return ''
})
</script>

<style scoped>
.wb { border: 1px solid var(--border); border-radius: var(--radius); background: #fff;
  padding: 14px 16px; display: flex; flex-direction: column; gap: 12px; }
.wb-todo { border-left: 4px solid #22c55e; background: #f0fdf4; }
.wb-waiting { border-left: 4px solid #f59e0b; background: #fffbeb; }
.wb-all_done { border-left: 4px solid var(--primary); background: var(--primary-light); }
.wb-no_steps, .wb-no_role { border-left: 4px solid #d1d5db; }
/* 管理员看未参与的项目:不是"缺失",所以不用灰的报警配色,用信息色 */
.wb-admin { border-left: 4px solid var(--primary); background: var(--primary-light); }

.wb-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.wb-ico { flex-shrink: 0; }
.wb-todo .wb-ico { color: #22c55e; }
.wb-waiting .wb-ico { color: #f59e0b; }
.wb-all_done .wb-ico { color: var(--primary); }
.wb-no_steps .wb-ico, .wb-no_role .wb-ico { color: #9ca3af; }
.wb-admin .wb-ico { color: var(--primary); }
.wb-title { display: flex; flex-direction: column; gap: 1px; }
.wb-title .t1 { font-size: 15px; font-weight: 700; color: var(--text); }
.wb-title .t2 { font-size: 12.5px; color: var(--text-secondary); }

.wb-prog { margin-left: auto; display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--text-secondary); }
.p-bar { width: 110px; height: 7px; border-radius: 4px; background: #e5e7eb; overflow: hidden; }
.p-bar i { display: block; height: 100%; background: #22c55e; border-radius: 4px; transition: width .3s; }
.p-num { font-variant-numeric: tabular-nums; color: var(--text); font-weight: 600; }

.wb-body { display: flex; flex-direction: column; gap: 9px; }
.n-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.n-idx { width: 21px; height: 21px; border-radius: 50%; background: #22c55e; color: #fff;
  font-size: 11.5px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.n-name { font-size: 15px; font-weight: 700; color: var(--text); }

.n-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px 16px;
  background: rgba(255, 255, 255, .72); border-radius: 6px; padding: 10px 12px; }
.n-cell { display: flex; gap: 8px; font-size: 12.5px; line-height: 1.5; }
.n-cell .k { flex-shrink: 0; width: 52px; color: var(--text-muted); }
.n-cell .v { color: var(--text-secondary); }
.n-cell .v.handoff { color: #2563eb; font-weight: 600; }
.n-tip { font-size: 12.5px; color: #b45309; }

.n-dels { display: flex; flex-direction: column; gap: 4px; }
.d-row { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.d-name { color: var(--text-secondary); }

.n-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 2px; }
.a-hint { font-size: 12px; color: var(--text-muted); }

.w-title { font-size: 13px; font-weight: 600; color: var(--text); }
.w-row { display: flex; align-items: center; gap: 9px; font-size: 12.5px;
  background: rgba(255, 255, 255, .72); border-radius: 6px; padding: 6px 10px; }
.w-dot { width: 8px; height: 8px; border-radius: 50%; background: #d1d5db; flex-shrink: 0; }
.w-dot.d-done { background: #22c55e; }
.w-dot.d-in_progress { background: var(--el-color-primary); }
.w-dot.d-pending_confirm { background: #f59e0b; }
.w-dot.d-blocked { background: #ef4444; }
.w-seq { color: var(--text-muted); flex-shrink: 0; }
.w-name { color: var(--text); font-weight: 600; }
.w-roles { color: var(--text-muted); margin-left: auto; }

.bn { display: flex; align-items: center; gap: 9px; font-size: 13px; flex-wrap: wrap; }
.bn-k { color: var(--text-muted); }
.bn-v { color: var(--text); font-weight: 600; }
.bn-r { color: var(--text-secondary); margin-left: auto; }

.nr-text { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }
</style>
