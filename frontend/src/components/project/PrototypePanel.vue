<template>
  <div>
    <input type="file" ref="bomFileInput" @change="onBomFileSelected" style="display:none" />
    <div class="card-header mb-md"><span></span><el-button size="small" type="primary" @click="openBuild()"><el-icon><Plus /></el-icon> 添加试制批次</el-button></div>

    <div v-if="builds.length===0" style="text-align:center;padding:40px;color:var(--text-muted)">
      暂无试制批次。创建批次后可在此管理样机BOM和物料齐套。
    </div>

    <div v-for="b in builds" :key="b.id" class="build-card">
      <div class="build-hdr">
        <span class="build-name">{{ b.batch_name }}</span>
        <span class="tag tag-blue" style="margin:0 8px">{{ buildStatusLabel(b.status) }}</span>
        <span v-if="bMatMissing(b) > 0" class="tag tag-red" style="font-size:10px">缺料{{ bMatMissing(b) }}</span>
        <span v-else-if="bMatReady(b) > 0" class="tag tag-green" style="font-size:10px">物料齐套</span>
        <span style="margin-left:auto;display:flex;gap:4px">
          <el-button link size="small" @click="openBuild(b)">编辑</el-button>
          <el-popconfirm title="删除?" @confirm="delBuild(b.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
        </span>
      </div>
      <div class="build-meta">
        <span>数量: {{ b.actual_qty != null ? b.actual_qty : (b.planned_qty||0) }}/{{ b.planned_qty }}台</span>
        <span>{{ b.start_date || '?' }} → {{ b.end_date || '?' }}</span>
        <span v-if="b.notes" style="color:var(--text-muted)">{{ b.notes.slice(0, 60) }}</span>
      </div>

      <!-- BOM + Material section (expandable) -->
      <div style="margin-top:12px" v-if="expandedBuildId === b.id">
        <div class="card-header" style="margin-bottom:8px">
          <span style="font-size:13px;font-weight:600">BOM (物料清单)</span>
          <div style="display:flex;gap:6px;align-items:center">
            <el-button size="small" @click="triggerBomUpload(b.id)">📎 上传BOM文件</el-button>
            <el-button size="small" type="success" @click="aiBomBuildId=b.id;aiBomFile?.click()">🤖 AI生成BOM</el-button>
          </div>
        </div>
        <!-- BOM attached files -->
        <div v-if="(bomFiles[b.id]||[]).length > 0" style="margin-bottom:8px">
          <div v-for="f in (bomFiles[b.id]||[])" :key="f.id" style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px">
            <span>📄</span>
            <a :href="`/api/prototype-builds/${b.id}/bom-files/${f.id}/download`" target="_blank" style="color:var(--primary);text-decoration:none;flex:1">{{ f.name }}</a>
            <span style="font-size:11px;color:var(--text-muted)">{{ f.size_kb }}KB · {{ f.upload_date }}</span>
            <el-button link size="small" type="primary" @click="previewBomFile(b.id, f.id)">预览</el-button>
            <el-popconfirm title="删除?" @confirm="delBomFile(b.id, f.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
          </div>
        </div>
        <div v-else style="color:var(--text-muted);font-size:12px;padding:8px 0">暂无BOM文件，点击"上传BOM文件"添加</div>

        <!-- Material check (separate section under BOM) -->
        <div v-if="materialChecks.length > 0" style="margin-top:16px">
          <div class="card-header" style="margin-bottom:8px">
            <span style="font-size:13px;font-weight:600">物料齐套检查</span>
            <el-button size="small" @click="openMaterial()">+ 添加检查项</el-button>
          </div>
          <el-table :data="materialChecks" stripe size="small">
            <el-table-column prop="material_name" label="物料名称" min-width="140" />
            <el-table-column prop="specification" label="规格" width="140" show-overflow-tooltip />
            <el-table-column label="所需/可用" width="90"><template #default="{row}">{{ row.required_qty }} / <span :style="{color:row.available_qty<row.required_qty?'#ef4444':'#10b981'}">{{ row.available_qty }}</span></template></el-table-column>
            <el-table-column label="状态" width="75"><template #default="{row}"><span :class="'tag tag-'+matCls(row.status)" style="font-size:10px">{{ matLabel(row.status) }}</span></template></el-table-column>
            <el-table-column prop="supplier" label="供应商" width="90" />
            <el-table-column label="交期" width="55"><template #default="{row}">{{ row.lead_time_days||'?' }}天</template></el-table-column>
            <el-table-column label="操作" width="100"><template #default="{row}"><el-button link size="small" type="primary" @click="openMaterial(row)">编辑</el-button><el-popconfirm title="删除?" @confirm="delMaterial(row.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm></template></el-table-column>
          </el-table>
        </div>
      </div>

      <div v-else style="margin-top:8px">
        <el-button link size="small" @click="expandBuild(b)">展开 BOM & 物料齐套 ▼</el-button>
      </div>
    </div>

    <!-- Build Dialog -->
    <el-dialog v-model="showBuildDlg" :title="editingBuild ? '编辑批次' : '添加试制批次'" width="450px">
      <el-form :model="buildForm" label-width="80px"><el-form-item label="批次名称" required><el-input v-model="buildForm.batch_name" /></el-form-item><el-row :gutter="12"><el-col :span="6"><el-form-item label="计划数" label-width="50px"><el-input v-model.number="buildForm.planned_qty" type="number" min="1" /></el-form-item></el-col><el-col :span="6"><el-form-item label="实际数" label-width="50px"><el-input v-model.number="buildForm.actual_qty" type="number" min="0" /></el-form-item></el-col><el-col :span="12"><el-form-item label="状态" label-width="40px"><el-select v-model="buildForm.status" style="width:100%"><el-option label="计划中" value="planned" /><el-option label="备料中" value="material_ready" /><el-option label="装配中" value="in_progress" /><el-option label="已完成" value="completed" /></el-select></el-form-item></el-col></el-row><el-row :gutter="12"><el-col :span="12"><el-form-item label="开始"><el-date-picker v-model="buildForm.start_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col><el-col :span="12"><el-form-item label="结束"><el-date-picker v-model="buildForm.end_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col></el-row><el-form-item label="备注"><el-input v-model="buildForm.notes" type="textarea" :rows="2" /></el-form-item></el-form>
      <template #footer><el-button @click="showBuildDlg=false">取消</el-button><el-button type="primary" @click="saveBuild" :loading="saving">保存</el-button></template>
    </el-dialog>

    <!-- BOM Item Dialog -->
    <el-dialog v-model="showBomDlg" :title="editingBom ? '编辑物料' : '添加BOM物料'" width="480px">
      <el-form :model="bomForm" label-width="80px" size="small"><el-row :gutter="12"><el-col :span="12"><el-form-item label="物料号"><el-input v-model="bomForm.part_number" /></el-form-item></el-col><el-col :span="12"><el-form-item label="名称" required><el-input v-model="bomForm.name" /></el-form-item></el-col></el-row><el-form-item label="规格"><el-input v-model="bomForm.specification" /></el-form-item><el-row :gutter="12"><el-col :span="6"><el-form-item label="数量" label-width="40px"><el-input v-model.number="bomForm.quantity" type="number" min="0" /></el-form-item></el-col><el-col :span="6"><el-form-item label="单位" label-width="40px"><el-input v-model="bomForm.unit" /></el-form-item></el-col><el-col :span="6"><el-form-item label="材质" label-width="40px"><el-input v-model="bomForm.material" /></el-form-item></el-col><el-col :span="6"><el-form-item label="层级" label-width="40px"><el-input v-model.number="bomForm.level" type="number" min="0" /></el-form-item></el-col></el-row><el-form-item label="父物料" v-if="!editingBom || bomForm.parent_id"><el-select v-model="bomForm.parent_id" clearable style="width:100%" placeholder="（顶级）"><el-option v-for="i in flatBom" :key="i.id" :label="i.name" :value="i.id" :disabled="i.id===editingBom?.id" /></el-select></el-form-item><el-form-item label="供应商"><el-input v-model="bomForm.supplier" /></el-form-item></el-form>
      <template #footer><el-button @click="showBomDlg=false">取消</el-button><el-button type="primary" @click="saveBomItem" :loading="saving">保存</el-button></template>
    </el-dialog>

    <!-- Material Dialog -->
    <el-dialog v-model="showMatDlg" :title="editingMat ? '编辑检查项' : '添加物料检查'" width="480px">
      <el-form :model="matForm" label-width="80px"><el-form-item label="物料名称" required><el-input v-model="matForm.material_name" /></el-form-item><el-form-item label="规格"><el-input v-model="matForm.specification" /></el-form-item><el-row :gutter="12"><el-col :span="8"><el-form-item label="需求数"><el-input v-model.number="matForm.required_qty" type="number" min="0" /></el-form-item></el-col><el-col :span="8"><el-form-item label="可用数"><el-input v-model.number="matForm.available_qty" type="number" min="0" /></el-form-item></el-col><el-col :span="8"><el-form-item label="状态"><el-select v-model="matForm.status" style="width:100%"><el-option label="已就绪" value="ready" /><el-option label="已下单" value="ordered" /><el-option label="缺料" value="missing" /><el-option label="紧急" value="urgent" /></el-select></el-form-item></el-col></el-row><el-row :gutter="12"><el-col :span="12"><el-form-item label="供应商"><el-input v-model="matForm.supplier" /></el-form-item></el-col><el-col :span="12"><el-form-item label="交期(天)"><el-input v-model.number="matForm.lead_time_days" type="number" min="0" /></el-form-item></el-col></el-row></el-form>
      <template #footer><el-button @click="showMatDlg=false">取消</el-button><el-button type="primary" @click="saveMaterial" :loading="saving">保存</el-button></template>
    </el-dialog>

    <!-- BOM File Preview Dialog -->
    <el-dialog v-model="showPreview" :title="previewTitle" width="900px" top="20px">
      <div v-if="previewLoading" style="text-align:center;padding:40px">加载中...</div>
      <div v-else-if="previewHtml" v-html="previewHtml" style="max-height:70vh;overflow:auto"></div>
      <div v-else-if="previewError" style="color:#ef4444;padding:20px">{{ previewError }}</div>
    </el-dialog>

    <!-- AI BOM Result Dialog -->
    <el-dialog v-model="showAiBomDlg" title="🤖 AI 生成物料清单" width="800px">
      <div v-if="aiBomResult">
        <div v-if="aiBomResult.error" style="color:#ef4444;margin-bottom:12px">{{ aiBomResult.error }}</div>
        <div v-if="aiBomResult.ocr_text" style="margin-bottom:12px;font-size:12px;color:var(--text-muted);background:#f5f7fa;padding:8px;border-radius:4px;max-height:80px;overflow-y:auto">
          📷 识别文字: {{ aiBomResult.ocr_text }}
        </div>
        <el-table :data="aiBomResult.items||[]" size="small" max-height="380">
          <el-table-column prop="material_name" label="物料名称" width="160" />
          <el-table-column prop="specification" label="规格型号" width="180" />
          <el-table-column prop="required_qty" label="数量" width="60" />
          <el-table-column prop="category" label="类别" width="80" />
          <el-table-column prop="notes" label="备注" min-width="150" />
        </el-table>
        <div v-if="!(aiBomResult.items||[]).length" style="text-align:center;padding:30px;color:var(--text-muted)">未识别到物料</div>
      </div>
      <template #footer>
        <el-button @click="showAiBomDlg=false">取消</el-button>
        <el-button type="primary" @click="saveAiBom" :disabled="!(aiBomResult?.items?.length)">💾 保存到物料清单</el-button>
      </template>
    </el-dialog>
    <input type="file" ref="aiBomFile" accept="image/*,.pdf" style="display:none" @change="e => doAiBom(aiBomBuildId, e)" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })

