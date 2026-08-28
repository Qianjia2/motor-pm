<template>
  <div class="training-page">
    <div class="page-header">
      <div>
        <h2>培训学习</h2>
        <p class="subtitle">教学资料 · 任务清单</p>
      </div>
    </div>

    <el-tabs v-model="activeSub" class="sub-tabs">
      <!-- ─── 教学资料 ─── -->
      <el-tab-pane label="📚 教学资料" name="materials">
        <div class="materials-head">
          <el-radio-group v-model="activeCategory" size="small" @change="loadMaterials">
            <el-radio-button value="">全部</el-radio-button>
            <el-radio-button v-for="c in categories" :key="c.category" :value="c.category">
              {{ c.category }} ({{ c.count }})
            </el-radio-button>
          </el-radio-group>
          <el-button v-if="auth.isAdmin" type="primary" size="small" icon="Upload" @click="openUpload">上传素材</el-button>
        </div>

        <div v-loading="loading" class="material-grid">
          <el-empty v-if="!loading && materials.length === 0" description="暂无素材，管理员可在右上角上传" />
          <el-card v-for="m in materials" :key="m.id" class="material-card" shadow="hover">
            <div class="m-card-body" @click="openMaterial(m)">
              <div class="m-icon" :class="m.is_video ? 'video' : 'manual'">
                <el-icon :size="22"><VideoCamera v-if="m.is_video" /><Document v-else /></el-icon>
              </div>
              <div class="m-info">
                <div class="m-title">{{ m.title }}</div>
                <div class="m-desc">{{ m.description || '暂无简介' }}</div>
                <div class="m-meta">
                  <el-tag size="small" effect="plain">{{ m.is_video ? '视频' : m.material_type === 'manual' ? '手册' : '资料' }}</el-tag>
                  <span>{{ formatSize(m.file_size) }}</span>
                  <span>{{ m.file_ext?.toUpperCase() }}</span>
                  <span>{{ m.uploader }}</span>
                </div>
              </div>
            </div>
            <div v-if="auth.isAdmin" class="m-actions">
              <el-button size="small" type="danger" plain @click="removeMaterial(m)">删除</el-button>
            </div>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- ─── 任务清单 ─── -->
      <el-tab-pane label="✅ 任务清单" name="tasks">
        <TrainingTasksView />
      </el-tab-pane>
    </el-tabs>

    <!-- Video player dialog -->
    <el-dialog v-model="playerVisible" :title="current?.title || '视频播放'" width="820px" destroy-on-close>
      <video v-if="current" :src="fileUrl(current)" controls autoplay class="player" style="width:100%;max-height:60vh;background:#000;border-radius:8px" />
      <div v-if="current" class="dialog-foot">
        <el-button type="primary" :icon="Download" @click="downloadFile(current)">下载视频</el-button>
        <span class="dialog-desc">{{ current.description }}</span>
      </div>
    </el-dialog>

    <!-- Manual preview dialog -->
    <el-dialog v-model="manualVisible" :title="current?.title || '文档预览'" width="860px" destroy-on-close>
      <iframe v-if="current && isPdf(current)" :src="fileUrl(current)" style="width:100%;height:60vh;border:none;border-radius:8px" />
      <el-empty v-if="current && !isPdf(current)" description="该格式不支持在线预览，请下载后查看" :image-size="80" />
      <div v-if="current" class="dialog-foot">
        <el-button type="primary" :icon="Download" @click="downloadFile(current)">下载{{ isPdf(current) ? '' : '文档' }}</el-button>
        <span class="dialog-desc">{{ current.description }}</span>
      </div>
    </el-dialog>

    <!-- Upload dialog -->
    <el-dialog v-model="uploadVisible" title="上传培训素材" width="560px" destroy-on-close>
      <el-form label-width="90px">
        <el-form-item label="所属模块" required>
          <el-select v-model="form.category" filterable allow-create default-first-option placeholder="选择或输入新模块名" style="width:100%">
            <el-option v-for="c in categories" :key="c.category" :label="c.category" :value="c.category" />
          </el-select>
        </el-form-item>
        <el-form-item label="素材标题" required>
          <el-input v-model="form.title" placeholder="如：阶段门评审操作视频" />
        </el-form-item>
        <el-form-item label="素材类型">
          <el-radio-group v-model="form.material_type">
            <el-radio value="video">学习视频</el-radio>
            <el-radio value="manual">操作手册</el-radio>
            <el-radio value="other">其他资料</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="简要说明素材内容、适用对象" />
        </el-form-item>
        <el-form-item label="文件" required>
          <input ref="fileInput" type="file" class="file-input" @change="onFileChange" />
          <div v-if="form.file" class="file-name">{{ form.file.name }}（{{ formatSize(form.file.size) }}）</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="submitUpload">上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoCamera, Document, Download, Upload } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import TrainingTasksView from '../components/training/TrainingTasksView.vue'

