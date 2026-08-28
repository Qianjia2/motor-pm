<template>
  <div>
    <div class="card-header mb-md"><span></span><el-button size="small" type="primary" @click="openEcn()"><el-icon><Plus /></el-icon> 新建ECN</el-button></div>
    <div v-if="ecns.length===0" style="text-align:center;padding:40px;color:var(--text-muted)">暂无工程变更</div>
    <el-table :data="ecns" stripe size="small">
      <el-table-column prop="ecn_number" label="ECN编号" width="130" />
      <el-table-column prop="title" label="变更标题" min-width="200" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{row}"><span :class="'tag tag-'+ecnCls(row.status)" style="font-size:10px">{{ ecnLabel(row.status) }}</span></template>
      </el-table-column>
      <el-table-column prop="submitted_by" label="提交人" width="80" />
      <el-table-column prop="submitted_date" label="提交日期" width="100" />
      <el-table-column label="操作" width="140">
        <template #default="{row}">
          <el-button link size="small" type="primary" @click="openEcn(row)">编辑</el-button>
          <el-popconfirm title="删除?" @confirm="delEcn(row.id)"><template #reference><el-button link size="small" type="danger">删</el-button></template></el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDlg" :title="editing ? '编辑ECN' : '新建工程变更'" width="550px">
      <el-form :model="form" label-width="80px" size="small">
        <el-form-item label="变更标题" required><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="变更原因"><el-input v-model="form.reason" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="变更描述"><el-input v-model="form.change_description" type="textarea" :rows="2" /></el-form-item>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="状态"><el-select v-model="form.status" style="width:100%"><el-option label="草稿" value="draft" /><el-option label="已提交" value="submitted" /><el-option label="已审核" value="reviewed" /><el-option label="已批准" value="approved" /><el-option label="已拒绝" value="rejected" /><el-option label="已实施" value="implemented" /></el-select></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="提交人"><el-input v-model="form.submitted_by" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="批准人"><el-input v-model="form.approved_by" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12"><el-form-item label="提交日期"><el-date-picker v-model="form.submitted_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="批准日期"><el-date-picker v-model="form.approved_date" type="date" style="width:100%" value-format="YYYY-MM-DD" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="showDlg=false">取消</el-button><el-button type="primary" @click="saveEcn" :loading="saving">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import api from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })
const ecns = ref([])
const showDlg = ref(false); const editing = ref(null); const saving = ref(false)
const form = reactive({ title:'', reason:'', change_description:'', status:'draft', submitted_by:'', approved_by:'', submitted_date:null, approved_date:null })

function ecnLabel(s) { const m={draft:'草稿',submitted:'已提交',reviewed:'已审核',approved:'已批准',rejected:'已拒绝',implemented:'已实施'}; return m[s]||s }
function ecnCls(s) { return s==='approved'||s==='implemented'?'green':s==='rejected'?'red':s==='submitted'?'blue':'gray' }

onMounted(load)
async function load() { try { const r = await api.get(`/projects/${props.projectId}/ecns`); ecns.value=r.data||[] } catch(e){} }

function openEcn(row) {
  editing.value = row||null
  Object.assign(form, row ? {...row} : {title:'',reason:'',change_description:'',status:'draft',submitted_by:'',approved_by:'',submitted_date:null,approved_date:null})
  showDlg.value = true
}
async function saveEcn() {
  if (!form.title) { ElMessage.warning('请输入标题'); return }
  saving.value = true
  try {
    if (editing.value) { await api.put(`/ecns/${editing.value.id}`,{...form}) }
    else { await api.post(`/projects/${props.projectId}/ecns`,{...form}) }
    ElMessage.success('已保存'); showDlg.value=false; editing.value=null; await load()
  } catch(e) { ElMessage.error('保存失败') } finally { saving.value=false }
}
async function delEcn(id) { await api.delete(`/ecns/${id}`); ElMessage.success('已删除'); await load() }
</script>