const builds = ref([]); const expandedBuildId = ref(null); const saving = ref(false)

// BOM file upload state
const bomFiles = ref({})  // { [buildId]: [file objects] }
// AI BOM generation
const aiBomFile = ref(null); const aiBomLoading = ref(false); const aiBomResult = ref(null); const showAiBomDlg = ref(false); const aiBomBuildId = ref(null)
async function doAiBom(buildId, e) {
  const file = (e.target.files||[])[0]; if (!file) return
  aiBomLoading.value = true; aiBomBuildId.value = buildId
  const fd = new FormData(); fd.append('file', file)
  try {
    const r = await api.post('/bom/from-drawing', fd, { timeout: 180000 })
    aiBomResult.value = r.data; showAiBomDlg.value = true
  } catch(e) { ElMessage.error('识别失败: ' + (e?.response?.data?.detail || e.message)) }
  aiBomLoading.value = false
  e.target.value = ''
}
async function saveAiBom() {
  if (!aiBomResult.value?.items?.length) return
  try {
    // Map to material format
    const items = aiBomResult.value.items.map(i => ({
      material_name: i.name||i.material_name||'', specification: i.spec||i.specification||'',
      required_qty: i.qty||i.required_qty||1,
      supplier: i.supplier||'', notes: i.note||i.notes||''
    }))
    const r = await api.post(`/prototype-builds/${aiBomBuildId.value}/materials/batch`, { items })
    ElMessage.success(r.data.message)
    showAiBomDlg.value = false; aiBomResult.value = null
    if (aiBomBuildId.value) { expandBuild({id: aiBomBuildId.value}); loadMaterials(aiBomBuildId.value) }
  } catch(e) { ElMessage.error('保存失败') }
}
const bomFileInput = ref(null)
const pendingBuildId = ref(null)

