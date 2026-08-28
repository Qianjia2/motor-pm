<template>
  <div>
    <div class="card-header mb-md">
      <div style="display:flex;gap:8px;align-items:center">
        <el-input v-model="searchQuery" placeholder="搜索文档名..." size="small" style="width:180px" clearable @clear="load(1)" @keyup.enter="load(1)">
          <template #prefix><span style="font-size:12px">🔍</span></template>
        </el-input>
        <el-select v-model="filterPhase" placeholder="阶段筛选" clearable size="small" style="width:130px">
          <el-option v-for="g in docGroups" :key="g.id" :label="g.name" :value="g.id" />
        </el-select>
        <el-select v-model="filterType" placeholder="类型筛选" clearable size="small" style="width:140px">
          <el-option-group v-for="g in docGroups" :key="g.id" :label="g.name">
            <el-option v-for="t in g.types" :key="t.value" :label="t.label" :value="t.value" />
          </el-option-group>
        </el-select>
      </div>
      <div style="display:flex;gap:6px">
        <el-button size="small" @click="showNewFolder = true">📁 新建文件夹</el-button>
        <el-button size="small" @click="showTypeMgr = true">⚙ 管理类型</el-button>
        <el-button type="primary" size="small" @click="showUpload = true">
          <el-icon><Plus /></el-icon> 上传文件
        </el-button>
        <el-tooltip :content="isConnected ? `在线人数: ${presence.length}` : '实时协作未连接'" placement="bottom">
          <span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;margin-left:8px;white-space:nowrap">
            <span :style="{display:'inline-block',width:'8px',height:'8px',borderRadius:'50%',background:isConnected?'#67c23a':'#c0c4cc'}"></span>
            <span v-if="isConnected" style="color:#67c23a">实时在线 ({{ presence.length }}人)</span>
            <span v-else style="color:#c0c4cc">离线</span>
          </span>
        </el-tooltip>
      </div>
    </div>

    <!-- Batch action bar -->
    <div v-if="selectedIds.length > 0" style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:#ecf5ff;border-radius:6px;margin-bottom:10px">
      <span style="font-size:13px;font-weight:600">已选 {{ selectedIds.length }} 项</span>
      <el-button size="small" type="danger" @click="batchDelete">🗑 批量删除</el-button>
      <el-select v-model="batchMoveTarget" size="small" placeholder="移动到..." style="width:160px" clearable @change="onBatchMove">
        <el-option label="📁 根目录" value="" />
        <el-option v-for="f in folders" :key="f" :label="'📁 '+f" :value="f" />
      </el-select>
      <el-button size="small" @click="selectedIds = []">取消选择</el-button>
    </div>

    <!-- Folder sidebar + document area -->
    <div v-if="filteredDocs.length > 0" style="display:flex;gap:12px">
      <!-- Folder tree sidebar -->
      <div class="folder-sidebar">
        <div class="folder-tree-title">📁 文件夹</div>
        <div
          class="folder-tree-item"
          :class="{ active: currentFolder === '' }"
          @click="currentFolder = ''"
        >
          📂 全部文档
          <span class="folder-count">{{ docTotal }}</span>
        </div>
        <div
          v-for="f in folderTree"
          :key="f.path"
          class="folder-tree-item"
          :class="{ active: currentFolder === f.path, hidden: !isFolderVisible(f) }"
          :style="{ paddingLeft: (12 + f.level * 16) + 'px' }"
          @click="currentFolder = f.path"
        >
          <span style="cursor:pointer;margin-right:4px" @click.stop="toggleFolder(f.path)">
            {{ folderToggles[f.path] !== false ? '📂' : '📁' }}
          </span>
          {{ f.name }}
          <span class="folder-count">{{ f.count }}</span>
        </div>
        <div class="folder-tree-footer">
          <el-button link size="small" @click="showNewFolder = true">+ 新建文件夹</el-button>
        </div>
      </div>

      <!-- Document content area -->
      <div style="flex:1;min-width:0">
        <div v-if="currentFolder" style="font-size:13px;margin-bottom:8px;display:flex;align-items:center;gap:6px">
          <span style="color:var(--text-muted)">当前文件夹：</span>
          <el-tag size="small" closable @close="currentFolder = ''">📁 {{ currentFolder }}</el-tag>
        </div>

    <!-- Phase-grouped document list -->
    <template v-if="filteredDocs.length > 0">
      <div v-for="phase in visiblePhases" :key="phase.id" class="phase-section">
        <div class="phase-header" @click="phaseToggles[phase.id] = !phaseToggles[phase.id]">
          <div class="phase-header-left">
            <span style="transition:transform .2s;display:inline-block;font-size:12px" :style="{transform: phaseToggles[phase.id] ? 'rotate(90deg)' : 'rotate(0)'}">▶</span>
            <span class="phase-name">{{ phase.name }}</span>
            <el-tag size="small" :type="phase.color" effect="plain">{{ phase.docs.length }} 个文档</el-tag>
          </div>
          <span style="font-size:12px;color:var(--text-muted)">{{ phase.desc }}</span>
        </div>
        <div v-show="phaseToggles[phase.id] !== false" class="phase-body">
          <el-table :data="phase.docs" size="small" stripe @selection-change="(rows) => onPhaseSelection(phase.id, rows)">
            <el-table-column type="selection" width="36" />
            <el-table-column label="文档类型" width="110">
              <template #default="{row}">
                <span style="font-size:13px;color:var(--text-secondary)">{{ typeLabel(row.doc_type) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="文件夹" width="100">
              <template #default="{row}">
                <span v-if="row.folder" style="font-size:12px;color:var(--text-muted)">📁 {{ row.folder }}</span>
                <span v-else style="font-size:12px;color:#c0c4cc">-</span>
              </template>
            </el-table-column>
            <el-table-column label="文档名称" min-width="220" show-overflow-tooltip>
              <template #default="{row}">
                <div style="display:flex;align-items:center;gap:6px">
                  <el-tag v-if="row.status==='active'" type="success" size="small" effect="plain">有效</el-tag>
                  <el-tag v-else-if="row.status==='superseded'" type="warning" size="small" effect="plain">已替代</el-tag>
                  <el-tag v-else-if="row.status==='deprecated'" type="danger" size="small" effect="plain">失效</el-tag>
                  <el-tooltip v-if="row.broken_ref" content="引用文件已不存在（路径无效或文件被删除）" placement="top">
                    <span style="color:#f56c6c;font-size:12px;margin-right:2px">⚠️</span>
                  </el-tooltip>
                  <span v-if="row.file_path" style="cursor:pointer;color:#409eff" @click="openFile(row)" :style="{textDecoration:row.status!=='active'?'line-through':'none',opacity:row.status!=='active'?0.6:1}">
                    <template v-if="(row.notes||'').startsWith('路径引用')">🔗 </template>
                    V{{ row.version||1 }} {{ row.name }}
                  </span>
                  <span v-else-if="row.content" style="cursor:pointer;color:#409eff" @click="viewContent(row)">{{ row.name }}</span>
                  <span v-else :style="{textDecoration:row.status!=='active'?'line-through':'none'}">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="file_size" label="大小" width="80">
              <template #default="{row}">{{ row.file_size ? formatSize(row.file_size) : '-' }}</template>
            </el-table-column>
            <el-table-column prop="uploaded_by" label="上传人" width="70" />
            <el-table-column prop="upload_date" label="日期" width="100" sortable />
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{row}">
                <el-dropdown v-if="row.file_path||row.content" @command="(fmt)=>downloadDoc(row,fmt)">
                  <el-button link size="small" type="primary">下载</el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="md">Markdown</el-dropdown-item>
                      <el-dropdown-item command="docx">Word</el-dropdown-item>
                      <el-dropdown-item command="pptx">PPT</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
                <el-button v-if="row.status==='active'" type="warning" link size="small" @click="deprecateDoc(row.id)">失效</el-button>
                <el-button v-if="row.status==='active'" type="success" link size="small" @click="replaceDoc(row)">替换</el-button>
                <el-button v-if="row.content" type="primary" link size="small" @click="editContent(row)">编辑</el-button>
                <el-button type="primary" link size="small" @click="editDoc(row)">属性</el-button>
                <el-popconfirm title="确认删除?" @confirm="delDoc(row.id)">
                  <template #reference><el-button type="danger" link size="small">删除</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </template>
      <!-- Pagination -->
      <div v-if="docPages > 1" style="display:flex;justify-content:center;margin-top:12px">
        <el-pagination
          v-model:current-page="docPage"
          :page-size="DOC_PAGE_SIZE"
          :total="docTotal"
          layout="prev, pager, next, total"
          small
          @current-change="(p) => load(p)"
        />
      </div>
      </div><!-- end document area -->
    </div><!-- end flex layout -->

    <div v-else-if="docTotal === 0" style="text-align:center;padding:40px;color:#c0c4cc">
      <el-icon :size="40"><FolderOpened /></el-icon>
      <p>暂无项目文档，点击"上传文件"添加</p>
      <p style="font-size:12px">P0需求阶段：合同/协议/需求书/立项报告</p>
      <p style="font-size:12px">PP1研发阶段：模型/设计报告/图纸/测试方案</p>
      <p style="font-size:12px">PP2验证阶段：测试报告/数据回归/改进计划和报告</p>
    </div>

    <div v-else style="text-align:center;padding:40px;color:#c0c4cc">
      当前文件夹为空
    </div>

    <!-- 文档类型管理弹窗 -->
    <el-dialog v-model="showTypeMgr" title="文档类型管理" width="650px">
      <div v-for="g in editableDocGroups" :key="g.id" style="margin-bottom:12px">
        <h4 style="margin:0 0 6px;font-size:14px">{{ g.name }}</h4>
        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <el-tag v-for="(t,i) in g.types" :key="t.value" closable @close="removeType(g.id, i)" size="small">{{ t.label }}</el-tag>
        </div>
        <div style="display:flex;gap:4px;margin-top:6px">
          <el-input v-model="newTypeLabels[g.id]" size="small" placeholder="新类型名称" style="width:140px" @keyup.enter="addType(g.id)" />
          <el-button size="small" @click="addType(g.id)">添加</el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="showTypeMgr = false">取消</el-button>
        <el-button type="primary" @click="saveDocTypes" :loading="savingTypes">保存</el-button>
      </template>
    </el-dialog>

    <!-- 替换文件弹窗 -->
    <el-dialog v-model="showReplace" title="替换文件 - 上传新版本" width="450px">
      <div style="margin-bottom:12px;font-size:13px;color:#606266">
        正在替换：<strong>{{ replaceTarget?.name }}</strong>（V{{ replaceTarget?.version || 1 }}）
      </div>
      <el-form label-width="80px">
        <el-form-item label="新文件">
          <el-upload :auto-upload="false" :limit="1" :on-change="onReplaceFileChange" drag>
            <el-icon :size="28"><UploadFilled /></el-icon>
            <div style="font-size:12px;color:#909399">上传新版本文件</div>
          </el-upload>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="replaceNotes" type="textarea" :rows="2" placeholder="说明替换原因" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReplace = false">取消</el-button>
        <el-button type="primary" @click="confirmReplace" :loading="uploading">确认替换</el-button>
      </template>
    </el-dialog>

    <!-- 上传弹窗 -->
    <!-- Content editor dialog -->
    <el-dialog v-model="showContentEditor" :title="'编辑内容 - ' + (editingContentDoc?.name || '')" width="900px" top="3vh">
      <el-input v-model="editingContent" type="textarea" :rows="24" style="font-size:13px;line-height:1.8;font-family:monospace" placeholder="Markdown 内容..." />
      <template #footer>
        <el-button @click="showContentEditor = false">取消</el-button>
        <el-button type="primary" @click="saveContent" :loading="savingContent">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showUpload" :title="editingDoc ? '编辑文档' : '上传项目文档'" width="500px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="所属阶段" required>
          <el-select v-model="form.doc_phase" style="width:100%" @change="onPhaseChange">
            <el-option v-for="g in docGroups" :key="g.id" :label="g.name" :value="g.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档类型" required>
          <el-select v-model="form.doc_type" style="width:100%">
            <el-option v-for="t in currentTypes" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档名称" required>
          <el-input v-model="form.name" placeholder="如：200kW电机电磁方案设计报告" />
        </el-form-item>
        <el-form-item label="存放文件夹">
          <el-select v-model="form.folder" style="width:100%" clearable placeholder="根目录（不分类）" allow-create filterable>
            <el-option label="📁 根目录（不分类）" value="" />
            <el-option v-for="f in folders" :key="f" :label="'📁 '+f" :value="f" />
          </el-select>
        </el-form-item>
        <el-form-item label="上传方式" v-if="!editingDoc">
          <el-radio-group v-model="uploadMode" size="small" style="margin-bottom:6px">
            <el-radio-button value="file">单个文件</el-radio-button>
            <el-radio-button value="folder">整个文件夹</el-radio-button>
            <el-radio-button value="ref">🔗 路径引用</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="!editingDoc && uploadMode === 'ref'" label="文件路径">
          <el-input v-model="refPath" placeholder="Z:\项目资料\设计报告.pdf 或 \\server\share\file.pdf">
            <template #append><el-button @click="quickImportRef">添加</el-button></template>
          </el-input>
          <div v-if="refList.length" style="margin-top:6px">
            <el-tag v-for="(r,i) in refList" :key="i" size="small" closable @close="refList.splice(i,1)" style="margin:2px">📎 {{ r.name }}</el-tag>
            <span style="font-size:12px;color:var(--text-muted)">已添加 {{ refList.length }} 个引用（不占用存储空间）</span>
          </div>
        </el-form-item>
        <el-form-item v-if="!editingDoc && uploadMode === 'file'">
          <el-upload ref="uploadRef" :auto-upload="false" :limit="1" :on-change="onFileChange" :on-remove="onFileRemove" drag>
            <el-icon :size="28"><UploadFilled /></el-icon>
            <div style="font-size:12px;color:#909399">点击或拖拽上传单个文件</div>
          </el-upload>
        </el-form-item>
        <el-form-item v-if="!editingDoc && uploadMode === 'folder'">
          <input type="file" ref="folderInput" webkitdirectory multiple style="display:none" @change="onFolderPicked" />
          <div @click="$refs.folderInput.click()" style="border:2px dashed var(--el-border-color);border-radius:8px;padding:28px;text-align:center;cursor:pointer">
            <div style="font-size:28px;margin-bottom:6px">📂</div>
            <div style="font-size:12px;color:#909399">点击选择整个文件夹</div>
            <div v-if="folderFiles.length" style="margin-top:8px;font-size:12px;color:#409eff">
              已选 {{ folderFiles.length }} 个文件 → 自动归入文件夹 "{{ folderFiles[0]?.relativeFolder }}"
            </div>
          </div>
        </el-form-item>
        <el-form-item label="上传人">
          <el-input v-model="form.uploaded_by" placeholder="填写人姓名" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" :rows="2" placeholder="补充说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="saveDoc" :loading="uploading">保存</el-button>
      </template>
    </el-dialog>

    <!-- Content view dialog -->
    <el-dialog v-model="showContent" :title="viewingDoc?.name || '文档预览'" width="800px" top="5vh">
      <div class="markdown-body" v-html="renderedDocContent" style="max-height:70vh;overflow-y:auto;font-size:14px;line-height:1.8"></div>
    </el-dialog>

    <!-- New folder dialog -->
    <el-dialog v-model="showNewFolder" title="新建文件夹" width="380px">
      <el-input v-model="newFolderName" placeholder="输入文件夹名称" @keyup.enter="createFolder" />
      <template #footer>
        <el-button @click="showNewFolder = false">取消</el-button>
        <el-button type="primary" @click="createFolder" :disabled="!newFolderName.trim()">创建</el-button>
      </template>
    </el-dialog>

    <!-- File preview dialog -->
    <el-dialog v-model="showFilePreview" :title="previewDoc?.name || '文件预览'" width="900px" top="2vh">
      <div v-if="previewLoading" style="text-align:center;padding:40px;color:var(--text-muted)">⏳ 正在加载预览...</div>
      <div v-else-if="previewError" style="text-align:center;padding:40px;color:#e6a23c">{{ previewError }}</div>
      <iframe v-else :srcdoc="previewHtml" style="width:100%;height:65vh;border:1px solid #eee;border-radius:4px"></iframe>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api/index.js'
import { useRealtime } from '../../composables/useRealtime.js'

const props = defineProps({ projectId: { type: Number, required: true } })

// ── Real-time collaboration WebSocket ──
const { isConnected, presence, lastChange, connect, disconnect, sendChange } = useRealtime('project_docs', props.projectId)

const docs = ref([])
const docGroups = ref([])
const folders = ref([])
const currentFolder = ref('')
const searchQuery = ref('')
const showNewFolder = ref(false)
const selectedIds = ref([])
const batchMoveTarget = ref('')
const phaseSelections = ref({})

function onPhaseSelection(phaseId, rows) {
  phaseSelections.value[phaseId] = rows
  // Collect all selected IDs across all phases
  const ids = []
  for (const pid of Object.keys(phaseSelections.value)) {
    for (const r of phaseSelections.value[pid]) {
      ids.push(r.id)
    }
  }
  selectedIds.value = ids
}

async function batchDelete() {
  if (!selectedIds.value.length) return
  try {
    await ElMessageBox.confirm(`确认删除 ${selectedIds.value.length} 个文档？`, '批量删除', { type: 'warning' })
    await api.post(`/projects/${props.projectId}/docs/batch`, { ids: selectedIds.value, action: 'delete' })
    ElMessage.success(`已删除 ${selectedIds.value.length} 个文档`)
    sendChange({ action: 'batch_delete', count: selectedIds.value.length })
    selectedIds.value = []
    phaseSelections.value = {}
    await load()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e?.response?.data?.detail || '删除失败')
  }
}

async function onBatchMove(folder) {
  if (!selectedIds.value.length || folder === undefined) return
  try {
    await api.post(`/projects/${props.projectId}/docs/batch`, { ids: selectedIds.value, action: 'move', folder: folder })
    ElMessage.success(`已移动 ${selectedIds.value.length} 个文档`)
    selectedIds.value = []
    phaseSelections.value = {}
    batchMoveTarget.value = ''
    await load()
  } catch (e) {
    ElMessage.error(e?.response?.data?.detail || '移动失败')
  }
}
const newFolderName = ref('')
const showContent = ref(false)
const viewingDoc = ref(null)
const showContentEditor = ref(false)
const editingContentDoc = ref(null)
const editingContent = ref('')
const savingContent = ref(false)

function editContent(row) {
  editingContentDoc.value = row
  editingContent.value = row.content || ''
  showContentEditor.value = true
}

async function saveContent() {
  if (!editingContentDoc.value) return
  savingContent.value = true
  try {
    await api.put(`/docs/${editingContentDoc.value.id}`, {
      name: editingContentDoc.value.name,
      doc_type: editingContentDoc.value.doc_type,
      content: editingContent.value,
    })
    editingContentDoc.value.content = editingContent.value
    ElMessage.success('内容已保存')
    showContentEditor.value = false
  } catch(e) { ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || '')) }
  finally { savingContent.value = false }
}
const showTypeMgr = ref(false)
const editableDocGroups = ref([])
const newTypeLabels = reactive({})
const savingTypes = ref(false)

