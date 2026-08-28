<template>
  <div class="kanban">
    <div class="kanban-cols">
      <div v-for="col in columns" :key="col.status" class="kanban-col"
        @dragover.prevent @drop="onDrop($event, col.status)">
        <div class="kanban-col-hdr" :style="{borderTopColor:col.color}">
          <span>{{ col.label }}</span>
          <span class="col-count">{{ tasksByStatus(col.status).length }}</span>
        </div>
        <div class="kanban-cards">
          <div v-for="t in tasksByStatus(col.status)" :key="t.id" class="kanban-card"
            draggable="true" @dragstart="onDragStart($event, t)"
            :class="{blocked: t.status==='blocked', done: t.status==='completed'}">
            <div class="card-title">{{ t.name }}</div>
            <div class="card-meta">
              <span v-if="t.assignee" class="tag tag-blue" style="font-size:10px">{{ t.assignee.name }}</span>
              <span v-if="t.line" class="tag tag-gray" style="font-size:10px">{{ t.line.short_name || t.line.name }}</span>
            </div>
            <div class="card-bottom">
              <el-progress :percentage="t.progress_pct||0" :stroke-width="4" :show-text="false"
                :color="t.progress_pct>=80?'#10b981':'#3b82f6'" style="flex:1;margin-right:8px" />
              <span style="font-size:10px;color:var(--text-muted);white-space:nowrap">{{ t.end_date||'-' }}</span>
            </div>
          </div>
          <div v-if="tasksByStatus(col.status).length===0" class="kanban-empty">拖拽任务至此</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import api from '../../api/index.js'
import { ElMessage } from 'element-plus'

const props = defineProps({ tasks: { type: Array, default: () => [] } })
const emit = defineEmits(['update'])

const columns = [
  { status: 'pending', label: '待开始', color: '#9ca3af' },
  { status: 'in_progress', label: '进行中', color: '#3b82f6' },
  { status: 'completed', label: '已完成', color: '#10b981' },
  { status: 'blocked', label: '阻塞', color: '#ef4444' },
]

function tasksByStatus(s) { return props.tasks.filter(t => t.status === s) }

let dragTask = null
function onDragStart(e, t) { dragTask = t }

async function onDrop(e, newStatus) {
  if (!dragTask || dragTask.status === newStatus) return
  try {
    await api.put(`/tasks/${dragTask.id}`, { status: newStatus,
      progress_pct: newStatus === 'completed' ? 100 : dragTask.progress_pct })
    ElMessage.success(`已移至"${columns.find(c=>c.status===newStatus)?.label}"`)
    emit('update')
  } catch (e) { ElMessage.error('更新失败') }
}
</script>

<style scoped>
.kanban { overflow-x:auto; }
.kanban-cols { display:flex; gap:12px; min-width:700px; }
.kanban-col { flex:1; min-width:160px; background:#f3f4f6; border-radius:8px; border-top:3px solid #d1d5db; display:flex; flex-direction:column; min-height:300px; }
.kanban-col-hdr { display:flex; justify-content:space-between; padding:10px 12px; font-size:13px; font-weight:600; color:var(--text); border-top:3px solid; margin-top:-3px; border-radius:8px 8px 0 0; background:#fff; }
.col-count { background:#e5e7eb; padding:0 8px; border-radius:10px; font-size:11px; }
.kanban-cards { flex:1; padding:8px; display:flex; flex-direction:column; gap:6px; overflow-y:auto; }
.kanban-card { background:#fff; border-radius:6px; padding:10px 12px; box-shadow:var(--shadow-sm); cursor:grab; transition:box-shadow .15s; }
.kanban-card:hover { box-shadow:var(--shadow-md); }
.kanban-card.blocked { border-left:3px solid #ef4444; }
.kanban-card.done { opacity:.7; }
.card-title { font-size:13px; font-weight:500; color:var(--text); margin-bottom:6px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.card-meta { display:flex; gap:4px; margin-bottom:6px; }
.card-bottom { display:flex; align-items:center; }
.kanban-empty { text-align:center; color:var(--text-muted); font-size:12px; padding:20px 0; }
</style>