function triggerBomUpload(buildId) {
  pendingBuildId.value = buildId
  bomFileInput.value?.click()
}

async function onBomFileSelected() {
  const buildId = pendingBuildId.value
  if (!buildId) return
  await uploadBomFile(buildId)
  bomFileInput.value.value = ''
}

// Material state
const materialChecks = ref([]); const showMatDlg = ref(false); const editingMat = ref(null)
const matForm = reactive({ material_name:'',specification:'',required_qty:0,available_qty:0,status:'ordered',supplier:'',lead_time_days:null })

// Build state
const showBuildDlg = ref(false); const editingBuild = ref(null)
const buildForm = reactive({ batch_name:'',planned_qty:1,actual_qty:null,start_date:null,end_date:null,status:'planned',notes:'' })

function buildStatusLabel(s) { const m={planned:'计划中',material_ready:'备料中',in_progress:'装配中',completed:'已完成'}; return m[s]||s }
function matLabel(s) { const m={ready:'就绪',ordered:'已下单',missing:'缺料',urgent:'紧急'}; return m[s]||s }
function matCls(s) { return s==='ready'?'green':s==='ordered'?'blue':s==='missing'?'orange':'red' }
function bMatMissing(b) { return b.material_missing||0 }
function bMatReady(b) { return b.material_ready||0 }