async function loadDocTypes() {
  try { const r = await api.get('/lookups/doc-types'); editableDocGroups.value = JSON.parse(JSON.stringify(r.data.groups || [])) }
  catch(e) {}
}

function addType(groupId) {
  const label = (newTypeLabels[groupId] || '').trim()
  if (!label) return
  const group = editableDocGroups.value.find(g => g.id === groupId)
  if (!group) return
  const value = groupId.toLowerCase() + '_' + label.replace(/[^a-zA-Z0-9一-鿿]/g, '_').toLowerCase()
  if (group.types.some(t => t.value === value)) { return }
  group.types.push({ value, label })
  newTypeLabels[groupId] = ''
}

function removeType(groupId, idx) {
  const group = editableDocGroups.value.find(g => g.id === groupId)
  if (group) group.types.splice(idx, 1)
}

async function saveDocTypes() {
  savingTypes.value = true
  try {
    await api.put('/lookups/doc-types', { groups: editableDocGroups.value })
    docGroups.value = JSON.parse(JSON.stringify(editableDocGroups.value))
    ElMessage.success('文档类型已保存')
    showTypeMgr.value = false
  } catch(e) { ElMessage.error('保存失败') }
  finally { savingTypes.value = false }
}

const renderedDocContent = computed(() => {
  const text = viewingDoc.value?.content || ''
  return text
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" style="max-width:100%;border-radius:4px;margin:8px 0">')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n## (.+)/g, '<h4>$1</h4>')
    .replace(/\n### (.+)/g, '<h3>$1</h3>')
    .replace(/\n- (.+)/g, '• $1')
    .replace(/\n/g, '<br>')
})

function viewContent(row) {
  viewingDoc.value = row
  showContent.value = true
}
const filterPhase = ref('')
const filterType = ref('')
const showUpload = ref(false)
const uploading = ref(false)
const editingDoc = ref(null)
const uploadRef = ref(null)
const uploadFile = ref(null)
const uploadMode = ref('file')
const folderFiles = ref([])
const refPath = ref('')
const refList = ref([])

function quickImportRef() {
  const p = refPath.value.trim()
  if (!p) return
  const parts = p.replace(/\\/g, '/').split('/')
  const name = parts.pop() || p
  refList.value.push({ path: p, name })
  refPath.value = ''
}
const folderUploading = ref(false)
const folderProgress = ref({ current: 0, total: 0 })

// Replace dialog
const showReplace = ref(false)
const replaceTarget = ref(null)
const replaceFile = ref(null)
const replaceNotes = ref('')

const form = reactive({ name: '', doc_type: 'p0_contract', doc_phase: 'P0', folder: '', uploaded_by: '', notes: '' })

const allTypes = computed(() => {
  const types = []
  for (const g of docGroups.value) {
    for (const t of g.types) types.push(t)
  }
  return types
})

const currentTypes = computed(() => {
  const group = docGroups.value.find(g => g.id === form.doc_phase)
  return group ? group.types : []
})

const filteredDocs = computed(() => {
  let list = docs.value
  if (filterPhase.value) {
    const group = docGroups.value.find(g => g.id === filterPhase.value)
    if (group) {
      const typeValues = group.types.map(t => t.value)
      list = list.filter(d => typeValues.includes(d.doc_type))
    }
  }
  if (filterType.value) {
    list = list.filter(d => d.doc_type === filterType.value)
  }
  return list
})

// Always sort by upload_date desc (newest first) by default
// Folder tree — loaded from lightweight API (no file data)
const folderTree = ref([])
const rootDocCount = ref(0)

async function loadFolderTree() {
  try {
    const r = await api.get(`/projects/${props.projectId}/doc-folders`)
    const data = r.data || {}
    folderTree.value = data.tree || []
    rootDocCount.value = data.root_count || 0
    // Init toggles for new folders
    for (const f of folderTree.value) {
      if (!(f.path in folderToggles.value)) folderToggles.value[f.path] = true
    }
  } catch {}
}

const sortedDocs = computed(() => {
  return [...filteredDocs.value].sort((a, b) => {
    if (!a.upload_date) return 1
    if (!b.upload_date) return -1
    return b.upload_date.localeCompare(a.upload_date)
  })
})

const PHASE_ORDER = ['P0', 'PP1', 'PP2', 'PP3', 'PP4']
const PHASE_COLORS = { P0: '', PP1: 'warning', PP2: 'success', PP3: 'danger', PP4: 'info' }
const PHASE_DESCS = {
  P0: '合同、协议、需求书、立项报告',
  PP1: '模型、设计报告、图纸、测试方案',
  PP2: '测试报告、数据回归、改进计划',
  PP3: '小批量验证、可靠性测试',
  PP4: '定型文件、总结报告、量产移交',
}
const PHASE_NAME_MAP = { 'P0': '概念需求阶段', 'PP1': '方案设计阶段', 'PP2': '样机试制阶段', 'PP3': '验证阶段', 'PP4': '设计定型阶段' }

const phaseToggles = ref({})
const folderToggles = ref({})

const visiblePhases = computed(() => {
  const grouped = {}
  for (const d of sortedDocs.value) {
    const phase = extractPhaseCode(d.doc_type)
    if (!grouped[phase]) grouped[phase] = []
    grouped[phase].push(d)
  }
  return PHASE_ORDER.filter(p => grouped[p] && grouped[p].length > 0).map(p => {
    if (!(p in phaseToggles.value)) phaseToggles.value[p] = true
    return {
      id: p,
      name: `${p} ${PHASE_NAME_MAP[p] || ''}`,
      desc: PHASE_DESCS[p] || '',
      color: PHASE_COLORS[p] || 'info',
      docs: grouped[p],
    }
  })
})

function extractPhaseCode(t) { if(!t)return'PP2'; if(t.startsWith('p0_'))return'P0'; if(t.startsWith('pp1_'))return'PP1'; if(t.startsWith('pp2_'))return'PP2'; if(t.startsWith('pp3_'))return'PP3'; if(t.startsWith('pp4_'))return'PP4'; return'PP2' }
function phaseTag(t) {
  const c = extractPhaseCode(t); if(c==='P0')return''; if(c==='PP1')return'warning'; if(c==='PP2')return'success'; if(c==='PP3')return'danger'; return'info'
}

function typeLabel(t) {
  if(!t)return'-'; if(t.includes('_ai_'))return'AI生成报告'
  return allTypes.value.find(x => x.value === t)?.label || t
}

function phaseLabel(row) {
  const t = row.doc_type || ''; const code = extractPhaseCode(t)
  if(PHASE_NAME_MAP[code])return PHASE_NAME_MAP[code]
  const group = docGroups.value.find(g => g.types.some(x => x.value === t))
  return group ? group.name : ''
}

function onPhaseChange() {
  if (currentTypes.value.length > 0) {
    form.doc_type = currentTypes.value[0].value
  }
}

function formatSize(bytes) {
  if (!bytes) return '-'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / (1024 * 1024)).toFixed(1) + 'MB'
}

