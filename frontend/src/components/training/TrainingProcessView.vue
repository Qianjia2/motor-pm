<template>
  <div class="process-view" v-loading="loading">
    <!-- ── 顶部:项目类型 + 角色筛选 ── -->
    <div class="filter-bar">
      <div class="filter-left">
        <el-radio-group v-model="projectType" size="small" @change="load">
          <el-radio-button value="hardware">电机/硬件项目</el-radio-button>
          <el-radio-button value="software">软件项目</el-radio-button>
        </el-radio-group>
      </div>
      <div class="filter-right">
        <span class="filter-label">我是：</span>
        <el-select v-model="myRole" placeholder="选择岗位，查看我在哪些节点介入" clearable
          filterable size="default" style="width:220px">
          <el-option v-for="r in roles" :key="r" :label="r" :value="r" />
        </el-select>
      </div>
    </div>

    <!-- ── 我的介入概览 ── -->
    <!-- 平台边界:审批在钉钉,本平台只做阶段门把关 -->
    <el-alert v-if="notes.length" type="warning" :closable="false" show-icon class="boundary-note">
      <template #title><b>审批在钉钉，本平台只做阶段门把关</b></template>
      <template #default>
        <ul class="note-list">
          <li v-for="(nt, i) in notes" :key="i">{{ nt }}</li>
        </ul>
      </template>
    </el-alert>

    <el-alert v-if="myRole && myStageCount" type="success" :closable="false" show-icon class="my-summary">
      <template #title>
        作为「<b>{{ myRole }}</b>」，你在 <b>{{ myStageCount }}</b> 个阶段共 <b>{{ myItemCount }}</b> 项工作中需要介入
        <span class="summary-hint">（下方高亮的即为你的节点）</span>
      </template>
    </el-alert>
    <el-alert v-else-if="myRole" type="info" :closable="false" show-icon class="my-summary"
      title="该岗位在本流程中暂无明确的交付物责任，可参考整体流程了解协作关系" />

    <!-- ── 流程图 ── -->
    <div class="flow">
      <div v-for="(st, i) in stages" :key="st.key" class="flow-row"
        :class="{ dimmed: myRole && !stageHasRole(st), mine: myRole && stageHasRole(st) }">
        <!-- 时间轴 -->
        <div class="axis">
          <div class="dot" :class="st.kind">{{ st.key }}</div>
          <div v-if="i < stages.length - 1" class="line"></div>
        </div>

        <!-- 阶段卡片 -->
        <div class="stage-card" :class="[st.kind, { open: isOpen(st.key) }]">
          <div class="stage-head" @click="toggle(st.key)">
            <div class="stage-title">
              <span class="stage-name">{{ st.name }}</span>
              <el-tag v-if="st.gate" size="small" type="warning" effect="dark" class="gate-tag">
                {{ st.gate.name }}
              </el-tag>
              <el-tag v-else-if="st.kind === 'phase'" size="small" effect="plain" type="info">无出口门禁</el-tag>
              <el-tag v-if="myRole && stageHasRole(st)" size="small" type="success" effect="plain">我在此阶段</el-tag>
            </div>
            <el-icon class="fold-icon"><ArrowDown v-if="isOpen(st.key)" /><ArrowRight v-else /></el-icon>
          </div>

          <div class="stage-summary">{{ st.summary }}</div>

          <!-- 进入 / 出口条件 -->
          <div class="cond">
            <div class="cond-item"><span class="cond-k">进入条件</span><span class="cond-v">{{ st.entry }}</span></div>
            <div class="cond-item"><span class="cond-k">出口条件</span><span class="cond-v">{{ st.exit }}</span></div>
          </div>

          <!-- 阶段涉及角色 -->
          <div v-if="st.roles?.length" class="role-chips">
            <span class="chip-label">涉及岗位：</span>
            <el-tag v-for="r in st.roles" :key="r" size="small" effect="plain"
              :type="r === myRole ? 'success' : 'info'" class="role-chip"
              :class="{ active: r === myRole }" @click.stop="myRole = myRole === r ? '' : r">
              {{ r }}
            </el-tag>
          </div>

          <!-- 展开内容 -->
          <div v-show="isOpen(st.key)" class="stage-body">
            <!-- 阶段内动作清单 + 交付物(P0-PP5 / S0-S3) -->
            <template v-if="st.kind === 'phase'">
              <!-- 先看「怎么干」:动作清单与前置/收尾节点同构 -->
              <template v-if="st.nodes?.length">
                <div class="deliver-head">
                  <span>本阶段动作清单（{{ st.nodes.length }} 步）</span>
                  <span class="hint">顺序推进；每步都要交付到具体的人、有明确时限、在平台留痕</span>
                </div>
                <div class="node-list">
                  <ProcessNode v-for="n in st.nodes" :key="n.seq" :node="n" :my-role="myRole" />
                </div>
              </template>

              <!-- 再看「要交什么」 -->
              <div class="deliver-head" :class="{ 'deliver-sep': st.nodes?.length }">
                <span>本阶段交付物（{{ st.deliverables.length }} 项，其中必需 {{ requiredCount(st) }} 项）</span>
                <span class="hint">门禁放行时系统会自动校验必需交付物是否齐备并批准</span>
              </div>
              <!-- 注意: el-table 的 row-class-name 回调入参是 {row, rowIndex}, 不是 row 本身 -->
              <el-table :data="st.deliverables" size="small" class="deliver-table"
                :row-class-name="({ row }) => rowRowClass(row, st)">
                <el-table-column label="交付物" min-width="180">
                  <template #default="{ row }">
                    <span class="d-name">{{ row.name }}</span>
                    <el-tag v-if="row.required" size="small" type="danger" effect="plain" class="req-tag">必需</el-tag>
                    <el-tag v-else size="small" type="info" effect="plain" class="req-tag">可选</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="谁来做" width="170">
                  <template #default="{ row }">
                    <span :class="{ 'mine-text': isMine(row.role) }">{{ row.role || '—' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="用什么模板" min-width="200">
                  <template #default="{ row }">
                    <span class="tpl" :class="{ empty: !row.template }">{{ row.template || '平台无内置模板，自拟' }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="验收要点" min-width="260">
                  <template #default="{ row }">
                    <span class="criteria">{{ row.criteria || '—' }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </template>

            <!-- 前置/收尾节点 -->
            <template v-else>
              <ProcessNode v-for="n in st.nodes" :key="n.seq" :node="n" :my-role="myRole" />
            </template>

            <!-- 下一步 -->
            <div class="next-step">
              <el-icon><Right /></el-icon>
              <span v-if="st.kind === 'phase'">
                本阶段工作完成并通过 <b>{{ st.gate ? st.gate.name : '阶段评审' }}</b> 后 → 进入
                <b>{{ nextStageName(st) }}</b>
              </span>
              <span v-else>完成以上节点后 → <b>{{ nextStageName(st) }}</b></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部说明 -->
    <div class="footnote">
      <p class="strong">合同审批、立项审批、需求审批在钉钉办公平台办理；本平台只承担阶段门把关（G1-G5 / G-S0~G-S3）。</p>
      <p>本流程的阶段、门禁、交付物、模板均取自平台当前配置，管理员在系统设置中调整后本页自动同步。</p>
      <p>各阶段动作清单、前置商务节点与收尾归档节点为平台流程规定，依据《项目开发控制程序》与《项目执行操作手册》整理；阶段、门禁、交付物、模板取自平台当前配置。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowDown, ArrowRight, Right } from '@element-plus/icons-vue'
import api from '../../api'
import ProcessNode from './ProcessNode.vue'

const loading = ref(false)
const projectType = ref('hardware')
const stages = ref([])
const roles = ref([])
const notes = ref([])
const myRole = ref('')
const openKeys = ref(new Set(['PRE']))

function isOpen(key) { return openKeys.value.has(key) }
function toggle(key) {
  const s = new Set(openKeys.value)
  s.has(key) ? s.delete(key) : s.add(key)
  openKeys.value = s
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/training/process-flow', { params: { project_type: projectType.value } })
    stages.value = res.data.stages || []
    roles.value = res.data.roles || []
    notes.value = res.data.notes || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '流程数据加载失败')
  } finally {
    loading.value = false
  }
}

function stageHasRole(st) {
  if (!myRole.value) return false
  return (st.roles || []).includes(myRole.value)
}
function isMine(roleText) {
  return myRole.value && roleText && roleText.includes(myRole.value)
}
function rowRowClass(row, st) {
  if (!myRole.value) return ''
  return isMine(row.role) ? 'row-mine' : 'row-dim'
}
function requiredCount(st) {
  return (st.deliverables || []).filter(d => d.required).length
}
function nextStageName(st) {
  if (st.kind === 'phase') {
    const idx = stages.value.findIndex(x => x.key === st.key)
    return stages.value[idx + 1]?.name || '结题归档'
  }
  if (st.kind === 'pre') return stages.value.find(x => x.kind === 'phase')?.name || 'P0 概念需求阶段'
  return '项目结题关闭，流程结束'
}

const myStageCount = computed(() => stages.value.filter(s => stageHasRole(s)).length)
const myItemCount = computed(() => {
  if (!myRole.value) return 0
  let n = 0
  for (const st of stages.value) {
    // 交付物是动作的产物,两者都算会重复计数;无动作清单的阶段(未配置)退回按交付物计
    const nodes = st.nodes || []
    if (nodes.length) n += nodes.filter(x => (x.roles || []).includes(myRole.value)).length
    else n += (st.deliverables || []).filter(d => isMine(d.role)).length
  }
  return n
})

onMounted(load)
</script>

<style scoped>
.process-view { min-height: 300px; }

/* 筛选栏 */
.filter-bar {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;
  gap: 10px; padding: 12px 14px; background: #f8fafc; border: 1px solid #e5e7eb;
  border-radius: 10px; margin-bottom: 12px; position: sticky; top: 0; z-index: 5;
}
.filter-left { display: flex; align-items: center; gap: 10px; }
.filter-right { display: flex; align-items: center; gap: 6px; }
.filter-label { font-size: 13px; color: #606266; }
.my-summary { margin-bottom: 14px; }
.summary-hint { color: #909399; font-size: 12px; }

/* 流程 */
.flow { padding-left: 4px; }
.flow-row { display: flex; gap: 14px; transition: opacity .2s; }
.flow-row.dimmed { opacity: .42; }
.flow-row.mine { opacity: 1; }

.axis { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; width: 54px; }
.dot {
  width: 46px; height: 46px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: 700; color: #fff; flex-shrink: 0;
  background: #3b82f6; box-shadow: 0 0 0 4px #eff6ff;
}
.dot.pre { background: #8b5cf6; box-shadow: 0 0 0 4px #f5f3ff; }
.dot.post { background: #10b981; box-shadow: 0 0 0 4px #ecfdf5; }
.line { flex: 1; width: 2px; background: #e5e7eb; min-height: 18px; margin: 4px 0; }

/* 阶段卡片 */
.stage-card {
  flex: 1; min-width: 0; border: 1px solid #e5e7eb; border-radius: 10px;
  margin-bottom: 14px; background: #fff; overflow: hidden;
}
.stage-card.pre { border-left: 4px solid #8b5cf6; }
.stage-card.phase { border-left: 4px solid #3b82f6; }
.stage-card.post { border-left: 4px solid #10b981; }
.flow-row.mine .stage-card { border-color: #22c55e; box-shadow: 0 2px 12px rgba(34,197,94,.12); }

.stage-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 14px 8px; cursor: pointer; user-select: none;
}
.stage-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.stage-name { font-size: 16px; font-weight: 700; color: #1f2937; }
.gate-tag { font-size: 11px; }
.fold-icon { color: #9ca3af; }
.stage-summary { padding: 0 14px 8px; font-size: 12.5px; color: #6b7280; }

.cond { padding: 0 14px 10px; display: flex; flex-direction: column; gap: 4px; }
.cond-item { display: flex; gap: 8px; font-size: 12px; }
.cond-k {
  flex-shrink: 0; width: 56px; color: #9ca3af;
}
.cond-v { color: #4b5563; }

.role-chips { padding: 0 14px 10px; display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.chip-label { font-size: 12px; color: #9ca3af; }
.role-chip { cursor: pointer; }
.role-chip.active { font-weight: 700; }

/* 展开区 */
.stage-body { border-top: 1px dashed #e5e7eb; padding: 12px 14px 14px; background: #fcfcfd; }
.deliver-head {
  display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap;
  gap: 6px; margin-bottom: 8px; font-size: 13px; font-weight: 600; color: #374151;
}
.deliver-head .hint { font-size: 11.5px; font-weight: 400; color: #9ca3af; }
/* 动作清单与交付物表之间的分隔:只在真的有动作清单时才画 */
.deliver-head.deliver-sep { margin-top: 14px; padding-top: 12px; border-top: 1px dashed #e5e7eb; }
.node-list { margin-bottom: 10px; }
.deliver-table { width: 100%; }
.deliver-table :deep(.row-mine) { background: #f0fdf4 !important; }
.deliver-table :deep(.row-dim) { opacity: .55; }
.d-name { font-weight: 600; color: #1f2937; }
.req-tag { margin-left: 6px; transform: scale(.9); }
.mine-text { color: #16a34a; font-weight: 700; }
.tpl { font-size: 12px; color: #2563eb; }
.tpl.empty { color: #9ca3af; font-style: italic; }
.criteria { font-size: 12px; color: #6b7280; }

/* 流程节点(.node 系列)的样式随 ProcessNode.vue 走 */

/* 下一步 */
.next-step {
  display: flex; align-items: center; gap: 6px; margin-top: 4px; padding: 9px 12px;
  background: #eff6ff; border-radius: 8px; font-size: 12.5px; color: #1e40af;
}

.boundary-note { margin-bottom: 12px; }
.boundary-note .note-list { margin: 6px 0 0; padding-left: 18px; }
.boundary-note .note-list li { font-size: 12.5px; line-height: 1.75; }
.footnote .strong { color: #b45309 !important; font-weight: 600; }

.footnote { margin-top: 8px; padding: 10px 14px; background: #f8fafc; border-radius: 8px; }
.footnote p { margin: 3px 0; font-size: 12px; color: #909399; }
</style>