const auth = useAuthStore()
const activeSub = ref('materials')

const categories = ref([])
const materials = ref([])
const activeCategory = ref('')
const loading = ref(false)

const playerVisible = ref(false)
const manualVisible = ref(false)
const current = ref(null)

const uploadVisible = ref(false)
const uploading = ref(false)
const fileInput = ref(null)
const form = ref({ category: '', title: '', description: '', material_type: 'video', file: null })

function fileUrl(m) {
  const token = localStorage.getItem('access_token') || ''
  return `/api/training/file/${m.id}?token=${encodeURIComponent(token)}`
}
function isPdf(m) { return m.file_ext === 'pdf' }
function formatSize(n) {
  if (!n) return ''
  if (n > 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB'
  if (n > 1024) return (n / 1024).toFixed(0) + ' KB'
  return n + ' B'
}

async function loadCategories() {
  const res = await api.get('/training/categories')
  categories.value = res.data.items || []
}
async function loadMaterials() {
  loading.value = true
  try {
    const res = await api.get('/training/materials', { params: { category: activeCategory.value || undefined } })
    materials.value = res.data.items || []
  } finally { loading.value = false }
}

function openMaterial(m) {
  current.value = m
  if (m.is_video) playerVisible.value = true
  else manualVisible.value = true
}
function downloadFile(m) {
  window.open(fileUrl(m).replace('?token=', '?download=true&token='), '_blank')
}

function openUpload() { uploadVisible.value = true }
function onFileChange(e) { form.value.file = e.target.files?.[0] || null }

async function submitUpload() {
  if (!form.value.category || !form.value.title || !form.value.file) {
    ElMessage.warning('请填写所属模块、标题并选择文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', form.value.file)
    fd.append('category', form.value.category)
    fd.append('title', form.value.title)
    fd.append('description', form.value.description)
    fd.append('material_type', form.value.material_type)
    await api.post('/training/materials', fd)
    ElMessage.success('上传成功')
    uploadVisible.value = false
    const uploadedCategory = form.value.category
    form.value = { category: '', title: '', description: '', material_type: 'video', file: null }
    if (fileInput.value) fileInput.value.value = ''
    activeCategory.value = uploadedCategory
    await loadCategories()
    await loadMaterials()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally { uploading.value = false }
}

async function removeMaterial(m) {
  try {
    await ElMessageBox.confirm(`确定删除「${m.title}」？文件将一并移除。`, '删除确认', { type: 'warning' })
  } catch { return }
  await api.delete(`/training/materials/${m.id}`)
  ElMessage.success('已删除')
  await loadCategories()
  await loadMaterials()
}

onMounted(async () => {
  await loadCategories()
  await loadMaterials()
})
</script>

<style scoped>
.training-page { padding: 20px; }
.page-header { margin-bottom: 8px; }
.page-header h2 { margin: 0 0 4px 0; font-size: 20px; }
.subtitle { color: #909399; font-size: 13px; }
.sub-tabs :deep(.el-tabs__item) { font-size: 15px; }
.materials-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.material-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; min-height: 120px; }
.material-card { position: relative; cursor: pointer; }
.material-card :deep(.el-card__body) { padding: 14px; }
.m-card-body { display: flex; gap: 12px; }
.m-icon {
  flex-shrink: 0; width: 46px; height: 46px; border-radius: 10px;
  display: flex; align-items: center; justify-content: center; color: #fff;
}
.m-icon.video { background: linear-gradient(135deg, #f56c6c, #e6a23c); }
.m-icon.manual { background: linear-gradient(135deg, #3b82f6, #22c55e); }
.m-info { flex: 1; min-width: 0; }
.m-title { font-size: 14px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.m-desc {
  font-size: 12px; color: #909399; margin: 4px 0;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.m-meta { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #b0b3b8; flex-wrap: wrap; }
.m-actions { position: absolute; top: 8px; right: 8px; opacity: 0; transition: opacity .15s; }
.material-card:hover .m-actions { opacity: 1; }
.dialog-foot { display: flex; align-items: center; gap: 12px; margin-top: 12px; }
.dialog-desc { font-size: 12px; color: #909399; }
.file-input { width: 100%; }
.file-name { font-size: 12px; color: #3b82f6; margin-top: 4px; }
</style>
