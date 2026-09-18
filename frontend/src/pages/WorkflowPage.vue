<template>
  <!-- 项目工作流:工作流从"项目详情里的一个页签"提升为独立模块后的入口。
       跨项目,所以第一件事是选项目;选定后主体和项目详情里那个页签是同一个组件,
       不另起一套渲染——两处显示不一样才是真的坑。 -->
  <div class="wf-page">
    <div class="page-header">
      <h2>项目工作流</h2>
      <p class="subtitle">按项目看全流程编排与「我现在该干什么」</p>
    </div>

    <div class="wf-bar">
      <span class="wf-lbl">选择项目</span>
      <el-select v-model="pid" placeholder="选一个项目" filterable size="default"
        style="width:340px">
        <el-option v-for="p in projects" :key="p.id" :value="p.id"
          :label="`${p.code} ${p.name}`">
          <span class="opt-code">{{ p.code }}</span>
          <span>{{ p.name }}</span>
          <el-tag size="small" effect="plain" class="opt-tag">
            {{ p.project_type === 'software' ? '软件' : '硬件' }}
          </el-tag>
        </el-option>
      </el-select>
      <span v-if="projects.length" class="wf-hint">
        共 {{ projects.length }} 个已开放项目
      </span>
    </div>

    <el-empty v-if="!loading && !projects.length"
      description="还没有开放工作流的项目" />

    <el-empty v-else-if="!pid" description="选一个项目开始" />

    <ProjectWorkflow v-else :key="pid" :project-id="pid"
      :current-member-id="auth.currentMemberId" />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { useAuthStore } from '../stores/auth.js'
import ProjectWorkflow from '../components/project/ProjectWorkflow.vue'

const LAST_KEY = 'wf_last_project'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const projects = ref([])
const pid = ref(null)
const loading = ref(true)

// 选中的项目同时落 URL 和本地:URL 管分享/刷新,本地管下次进来直接回上次那个。
// 只写 URL 的话换台机器就丢;只写本地的话链接分享不出去。
watch(pid, v => {
  if (!v) return
  localStorage.setItem(LAST_KEY, String(v))
  if (Number(route.query.project) === v) return   // 已经是这个了,别再推一次导航
  router.replace({ query: { ...route.query, project: v } })
})

onMounted(async () => {
  try {
    // 支持清单由后端算(白名单只有 workflow_map 一处),前端不复制判定
    const r = await api.get('/workflow/projects')
    projects.value = r.data || []
  } catch (e) {
    projects.value = []
  }
  loading.value = false

  if (!projects.value.length) return
  const q = Number(route.query.project)
  const last = Number(localStorage.getItem(LAST_KEY))
  const hit = [q, last].find(n => n && projects.value.some(p => p.id === n))
  // 只有一个项目就别让人再选一次
  pid.value = hit || (projects.value.length === 1 ? projects.value[0].id : null)
})
</script>

<style scoped>
.wf-page { padding: 0; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0 0 4px; font-size: 20px; color: var(--text); }
.subtitle { margin: 0; font-size: 13px; color: var(--text-secondary); }

.wf-bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--bg-white); border-radius: 8px; box-shadow: var(--shadow-sm);
  padding: 12px 16px; margin-bottom: 16px; }
.wf-lbl { font-size: 13px; color: var(--text-secondary); }
.wf-hint { font-size: 12px; color: var(--text-muted); }

.opt-code { color: var(--text-muted); font-size: 12px; margin-right: 8px; }
.opt-tag { margin-left: 8px; }
</style>
