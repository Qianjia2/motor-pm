<template>
  <el-dialog v-model="visible" title="全局搜索" width="600px" :show-close="true" @closed="reset">
    <div class="search-input-wrap">
      <el-input v-model="query" placeholder="输入项目名、里程碑、文档、风险关键词..." size="large"
        :prefix-icon="Search" clearable @input="debouncedSearch" @keyup.enter="search" ref="inputRef" />
    </div>

    <div v-if="loading" style="text-align:center;padding:40px">
      <el-icon :size="24" class="is-loading"><Loading /></el-icon>
    </div>

    <div v-else-if="!queried" style="text-align:center;padding:40px;color:var(--text-muted)">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
      </svg>
      <p style="margin-top:12px">输入关键词搜索项目、里程碑、文档、风险</p>
    </div>

    <div v-else-if="isEmpty" style="text-align:center;padding:40px;color:var(--text-muted)">
      <p>未找到匹配结果</p>
    </div>

    <div v-else class="search-results">
      <!-- Projects -->
      <div v-if="results.projects.length" class="result-group">
        <div class="group-title">项目 ({{ results.projects.length }})</div>
        <div v-for="p in results.projects" :key="'p'+p.id" class="result-item" @click="go('/projects/'+p.id)">
          <span class="item-icon">📁</span>
          <div>
            <div class="item-name">{{ p.name }}</div>
            <div class="item-meta">{{ p.code }} · {{ p.phase }}</div>
          </div>
        </div>
      </div>

      <!-- Milestones -->
      <div v-if="results.milestones.length" class="result-group">
        <div class="group-title">里程碑 ({{ results.milestones.length }})</div>
        <div v-for="m in results.milestones" :key="'m'+m.id" class="result-item" @click="go('/projects/'+m.project_id)">
          <span class="item-icon">📅</span>
          <div>
            <div class="item-name">{{ m.name }}</div>
            <div class="item-meta">{{ m.project_name }} · {{ m.planned_date }}</div>
          </div>
        </div>
      </div>

      <!-- Documents -->
      <div v-if="results.documents.length" class="result-group">
        <div class="group-title">项目文档 ({{ results.documents.length }})</div>
        <div v-for="d in results.documents" :key="'d'+d.id" class="result-item" @click="go('/projects/'+d.project_id)">
          <span class="item-icon">📄</span>
          <div>
            <div class="item-name">{{ d.name }}</div>
            <div class="item-meta">{{ d.project_name }} · {{ d.doc_type }}</div>
          </div>
        </div>
      </div>

      <!-- Risks -->
      <div v-if="results.risks.length" class="result-group">
        <div class="group-title">风险/问题 ({{ results.risks.length }})</div>
        <div v-for="r in results.risks" :key="'r'+r.id" class="result-item" @click="go('/projects/'+r.project_id)">
          <span class="item-icon">{{ r.severity >= 3 ? '🔴' : r.severity >= 2 ? '🟡' : '🟢' }}</span>
          <div>
            <div class="item-name">{{ r.title }}</div>
            <div class="item-meta">{{ r.project_name }} · {{ r.status }}</div>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { searchGlobal } from '../../api/index.js'
import { Search, Loading } from '@element-plus/icons-vue'

const router = useRouter()
const visible = ref(false)
const query = ref('')
const results = ref({ projects: [], milestones: [], documents: [], risks: [] })
const loading = ref(false)
const queried = ref(false)
const inputRef = ref(null)
let timer = null

const isEmpty = computed(() => {
  const r = results.value
  return !r.projects.length && !r.milestones.length && !r.documents.length && !r.risks.length
})

function open() {
  visible.value = true
  nextTick(() => inputRef.value?.focus?.())
}

function reset() {
  query.value = ''
  results.value = { projects: [], milestones: [], documents: [], risks: [] }
  queried.value = false
}

async function search() {
  const q = query.value.trim()
  if (!q || q.length < 1) { results.value = { projects: [], milestones: [], documents: [], risks: [] }; queried.value = false; return }
  loading.value = true
  queried.value = true
  try {
    const res = await searchGlobal(q)
    results.value = res.data
  } catch (e) {
    results.value = { projects: [], milestones: [], documents: [], risks: [] }
  } finally {
    loading.value = false
  }
}

function debouncedSearch() {
  clearTimeout(timer)
  timer = setTimeout(search, 300)
}

function go(path) {
  visible.value = false
  router.push(path)
}

defineExpose({ open })
</script>

<style scoped>
.search-input-wrap { margin-bottom: 16px; }

.result-group { margin-bottom: 16px; }
.group-title { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; padding-bottom: 4px; border-bottom: 1px solid var(--border); }
.result-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 6px; cursor: pointer; transition: background .15s; }
.result-item:hover { background: var(--bg); }
.item-icon { font-size: 18px; flex-shrink: 0; }
.item-name { font-size: 13px; font-weight: 500; color: var(--text); }
.item-meta { font-size: 11px; color: var(--text-muted); margin-top: 1px; }
</style>
