<template>
  <div>
    <div class="card-header mb-md">
      <span></span>
      <el-button size="small" type="primary" @click="openItem()"><el-icon><Plus /></el-icon> 添加物料</el-button>
    </div>
    <div v-if="flatItems.length===0" style="text-align:center;padding:40px;color:var(--text-muted)">暂无BOM</div>
    <el-table v-else :data="displayBom" stripe size="small" row-key="id" default-expand-all
      :tree-props="{children:'children',hasChildren:'hasChildren'}">
      <el-table-column label="层级" width="45"><template #default="{row}">L{{ row.level||0 }}</template></el-table-column>
      <el-table-column prop="part_number" label="物料号" width="120" />
      <el-table-column label="物料名称" min-width="180">
        <template #default="{row}"><span :style="{fontWeight:row.level===0?'600':'400'}">{{ row.name }}</span></template>
      </el-table-column>
      <el-table-column prop="specification" label="规格" width="140" show-overflow-tooltip />
      <el-table-column prop="material" label="材质" width="90" />
      <el-table-column label="数量" width="70"><template #default="{row}">{{ row.quantity }}{{ row.unit }}</template></el-table-column>
      <el-table-column prop="supplier" label="供应商" width="100" />
      <el-table-column label="图纸" width="60">
        <template #default="{row}"><span v-if="row.drawing_file">📄</span></template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="{row}">
          <el-button link size="small" type="primary" @click="openItem(row)">编辑</el-button>
          <el-button link size="small" @click="openItem({parent_id:row.id,level:(row.level||0)+1})">子件</el-button>
          <el-popconfirm title="删除?" @confirm="delItem(row.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDlg" :title="editing ? '编辑物料' : '添加物料'" width="500px">
      <el-form :model="form" label-width="80px" size="small">
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="物料号"><el-input v-model="form.part_number" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="规格"><el-input v-model="form.specification" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="数量"><el-input-number v-model="form.quantity" :min="0" style="width:100%" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="单位"><el-input v-model="form.unit" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="材质"><el-input v-model="form.material" /></el-form-item></el-col>
        </el-row>
        <el-form-item label="父物料" v-if="!editing || form.parent_id">
          <el-select v-model="form.parent_id" clearable style="width:100%" placeholder="（顶级）">
            <el-option v-for="i in flatItems" :key="i.id" :label="i.name" :value="i.id" :disabled="i.id===editing?.id" />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="供应商"><el-input v-model="form.supplier" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="层级"><el-input-number v-model="form.level" :min="0" style="width:100%" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="showDlg=false">取消</el-button><el-button type="primary" @click="saveItem" :loading="saving">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })
const bomTree = ref([])
const showDlg = ref(false); const editing = ref(null); const saving = ref(false)
const form = reactive({ part_number:'', name:'', specification:'', material:'', quantity:1, unit:'pcs', supplier:'', level:0, parent_id:null })

const flatItems = computed(() => {
  const r = []; function walk(list) { for (const i of list) { r.push(i); if (i.children) walk(i.children) } }
  walk(bomTree.value); return r
})
const displayBom = computed(() => bomTree.value)

onMounted(load)
async function load() { try { const r = await api.get(`/projects/${props.projectId}/bom`); bomTree.value = r.data||[] } catch(e){} }

function openItem(row) {
  editing.value = row||null
  Object.assign(form, row ? {...row} : {part_number:'',name:'',specification:'',material:'',quantity:1,unit:'pcs',supplier:'',level:0,parent_id:null})
  showDlg.value = true
}
async function saveItem() {
  if (!form.name) { ElMessage.warning('请输入名称'); return }
  saving.value = true
  try {
    if (editing.value) { await api.put(`/bom/${editing.value.id}`,{...form}) }
    else { await api.post(`/projects/${props.projectId}/bom`,{...form}) }
    ElMessage.success('已保存'); showDlg.value=false; editing.value=null; await load()
  } catch(e) { ElMessage.error('保存失败') } finally { saving.value=false }
}
async function delItem(id) { await api.delete(`/bom/${id}`); ElMessage.success('已删除'); await load() }
</script>
