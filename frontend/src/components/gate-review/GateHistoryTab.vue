<template>
  <div class="ght-tab">
    <div class="toolbar">
      <el-radio-group v-model="view" size="small" @change="load">
        <el-radio-button value="by_gate">按门对比(同门跨项目)</el-radio-button>
        <el-radio-button value="by_project">按项目对比(同项目跨门)</el-radio-button>
      </el-radio-group>
      <el-button size="small" style="margin-left:12px" @click="load">刷新</el-button>
    </div>

    <!-- 按门查看 -->
    <template v-if="view === 'by_gate'">
      <div v-for="g in data.gates || []" :key="g.gate_id" class="gate-card">
        <div class="gate-card-head">
          <span class="gc-name">{{ g.gate_name || g.gate_code || '门' }}</span>
          <span class="gc-phase">{{ g.phase_name }}</span>
          <span class="gc-rate" :class="{ good: (g.pass_rate || 0) >= 0.8 }">
            通过率 {{ g.pass_rate != null ? Math.round(g.pass_rate * 100) + '%' : '—' }} ({{ g.passed }}/{{ g.total }})
          </span>
        </div>
        <el-table :data="g.projects || []" size="small">
          <el-table-column label="项目" min-width="200" prop="project_name" show-overflow-tooltip />
          <el-table-column label="门状态" width="100">
            <template #default="{ row }">
              <el-tag :type="gateTag(row.gate_status)" size="small">{{ gateLabel(row.gate_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="评审日期" width="110">
            <template #default="{ row }">{{ row.review_date || '—' }}</template>
          </el-table-column>
          <el-table-column label="签核时间线" min-width="260">
            <template #default="{ row }">
              <div class="timeline">
                <template v-for="(s, i) in row.signoffs || []" :key="i">
                  <span class="tl-item">
                    <span class="tl-tag" :class="s.status === 'approved' ? 'ok' : s.status === 'rejected' ? 'no' : 'wait'">
                      L{{ s.level }} {{ s.status === 'approved' ? '✓' : s.status === 'rejected' ? '✗' : '···' }}
                    </span>
                    <span class="tl-name">{{ s.signer_name || '—' }}</span>
                    <span v-if="s.signed_at" class="tl-time">{{ s.signed_at.replace('T', ' ').slice(0, 16) }}</span>
                  </span>
                  <span v-if="i < (row.signoffs || []).length - 1" class="tl-arrow">→</span>
                </template>
                <span v-if="!(row.signoffs || []).length" class="t-muted">未发起签核</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="评审意见" min-width="140" prop="notes" show-overflow-tooltip />
        </el-table>
      </div>
    </template>

    <!-- 按项目查看 -->
    <template v-else>
      <div v-for="p in data.projects || []" :key="p.project_id" class="gate-card">
        <div class="gate-card-head">
          <span class="gc-name">{{ p.project_name }}</span>
          <span class="gc-phase">{{ p.code }}</span>
          <span class="gc-rate" :class="{ good: (p.passed / (p.total || 1)) >= 0.8 }">
            已通过 {{ p.passed }}/{{ p.total }} 门
          </span>
        </div>
        <el-table :data="p.gates || []" size="small">
          <el-table-column label="阶段门" min-width="160">
            <template #default="{ row }">
              <span>{{ row.phase_name || '—' }}</span>
              <span v-if="row.gate_name" class="t-muted"> / {{ row.gate_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="门状态" width="100">
            <template #default="{ row }">
              <el-tag :type="gateTag(row.gate_status)" size="small">{{ gateLabel(row.gate_status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="计划截止" width="110">
            <template #default="{ row }">{{ row.planned_end_date || '—' }}</template>
          </el-table-column>
          <el-table-column label="评审日期" width="110">
            <template #default="{ row }">{{ row.review_date || '—' }}</template>
          </el-table-column>
          <el-table-column label="签核时间线" min-width="260">
            <template #default="{ row }">
              <div class="timeline">
                <template v-for="(s, i) in row.signoffs || []" :key="i">
                  <span class="tl-item">
                    <span class="tl-tag" :class="s.status === 'approved' ? 'ok' : s.status === 'rejected' ? 'no' : 'wait'">
                      L{{ s.level }} {{ s.status === 'approved' ? '✓' : s.status === 'rejected' ? '✗' : '···' }}
                    </span>
                    <span class="tl-name">{{ s.signer_name || '—' }}</span>
                    <span v-if="s.signed_at" class="tl-time">{{ s.signed_at.replace('T', ' ').slice(0, 16) }}</span>
                  </span>
                  <span v-if="i < (row.signoffs || []).length - 1" class="tl-arrow">→</span>
                </template>
                <span v-if="!(row.signoffs || []).length" class="t-muted">未发起签核</span>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </template>
    <div v-if="!loading && !data.gates?.length && !data.projects?.length" class="empty-hint">暂无阶段门数据</div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getGateHistory } from '../../api/index.js'

const props = defineProps({
  projects: { type: Array, default: () => [] },
})

const view = ref('by_gate')
const loading = ref(false)
const data = ref({})

function gateTag(s) {
  return { passed: 'success', failed: 'danger', pending: 'warning', waived: 'info' }[s] || 'info'
}
function gateLabel(s) {
  return { passed: '已放行', failed: '未通过', pending: '签核中', waived: '已豁免' }[s] || '未开始'
}

async function load() {
  loading.value = true
  try {
    data.value = (await getGateHistory({ view: view.value })).data || {}
  } finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.ght-tab { padding: 4px 0; }
.toolbar { display: flex; align-items: center; margin-bottom: 12px; }
.gate-card { background: #fff; border: 1px solid var(--border, #e5e7eb); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; }
.gate-card-head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 8px; }
.gc-name { font-weight: 600; font-size: 14px; }
.gc-phase { font-size: 12px; color: var(--text-muted); }
.gc-rate { font-size: 12px; color: var(--text-secondary); margin-left: auto; }
.gc-rate.good { color: #10b981; font-weight: 600; }
.timeline { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tl-item { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; }
.tl-tag { padding: 1px 6px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.tl-tag.ok { background: #ecfdf5; color: #059669; }
.tl-tag.no { background: #fef2f2; color: #dc2626; }
.tl-tag.wait { background: #fffbeb; color: #d97706; }
.tl-name { color: var(--text); }
.tl-time { color: var(--text-muted); font-size: 11px; }
.tl-arrow { color: #cbd5e1; }
.t-muted { color: var(--text-muted); font-size: 12px; }
.empty-hint { color: var(--text-muted); font-size: 12px; padding: 14px 4px; }
</style>