const showFilePreview = ref(false)
const previewDoc = ref(null)
const previewHtml = ref('')
const previewLoading = ref(false)
const previewError = ref('')

async function openFile(row) {
  if (!row.id) {
    window.open(row.file_path, '_blank')
    return
  }
  previewDoc.value = row
  previewLoading.value = true
  previewError.value = ''
  previewHtml.value = ''
  showFilePreview.value = true
  try {
    const r = await api.get(`/docs/${row.id}/preview`, { responseType: 'text', timeout: 30000 })
    previewHtml.value = r.data || r
  } catch (e) {
    previewError.value = '加载预览失败: ' + (e?.response?.data?.detail || e.message)
  } finally {
    previewLoading.value = false
  }
}

async function downloadDoc(row, fmt) {
  if (!fmt) fmt = 'md'
  const name = row.name || '文档'

  // File-based: just download the file
  if (row.file_path) {
    if (fmt === 'md') {
      const a = document.createElement('a')
      a.href = row.file_path
      a.download = name
      a.click()
      return
    }
    // For docx/pptx, cannot convert file — fallback to direct download
    ElMessage.warning('文件类文档仅支持原始格式下载')
    return
  }

  // Content-based: use backend export
  if (row.content) {
    if (fmt === 'md') {
      const blob = new Blob([row.content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url
      a.download = name + '.md'; a.click()
      URL.revokeObjectURL(url)
      return
    }
    if (fmt === 'docx' || fmt === 'pptx') {
      try {
        const r = await api.post('/report-gen/export/' + fmt, { content: row.content, title: name }, { responseType: 'arraybuffer', timeout: 60000 })
        const blob = new Blob([r.data], { type: fmt === 'docx' ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' : 'application/vnd.openxmlformats-officedocument.presentationml.presentation' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a'); a.href = url
        a.download = name + '.' + fmt; a.click()
        URL.revokeObjectURL(url)
        ElMessage.success((fmt === 'docx' ? 'Word' : 'PPT') + ' 下载完成')
      } catch(e) { ElMessage.error((fmt === 'docx' ? 'Word' : 'PPT') + ' 导出失败: ' + (e?.response?.data?.detail || e?.message || '未知错误')) }
      return
    }
  }
}
async function createFolder() {
  const name = newFolderName.value.trim()
  if (!name) return
  if (!folders.value.includes(name)) {
    folders.value.push(name)
    // Persist to backend registry so empty folder survives doc deletion
    try { await api.post(`/projects/${props.projectId}/doc-folders`, {name}) } catch {}
  }
  showNewFolder.value = false
  newFolderName.value = ''
  form.folder = name
  ElMessage.success(`文件夹 "${name}" 已创建，上传文档时选择即可`)
}

function toggleFolder(path) {
  folderToggles.value[path] = !folderToggles.value[path]
}
function isFolderVisible(f) {
  if (!f.level) return true // root-level always visible
  // Check all parent folders are expanded
  let parent = f.path.includes('/') ? f.path.substring(0, f.path.lastIndexOf('/')) : ''
  while (parent) {
    if (folderToggles.value[parent] === false) return false
    parent = parent.includes('/') ? parent.substring(0, parent.lastIndexOf('/')) : ''
  }
  return folderToggles.value[''] !== false
}

async function loadFolders() {
  try {
    const r = await api.get(`/projects/${props.projectId}/doc-folders`)
    folders.value = r.data || []
  } catch {}
}

function onFileChange(file) {
  uploadFile.value = file.raw
  if (!form.name) {
    form.name = file.name.replace(/\.[^.]+$/, '')
  }
}
function onFileRemove() { uploadFile.value = null; form.name = '' }

// ── Folder upload ──
async function onFolderPicked(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length) return

  const firstPath = files[0].webkitRelativePath || files[0].name
  const folderName = firstPath.includes('/') ? firstPath.split('/')[0] : ''
  form.folder = form.folder || folderName

  folderFiles.value = files.map(f => {
    const rel = f.webkitRelativePath || f.name
    const parts = rel.split('/')
    parts.shift()
    const sub = parts.length > 1 ? parts.slice(0, -1).join('/') : ''
    return {
      file: f,
      name: f.name,
      relativeFolder: folderName + (sub ? '/' + sub : ''),
    }
  })
  e.target.value = ''
}

function editDoc(row) {
  editingDoc.value = row
  form.name = row.name
  form.doc_type = row.doc_type
  form.folder = row.folder || ''
  form.uploaded_by = row.uploaded_by || ''
  form.notes = row.notes || ''
  form.doc_phase = extractPhaseCode(row.doc_type)
  showUpload.value = true
}

async function saveDoc() {
  if (!form.name) { ElMessage.warning('请输入文档名称'); return }
  uploading.value = true
  try {
    if (editingDoc.value) {
      await api.put(`/docs/${editingDoc.value.id}`, {
        name: form.name, doc_type: form.doc_type, folder: form.folder, notes: form.notes,
      })
      ElMessage.success('已更新')
    } else if (uploadMode.value === 'ref' && refList.value.length) {
      for (const r of refList.value) {
        await api.post(`/projects/${props.projectId}/docs/add-ref`, {
          file_path: r.path.replace(/\\/g, '/'),
          name: r.name.replace(/\.[^.]+$/, ''),
          doc_type: form.doc_type || 'pp2_report',
          folder: form.folder,
          notes: '路径引用，不占用空间',
        })
      }
      ElMessage.success(`已添加 ${refList.value.length} 个文件引用（不占用空间）`)
      refList.value = []
    } else if (uploadMode.value === 'folder' && folderFiles.value.length) {
      // Batch folder upload — show progress, batch errors
      const BATCH_SIZE = 10
      const total = folderFiles.value.length
      let done = 0
      let failed = 0
      const errors = []
      const errorCounts = {}
      const loadingMsg = ElMessage({ message: `正在导入 0/${total}...`, type: 'info', duration: 0 })

      for (let i = 0; i < total; i += BATCH_SIZE) {
        const batch = folderFiles.value.slice(i, i + BATCH_SIZE)
        await Promise.all(batch.map(async (f) => {
          try {
            const fd2 = new FormData()
            fd2.append('name', f.name.replace(/\.[^.]+$/, ''))
            fd2.append('doc_type', form.doc_type)
            fd2.append('folder', f.relativeFolder)
            fd2.append('uploaded_by', form.uploaded_by)
            fd2.append('notes', form.notes || '批量导入')
            fd2.append('file', f.file)
            await api.post(`/projects/${props.projectId}/docs`, fd2, {
              headers: { 'Content-Type': 'multipart/form-data' },
              timeout: 60000,
            })
            done++
          } catch (e) {
            failed++
            const detail = e?.response?.data?.detail || e.message || '未知错误'
            errorCounts[detail] = (errorCounts[detail] || 0) + 1
            if (errors.length < 20) errors.push(`${f.name}: ${detail}`)
          }
        }))
        loadingMsg.message = `正在导入 ${done + failed}/${total}...`
      }

      loadingMsg.close()
      folderFiles.value = []
      if (uploadRef.value) uploadRef.value.clearFiles()

      // Build detailed error summary
      const errorSummary = Object.entries(errorCounts)
        .sort((a, b) => b[1] - a[1])
        .map(([msg, count]) => `${count}个: ${msg}`)
        .join('\n')

      let msg = `成功 ${done} 个`
      if (failed) msg += `，失败 ${failed} 个`
      if (errorSummary) msg += `\n\n【失败原因统计】\n${errorSummary}`
      if (errors.length >= 20) msg += `\n\n（仅显示前20条详情）`

      // Use a dialog for long error messages
      if (failed > 20) {
        ElMessageBox.alert(errorSummary, `导入结果：成功 ${done} / 失败 ${failed}`, {
          confirmButtonText: '知道了',
          type: 'warning',
          dangerouslyUseHTMLString: false,
        })
      } else {
        ElMessage({ message: msg, type: failed ? 'warning' : 'success', duration: 10000, showClose: true })
      }
    } else {
      const fd = new FormData()
      fd.append('name', form.name)
      fd.append('doc_type', form.doc_type)
      fd.append('folder', form.folder)
      fd.append('uploaded_by', form.uploaded_by)
      fd.append('notes', form.notes)
      if (uploadFile.value) fd.append('file', uploadFile.value)
      await api.post(`/projects/${props.projectId}/docs`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      ElMessage.success('已上传')
    }
    const wasEdit = !!editingDoc.value
    showUpload.value = false
    editingDoc.value = null
    uploadFile.value = null
    uploadMode.value = 'file'
    folderFiles.value = []
    refList.value = []
    refPath.value = ''
    form.name = ''
    form.folder = ''
    form.notes = ''
    if (uploadRef.value) uploadRef.value.clearFiles()
    sendChange({ action: wasEdit ? 'update' : 'upload' })
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  } finally {
    uploading.value = false
  }
}

async function delDoc(id) {
  await api.delete(`/docs/${id}`)
  ElMessage.success('已删除')
  sendChange({ action: 'delete', doc_id: id })
  await load()
}

async function deprecateDoc(id) {
  try {
    await api.post(`/docs/${id}/deprecate`)
    ElMessage.success('已标记为失效')
    sendChange({ action: 'deprecate', doc_id: id })
    await load()
  } catch (e) {
    ElMessage.error('操作失败')
  }
}

function replaceDoc(row) {
  replaceTarget.value = row
  replaceNotes.value = ''
  replaceFile.value = null
  showReplace.value = true
}

function onReplaceFileChange(file) { replaceFile.value = file.raw }

async function confirmReplace() {
  if (!replaceFile.value) { ElMessage.warning('请选择新文件'); return }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('file', replaceFile.value)
    fd.append('name', replaceTarget.value.name)
    fd.append('doc_type', replaceTarget.value.doc_type)
    fd.append('uploaded_by', replaceTarget.value.uploaded_by || '')
    fd.append('notes', replaceNotes.value || `替换 V${replaceTarget.value.version || 1}`)
    await api.post(`/docs/${replaceTarget.value.id}/replace`, fd, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    ElMessage.success('文件已替换，旧版本标记为已替代')
    sendChange({ action: 'replace', doc_id: replaceTarget.value?.id })
    showReplace.value = false
    replaceTarget.value = null
    await load()
  } catch (e) {
    ElMessage.error('替换失败')
  } finally {
    uploading.value = false
  }
}

const docPage = ref(1)
const docTotal = ref(0)
const docPages = ref(1)
const DOC_PAGE_SIZE = 50

async function load(page = 1) {
  const params = { page, page_size: DOC_PAGE_SIZE }
  if (currentFolder.value) params.folder = currentFolder.value
  if (searchQuery.value) params.search = searchQuery.value
  if (filterType.value) params.doc_type = filterType.value

  const [docsRes, typesRes] = await Promise.all([
    api.get(`/projects/${props.projectId}/docs`, { params }),
    api.get('/lookups/doc-types'),
  ])
  // Handle paginated response
  const data = docsRes.data
  if (data && Array.isArray(data.items)) {
    docs.value = data.items
    docTotal.value = data.total
    docPage.value = data.page
    docPages.value = data.pages
  } else {
    // Backward compatibility with old flat array response
    docs.value = Array.isArray(data) ? data : (data.items || [])
    docTotal.value = docs.value.length
    docPages.value = 1
  }
  docGroups.value = typesRes.data.groups || []
  if (docGroups.value.length > 0 && docGroups.value[0].types.length > 0) {
    form.doc_type = docGroups.value[0].types[0].value
  }
  loadFolderTree()
  loadFolders()
}

onMounted(() => { load(1); connect() })
onUnmounted(() => disconnect())
// Reconnect if projectId changes
watch(() => props.projectId, () => {
  disconnect()
  connect()
  load(1)
})
// Auto-refresh when remote changes arrive (debounced)
let remoteRefreshTimer = null
watch(lastChange, (change) => {
  if (!change) return
  clearTimeout(remoteRefreshTimer)
  remoteRefreshTimer = setTimeout(() => load(1), 300)
})
watch(currentFolder, () => load(1))
watch(filterType, () => load(1))
let searchTimer = null
watch(searchQuery, (v) => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => load(1), 300)
})
watch(showTypeMgr, (v) => { if(v) { editableDocGroups.value = JSON.parse(JSON.stringify(docGroups.value)) } })
</script>

<style scoped>
.phase-section {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.phase-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--bg);
  cursor: pointer;
  user-select: none;
  transition: background .15s;
}
.phase-header:hover { background: #f0f2f5; }
.phase-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.phase-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.phase-body {
  border-top: 1px solid var(--border);
}
.phase-body .el-table {
  border-radius: 0;
}
.folder-sidebar {
  width: 200px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fafafa;
  overflow-y: auto;
  max-height: 500px;
}
.folder-tree-title {
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  border-bottom: 1px solid var(--border);
}
.folder-tree-item {
  padding: 7px 12px;
  font-size: 13px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: background .15s;
  border-bottom: 1px solid #f0f0f0;
}
.folder-tree-item:hover { background: #ecf5ff; }
.folder-tree-item.active {
  background: #d9ecff;
  color: #409eff;
  font-weight: 500;
}
.folder-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  background: #eee;
  padding: 1px 6px;
  border-radius: 10px;
}
.folder-tree-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}
.folder-tree-item.hidden { display: none; }
</style>