function bomMatStatus(bomItem) {
  const check = materialChecks.value.find(m => m.material_name === bomItem.name)
  if (!check) return null
  return check.available_qty >= (check.required_qty || bomItem.quantity * (builds.value.find(b=>b.id===expandedBuildId.value)?.planned_qty||1)) ? 'ready' : 'missing'
}

// BOM file upload
async function uploadBomFile(buildId) {
  const file = bomFileInput.value?.files?.[0]
  if (!file) return
  saving.value = true
  try {
    const fd = new FormData()
    fd.append('file', file)
    await api.post(`/prototype-builds/${buildId}/bom-files`, fd)
    ElMessage.success('BOM文件已上传')
    await loadBomFiles(buildId)
  } catch (e) {
    ElMessage.error('上传失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  saving.value = false
}

async function loadBomFiles(buildId) {
  try {
    const r = await api.get(`/prototype-builds/${buildId}/bom-files`)
    bomFiles.value = { ...bomFiles.value, [buildId]: r.data || [] }
  } catch {
    bomFiles.value = { ...bomFiles.value, [buildId]: [] }
  }
}

// BOM file preview
const showPreview = ref(false)
const previewTitle = ref('')
const previewHtml = ref('')
const previewError = ref('')
const previewLoading = ref(false)

async function previewBomFile(buildId, fileId) {
  showPreview.value = true
  previewTitle.value = 'BOM 文件预览'
  previewHtml.value = ''
  previewError.value = ''
  previewLoading.value = true
  try {
    const r = await api.get(`/prototype-builds/${buildId}/bom-files/${fileId}/preview`)
    const data = r.data
    if (data.error) {
      previewError.value = data.error
    } else if (data.html) {
      previewHtml.value = data.html
    } else if (data.text) {
      previewHtml.value = `<pre style="white-space:pre-wrap;font-family:monospace;font-size:13px">${data.text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre>`
    }
  } catch (e) {
    previewError.value = e?.response?.data?.detail || '预览失败'
  }
  previewLoading.value = false
}

async function delBomFile(buildId, fileId) {
  try {
    await api.delete(`/prototype-builds/${buildId}/bom-files/${fileId}`)
    ElMessage.success('已删除')
    await loadBomFiles(buildId)
  } catch { ElMessage.error('删除失败') }
}

onMounted(load)
async function load() { try { const r=await api.get(`/projects/${props.projectId}/prototype-builds`); builds.value=r.data||[]; if (!builds.value.find(b=>b.id===expandedBuildId.value)) { expandedBuildId.value=null; materialChecks.value=[] } } catch(e){builds.value=[]} }

async function expandBuild(b) {
  expandedBuildId.value = b.id
  try { const r=await api.get(`/prototype-builds/${b.id}/materials`); materialChecks.value=r.data||[] } catch(e){materialChecks.value=[]}
  await loadBomFiles(b.id)
}

// Build CRUD
function openBuild(row) {
  editingBuild.value = row || null
  const defaults = { batch_name:'', planned_qty:1, actual_qty:null, start_date:null, end_date:null, status:'planned', notes:'' }
  if (row) {
    Object.assign(buildForm, defaults, row)
  } else {
    Object.assign(buildForm, defaults)
  }
  showBuildDlg.value = true
}
async function saveBuild() { if(!buildForm.batch_name){ElMessage.warning('请输入名称');return}; saving.value=true; try{if(editingBuild.value){await api.put(`/prototype-builds/${editingBuild.value.id}`,{...buildForm})}else{await api.post(`/projects/${props.projectId}/prototype-builds`,{...buildForm})};ElMessage.success('已保存');showBuildDlg.value=false;editingBuild.value=null;await load()}catch(e){ElMessage.error('保存失败')}finally{saving.value=false} }
async function delBuild(id) { await api.delete(`/prototype-builds/${id}`); ElMessage.success('已删除'); await load() }

// Material CRUD
function openMaterial(row) { editingMat.value=row||null; Object.assign(matForm,row?{...row}:{material_name:'',specification:'',required_qty:0,available_qty:0,status:'ordered',supplier:'',lead_time_days:null}); showMatDlg.value=true }
async function saveMaterial() { if(!matForm.material_name){ElMessage.warning('请输入名称');return}; saving.value=true; try{if(editingMat.value){await api.put(`/materials/${editingMat.value.id}`,{...matForm})}else{await api.post(`/prototype-builds/${expandedBuildId.value}/materials`,{...matForm})};ElMessage.success('已保存');showMatDlg.value=false;editingMat.value=null;if(expandedBuildId.value)await expandBuild(builds.value.find(b=>b.id===expandedBuildId.value))}catch(e){ElMessage.error('保存失败')}finally{saving.value=false} }
async function delMaterial(id) { await api.delete(`/materials/${id}`); ElMessage.success('已删除'); if(expandedBuildId.value)await expandBuild(builds.value.find(b=>b.id===expandedBuildId.value)) }
</script>

<style scoped>
.build-card { border:1px solid var(--border); border-radius:8px; padding:16px; margin-bottom:12px; }
.build-hdr { display:flex; align-items:center; }
.build-name { font-weight:600; color:var(--text); font-size:15px; }
.build-meta { display:flex; gap:16px; margin-top:8px; font-size:12px; color:var(--text-secondary); }
</style>
