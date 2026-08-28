<template>
  <div class="card" v-if="items.length > 0">
    <div class="card-header">
      <div class="card-title">待审批事项 ({{ items.length }})</div>
      <span class="card-link" style="cursor:pointer" @click="refresh">刷新</span>
    </div>
    <div v-for="item in items" :key="item.type+item.id" class="approval-row" @click="goItem(item)">
      <span class="approval-icon">{{ item.type === 'change_signoff' ? '📋' : '✅' }}</span>
      <div style="flex:1;min-width:0">
        <div class="approval-title">
          {{ item.title }}
          <span v-if="item.type==='change_signoff'" class="tag" :class="item.level==='A'?'tag-red':item.level==='B'?'tag-orange':'tag-gray'" style="font-size:10px">
            {{ item.level }}级签核
          </span>
        </div>
        <div class="approval-meta">
          {{ item.project_name }}
          <span v-if="item.signer_name"> · 签核人:{{ item.signer_name }}</span>
          <span v-if="item.submitted_date"> · {{ item.submitted_date }}</span>
          <span v-if="item.due_date"> · 截止 {{ item.due_date }}</span>
        </div>
      </div>
      <div class="approval-actions" @click.stop>
        <el-button v-if="item.type==='change_signoff'" size="small" type="success" @click="approve(item)">批准</el-button>
        <el-button v-if="item.type==='change_signoff'" size="small" type="danger" @click="reject(item)">驳回</el-button>
        <el-button v-if="item.type==='review_action'" size="small" type="success" @click="resolveReview(item)">完成</el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../../api/index.js'
import { approveChangeSignoff, rejectChangeSignoff } from '../../api/index.js'

const router = useRouter()
const items = ref([])

onMounted(refresh)

async function refresh() {
  try {
    const res = await api.get('/approvals/pending')
    items.value = res.data || []
  } catch (e) {
    // approvals endpoint is new, may not exist yet
    items.value = []
  }
}

function goItem(item) {
  if (item.project_id) router.push(`/projects/${item.project_id}`)
}

async function approve(item) {
  try {
    if (item.type === 'change_signoff') {
      await approveChangeSignoff(item.id, {})
      ElMessage.success('已批准')
    } else {
      await api.put(`/changes/${item.id}`, { status: 'approved', decision_date: new Date().toISOString().slice(0,10) })
      ElMessage.success('已批准')
    }
    refresh()
  } catch (e) { ElMessage.error('操作失败') }
}

async function reject(item) {
  try {
    if (item.type === 'change_signoff') {
      await rejectChangeSignoff(item.id, { comment: '审批中心驳回' })
      ElMessage.success('已驳回')
    } else {
      await api.put(`/changes/${item.id}`, { status: 'rejected', decision_date: new Date().toISOString().slice(0,10) })
      ElMessage.success('已驳回')
    }
    refresh()
  } catch (e) { ElMessage.error('操作失败') }
}

async function resolveReview(item) {
  try {
    await api.put(`/action-items/${item.id}`, { status: 'closed', resolution: '已完成' })
    ElMessage.success('已完成')
    refresh()
  } catch (e) { ElMessage.error('操作失败') }
}
</script>

<style scoped>
.approval-row {
  display:flex; align-items:center; gap:12px;
  padding:12px 0; border-bottom:1px solid #f3f4f6;
  cursor:pointer; transition:background .15s;
}
.approval-row:hover { background:#fafafa; }
.approval-icon { font-size:18px; flex-shrink:0; }
.approval-title { font-size:13px; font-weight:500; display:flex; align-items:center; gap:6px; }
.approval-meta { font-size:11px; color:var(--text-muted); margin-top:2px; }
.approval-actions { display:flex; gap:4px; flex-shrink:0; }
</style>
