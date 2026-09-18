<template>
  <el-dialog :title="editing ? '编辑沟通记录' : '新增沟通记录'" v-model="visible" width="520px">
    <el-form :model="form" label-width="90px" size="small">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="沟通日期"><el-date-picker v-model="form.comm_date" type="date" value-format="YYYY-MM-DD" style="width:100%" /></el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="沟通方式">
            <el-select v-model="form.comm_type" style="width:100%">
              <el-option v-for="t in commTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="关联项目">
        <el-select v-model="form.project_id" style="width:100%" filterable clearable
                   :value-on-clear="() => null" placeholder="可选：本条沟通关联的项目">
          <el-option v-for="p in options" :key="p.id" :label="optLabel(p)" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="主题" required><el-input v-model="form.subject" placeholder="如：样机测试进度确认" /></el-form-item>
      <el-form-item label="沟通内容"><el-input v-model="form.content" type="textarea" :rows="3" /></el-form-item>
      <el-form-item label="微信图片">
        <div style="width:100%">
          <el-button size="small" type="primary" plain :loading="aiCommIng" @click="commImgInput?.click()">📷 上传微信图片（AI识别汇总）</el-button>
          <input ref="commImgInput" type="file" accept="image/*" multiple style="display:none" @change="onCommImages" />
          <div v-if="aiCommMsg" style="font-size:12px;color:#67c23a;margin-top:4px">{{ aiCommMsg }}</div>
          <div v-if="(form.images || []).length" class="comm-imgs">
            <div v-for="(img, i) in form.images" :key="img" class="comm-img">
              <a :href="'/uploads/' + img" target="_blank"><img :src="'/uploads/' + img" alt="图片" /></a>
              <span class="comm-img-del" title="移除" @click="removeCommImg(i)">✕</span>
            </div>
          </div>
        </div>
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="对方联系人"><el-input v-model="form.contact_person" /></el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="我方沟通人"><el-input v-model="form.owner" /></el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button v-if="editing" type="danger" plain size="small" style="float:left" @click="delComm">删除</el-button>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="saveComm" :loading="savingComm">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  clientId: { type: Number, default: null },          // 新增/上传图片必需
  projects: { type: Array, default: () => [] },       // [{id,name,code}] 供「关联项目」下拉
  defaultProjectId: { type: Number, default: null },  // 新增时预选项目(项目详情页传入)
  comm: { type: Object, default: null },              // null=新增, 否则=编辑
})
const emit = defineEmits(['update:modelValue', 'saved', 'deleted'])

const commTypes = ['电话', '邮件', '拜访', '微信', '会议', '其他']

const visible = computed({
  get: () => props.modelValue,
  set: v => emit('update:modelValue', v),
})

const editing = ref(null)
const savingComm = ref(false)
const aiCommIng = ref(false)
const aiCommMsg = ref('')
const form = ref({})
const commImgInput = ref(null)

const optLabel = p => (p.code ? `${p.name}（${p.code}）` : p.name)

// 编辑一条关联了「不在当前可选列表里的项目」的记录时(如客户其它项目),补一个合成项兜底,避免下拉显示空白
const options = computed(() => {
  const list = [...(props.projects || [])]
  const cur = form.value.project_id
  if (cur && !list.some(p => p.id === cur)) {
    list.push({
      id: cur,
      name: props.comm?.project_name || '当前关联项目',
      code: props.comm?.project_code || '',
    })
  }
  return list
})

function resetForm() {
  aiCommMsg.value = ''
  if (commImgInput.value) commImgInput.value.value = ''
  const c = props.comm
  if (c) {
    editing.value = c
    form.value = {
      id: c.id,
      comm_date: c.comm_date || '',
      comm_type: c.comm_type || '其他',
      subject: c.subject || '',
      content: c.content || '',
      owner: c.owner || '',
      contact_person: c.contact_person || '',
      images: [...(c.images || [])],
      project_id: c.project_id ?? null,
    }
  } else {
    editing.value = null
    form.value = {
      comm_date: new Date().toISOString().slice(0, 10),
      comm_type: '电话', subject: '', content: '', owner: '', contact_person: '', images: [],
      project_id: props.defaultProjectId ?? null,
    }
  }
}
watch(() => props.modelValue, v => { if (v) resetForm() })

async function onCommImages(e) {
  const files = [...(e.target.files || [])]
  e.target.value = ''
  if (!files.length) return
  const cid = props.clientId
  if (!cid) { ElMessage.warning('该客户尚未保存，无法上传图片'); return }
  aiCommIng.value = true
  aiCommMsg.value = ''
  try {
    const fd = new FormData()
    files.forEach(f => fd.append('files', f))
    const r = await api.post(`/clients/${cid}/communications/upload-images`, fd, { timeout: 300000 })
    const d = r.data
    const existing = new Set(form.value.images || [])
    const added = (d.images || []).filter(p => !existing.has(p))
    form.value.images = [...(form.value.images || []), ...added]
    if (d.ok && d.summary) {
      form.value.content = form.value.content
        ? form.value.content + '\n\n--- 微信图片AI汇总 ---\n' + d.summary
        : d.summary
      if (form.value.comm_type === '电话') form.value.comm_type = '微信'
      aiCommMsg.value = d.message + '，已生成汇总，可编辑后保存'
    } else {
      aiCommMsg.value = d.message || '识别完成'
    }
  } catch (err) {
    ElMessage.error('识别失败: ' + (err?.response?.data?.detail || err?.message || ''))
  }
  aiCommIng.value = false
}

function removeCommImg(i) {
  const img = form.value.images[i]
  form.value.images.splice(i, 1)
  api.delete(`/communications/remove-image?path=${encodeURIComponent(img)}`).catch(() => {})
}

async function saveComm() {
  const cid = props.clientId
  if (!cid) return
  if (!form.value.subject) { ElMessage.warning('请输入沟通主题'); return }
  savingComm.value = true
  try {
    // 归一化: el-select 清空可能给出 undefined, 而 JSON.stringify 会丢掉该键,导致后端收不到"解除关联"
    const payload = { ...form.value, project_id: form.value.project_id ?? null }
    if (editing.value) {
      await api.put(`/communications/${editing.value.id}`, payload)
    } else {
      await api.post(`/clients/${cid}/communications`, payload)
    }
    ElMessage.success('已保存')
    visible.value = false
    emit('saved', payload)
  } catch (e) {
    ElMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || ''))
  }
  savingComm.value = false
}

async function delComm() {
  try {
    await ElMessageBox.confirm('删除这条沟通记录？', '确认', { type: 'warning' })
    await api.delete(`/communications/${editing.value.id}`)
    ElMessage.success('已删除')
    visible.value = false
    emit('deleted', editing.value)
  } catch {}
}
</script>

<style scoped>
.comm-imgs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.comm-img { position: relative; width: 64px; height: 64px; border-radius: 6px; overflow: hidden; }
.comm-img img { width: 100%; height: 100%; object-fit: cover; }
.comm-img-del { position: absolute; top: 0; right: 0; width: 16px; height: 16px; font-size: 10px; line-height: 16px; text-align: center; color: #fff; background: rgba(0,0,0,.55); cursor: pointer; border-radius: 0 0 0 6px; }
</style>
