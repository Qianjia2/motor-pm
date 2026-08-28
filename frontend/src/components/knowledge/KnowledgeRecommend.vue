<template>
  <div class="card" style="margin-bottom:16px" v-if="items.length > 0 || !dismissed">
    <div class="card-header">
      <div class="card-title">知识推荐</div>
      <div style="display:flex;gap:6px">
        <el-button link size="small" @click="refresh">刷新</el-button>
        <el-button link size="small" @click="dismissed=true">收起</el-button>
      </div>
    </div>

    <div v-if="loading" style="text-align:center;padding:20px;color:var(--text-muted)">
      <el-icon class="is-loading"><Loading /></el-icon> AI分析中...
    </div>

    <div v-else-if="items.length === 0" style="text-align:center;padding:20px;color:var(--text-muted);font-size:13px">
      暂无相关的历史知识推荐
    </div>

    <div v-else style="max-height:260px;overflow-y:auto">
      <div v-for="item in items" :key="item.doc_id || item.id"
        style="padding:8px 0;border-bottom:1px solid var(--border);cursor:pointer"
        @click="openItem(item)">
        <div style="font-size:13px;font-weight:500;color:var(--text)">{{ item.title }}</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          {{ item.snippet || '' }}
        </div>
        <div v-if="item.tags && item.tags.length" style="margin-top:4px;display:flex;gap:4px;flex-wrap:wrap">
          <span v-for="t in item.tags.slice(0,4)" :key="t" class="tag tag-gray" style="font-size:10px">{{ t }}</span>
        </div>
      </div>
    </div>

    <!-- Quick AI Q&A -->
    <div style="margin-top:8px;display:flex;gap:6px">
      <el-input v-model="question" size="small" placeholder="问知识库..." @keyup.enter="askQuestion" />
      <el-button size="small" type="primary" @click="askQuestion" :loading="asking">问</el-button>
    </div>
    <div v-if="answer" style="margin-top:8px;padding:8px;background:#f0f9ff;border-radius:4px;font-size:12px;color:var(--text)">
      {{ answer }}
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({
  projectName: { type: String, default: '' },
  projectType: { type: String, default: '' },
})

const items = ref([])
const loading = ref(false)
const dismissed = ref(false)
const question = ref('')
const answer = ref('')
const asking = ref(false)

async function refresh() {
  if (!props.projectName) return
  loading.value = true
  dismissed.value = false
  try {
    const r = await api.get('/knowledge/project-recommend', {
      params: { project_name: props.projectName, project_type: props.projectType }
    })
    items.value = r.data || []
  } catch(e) { items.value = [] }
  loading.value = false
}

async function askQuestion() {
  if (!question.value.trim()) return
  asking.value = true
  try {
    const r = await api.post('/knowledge/qa', { question: question.value })
    answer.value = r.data?.answer || '未找到答案'
  } catch(e) { answer.value = '问答失败' }
  asking.value = false
}

function openItem(item) {
  window.open(`/knowledge?doc=${item.doc_id || item.id}`, '_blank')
}

onMounted(() => { if (props.projectName) refresh() })
</script>
