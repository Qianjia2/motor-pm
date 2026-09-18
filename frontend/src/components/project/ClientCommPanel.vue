<template>
  <div v-loading="loading">
    <div class="card-header mb-md">
      <span class="cc-title">客户沟通记录（{{ comms.length }}）</span>
      <el-button v-if="clientId" size="small" type="primary" @click="openComm(null)">
        <el-icon><Plus /></el-icon> 新增
      </el-button>
      <span v-if="project?.client?.name" class="cc-client">客户：{{ project.client.name }}</span>
    </div>

    <el-alert v-if="!clientId" type="info" :closable="false" show-icon style="margin-bottom:12px"
      title="该项目未关联客户，无法新增沟通记录" description="下方为历史遗留的沟通记录，仅供查看。" />

    <div v-if="!loading && comms.length === 0" class="cc-empty">暂无沟通记录</div>

    <div v-for="c in comms" :key="c.id" class="cc-item" @click="openComm(c)">
      <div class="cc-head">
        <el-tag size="small" effect="plain">{{ c.comm_type }}</el-tag>
        <span class="cc-subject">{{ c.subject || '（无主题）' }}</span>
        <span class="cc-date">{{ c.comm_date || '' }}</span>
      </div>
      <div class="cc-content">{{ c.content || '（无内容）' }}</div>
      <div v-if="(c.images || []).length" class="cc-thumbs">
        <a v-for="img in (c.images || []).slice(0, 6)" :key="img" :href="'/uploads/' + img" target="_blank" @click.stop>
          <img :src="'/uploads/' + img" class="cc-thumb" alt="沟通图片" />
        </a>
        <span v-if="(c.images || []).length > 6" class="cc-more">+{{ (c.images || []).length - 6 }}</span>
      </div>
      <div class="cc-foot">
        <span v-if="c.contact_person">对方：{{ c.contact_person }}</span>
        <span v-if="c.owner">我方：{{ c.owner }}</span>
      </div>
    </div>

    <CommDialog
      v-model="dialogVisible"
      :client-id="clientId"
      :projects="projectOptions"
      :default-project-id="projectId || null"
      :comm="editing"
      @saved="load"
      @deleted="load"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api'
import CommDialog from '../client/CommDialog.vue'

const props = defineProps({
  projectId: { type: Number, required: true },
  project: { type: Object, default: () => ({}) },
})

const comms = ref([])
const loading = ref(false)
const dialogVisible = ref(false)
const editing = ref(null)

// 客户可能没挂: project.client_id 为空时只能只读展示(记录可能比客户关联活得更久)
const clientId = computed(() => props.project?.client_id || props.project?.client?.id || null)
// 只给本项目一个选项,构造上杜绝把沟通错挂到同客户的其它项目
const projectOptions = computed(() => (
  props.projectId
    ? [{ id: props.projectId, name: props.project?.name || '', code: props.project?.code || '' }]
    : []
))

async function load() {
  if (!props.projectId) return
  loading.value = true
  try {
    const r = await api.get(`/projects/${props.projectId}/communications`)
    comms.value = r.data || []
  } catch (e) {
    comms.value = []
  }
  loading.value = false
}

function openComm(c) {
  editing.value = c || null
  dialogVisible.value = true
}

watch(() => props.projectId, load)
onMounted(load)
</script>

<style scoped>
.cc-title { font-weight: 600; }
.card-header { display: flex; align-items: center; gap: 10px; }
.cc-client { font-size: 12px; color: #909399; }
.cc-empty { text-align: center; padding: 40px; color: var(--text-muted, #909399); }
.cc-item { border-bottom: 1px solid #f0f2f5; padding: 10px 0; cursor: pointer; }
.cc-item:last-child { border-bottom: none; }
.cc-item:hover { background: #fafafa; }
.cc-head { display: flex; align-items: center; gap: 8px; }
.cc-subject { font-weight: 600; font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-date { font-size: 12px; color: #909399; }
.cc-content { font-size: 12px; color: #606266; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; white-space: pre-wrap; }
.cc-thumbs { display: flex; gap: 5px; margin-top: 6px; }
.cc-thumb { width: 44px; height: 44px; object-fit: cover; border-radius: 4px; border: 1px solid #f0f2f5; }
.cc-more { font-size: 12px; color: #909399; align-self: center; }
.cc-foot { display: flex; gap: 14px; font-size: 11px; color: #909399; margin-top: 4px; }
</style>
