<template>
  <div class="pd-page">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:20px">
      <el-button size="small" @click="$router.back()">← 返回</el-button>
      <h2 style="margin:0;font-size:18px">{{ product.product_model || product.name || '产品详情' }}</h2>
      <span v-if="product.product_code" style="font-size:13px;color:var(--text-secondary)">{{ product.product_code }}</span>
      <el-button type="primary" size="small" style="margin-left:auto" @click="openEdit">✏️ 编辑</el-button>
    </div>

    <div v-if="loading" style="text-align:center;padding:60px"><el-icon class="is-loading" :size="24"><Loading /></el-icon></div>

    <template v-if="!loading && product.id">
      <!-- Common / Basic Info -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-header"><div class="card-title">基本信息</div></div>
        <div class="detail-grid">
          <div class="detail-item" v-for="item in detailCommonFields" :key="item.key">
            <div class="detail-label">{{ item.label }}</div>
            <div class="detail-value">
              <span v-if="item.key==='status'" :class="'tag tag-'+statusColor(product.status)" style="font-size:12px">{{ product.status || '-' }}</span>
              <span v-else-if="item.key==='motor_type'" :class="'tag tag-'+motorTypeColor(product.motor_type)" style="font-size:12px">{{ product.motor_type || '-' }}</span>
              <span v-else>{{ product[item.key] || '-' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Product-Line Specific Fields -->
      <div class="card" style="margin-bottom:16px">
        <div class="card-header"><div class="card-title">{{ product.product_line || '产品' }}参数</div></div>
        <div class="detail-grid">
          <div class="detail-item" v-for="item in detailPlFields" :key="item.key">
            <div class="detail-label">{{ item.label }}</div>
            <div class="detail-value">{{ product[item.key] || '-' }}</div>
          </div>
        </div>
      </div>

      <!-- Files -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">📎 图纸 / 文件 ({{ files.length }})</div>
          <el-button size="small" @click="$refs.detailFileInput.click()">+ 上传文件</el-button>
          <input type="file" ref="detailFileInput" multiple @change="onDetailFileChange" style="display:none" />
        </div>
        <div v-if="files.length===0" style="color:var(--text-muted);font-size:13px;padding:12px">暂无附件</div>
        <div v-for="f in files" :key="f.id" style="display:flex;align-items:center;justify-content:space-between;padding:10px 14px;border-bottom:1px solid var(--border)">
          <span style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{{ f.filename }}</span>
          <span style="color:var(--text-muted);margin:0 12px;font-size:12px">{{ (f.size/1024).toFixed(1) }} KB</span>
          <el-button link size="small" type="primary" @click="downloadFile(f.id, f.filename)">下载</el-button>
          <el-popconfirm title="确认删除?" @confirm="deleteFile(f.id)"><template #reference><el-button link size="small" type="danger">删除</el-button></template></el-popconfirm>
        </div>
      </div>
    </template>

    <!-- Edit Dialog -->
    <el-dialog v-model="showEdit" title="编辑产品" width="650px" top="20px">
      <el-form :model="form" label-width="110px" size="small">
        <el-form-item label="产品编码"><el-input v-model="form.product_code" /></el-form-item>
        <el-form-item label="产品型号" required><el-input v-model="form.product_model" /></el-form-item>
        <el-form-item label="电机种类">
          <el-select v-model="form.motor_type" style="width:100%" clearable>
            <el-option v-for="t in motorTypes" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="产品线">
          <el-select v-model="form.product_line" style="width:100%" clearable>
            <el-option v-for="t in productLines" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%" clearable>
            <el-option v-for="t in statuses" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-divider content-position="left"><span style="font-size:12px;color:var(--text-muted)">电气性能</span></el-divider>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="额定功率(kW)" label-width="90px"><el-input v-model="form.rated_power" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="额定电压(V)" label-width="90px"><el-input v-model="form.rated_voltage" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="额定转速(rpm)" label-width="95px"><el-input v-model="form.rated_speed" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="电磁方案编号" label-width="90px"><el-input v-model="form.em_design_no" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="反电势系数" label-width="90px"><el-input v-model="form.back_emf_coef" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="峰值转矩(Nm)" label-width="90px"><el-input v-model="form.peak_torque" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="峰值转矩电流(A)" label-width="105px"><el-input v-model="form.peak_torque_current" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="峰值转矩转速" label-width="90px"><el-input v-model="form.peak_torque_speed" /></el-form-item></el-col>
        </el-row>
        <el-divider content-position="left"><span style="font-size:12px;color:var(--text-muted)">结构参数</span></el-divider>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="叠高(mm)" label-width="90px"><el-input v-model="form.stack_height" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="绕组" label-width="90px"><el-input v-model="form.winding" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="传感器类型" label-width="90px"><el-input v-model="form.sensor_type" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="花键规格" label-width="90px"><el-input v-model="form.spline_spec" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="止口直径(mm)" label-width="95px"><el-input v-model="form.mounting_spigot_dia" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="安装方式" label-width="90px"><el-input v-model="form.mounting_method" /></el-form-item></el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="8"><el-form-item label="后端盖固定" label-width="90px"><el-input v-model="form.rear_cover_fixing" /></el-form-item></el-col>
          <el-col :span="8"><el-form-item label="制动器" label-width="90px"><el-input v-model="form.brake" /></el-form-item></el-col>
        </el-row>
        <el-divider content-position="left"><span style="font-size:12px;color:var(--text-muted)">其他</span></el-divider>
        <el-form-item label="参考标准"><el-input v-model="form.standard" /></el-form-item>
        <el-form-item label="供应商"><el-input v-model="form.supplier" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit=false">取消</el-button>
        <el-button type="primary" @click="saveEdit" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import api from '../api/index.js'

const route = useRoute()
const product = ref({})
const files = ref([])
const loading = ref(true)

// Edit state
const showEdit = ref(false)
const saving = ref(false)
const form = ref({})
const motorTypes = ['永磁同步电机(PMSM)','异步电机(IM)','直流无刷电机(BLDC)','直流有刷电机','开关磁阻电机(SRM)','同步磁阻电机(SynRM)','步进电机','直线电机','其他']
const productLines = ['主驱电机','辅驱电机','空压机','转向泵','工业永磁','EMB','关节模组','其他']
const statuses = ['在售','研发中','预研']

const specialties = ref([])
const detailCommonFields = computed(() => {
  const spec = specialties.value.find(s => s.value === product.value.specialty)
  if (!spec) return []
  return spec.fields || []
})
const detailPlFields = computed(() => {
  const spec = specialties.value.find(s => s.value === product.value.specialty)
  const pl = product.value.product_line
  if (spec?.product_line_fields && pl && spec.product_line_fields[pl]) {
    return spec.product_line_fields[pl]
  }
  return []
})

function motorTypeColor(t) {
  if (!t) return 'gray'
  if (t.includes('永磁')) return 'blue'
  if (t.includes('异步')) return 'orange'
  if (t.includes('无刷')||t.includes('BLDC')) return 'green'
  if (t.includes('磁阻')||t.includes('SRM')) return 'purple'
  return 'gray'
}
function statusColor(s) {
  if (s === '在售') return 'green'
  if (s === '研发中') return 'orange'
  if (s === '预研') return 'purple'
  return 'gray'
}

async function loadProduct() {
  loading.value = true
  try {
    const [r, sr] = await Promise.all([
      api.get(`/product-tech/${route.params.id}`),
      api.get('/product-tech/specialties')
    ])
    product.value = r.data || {}
    files.value = product.value.files || []
    specialties.value = sr.data || []
  } catch { product.value = {} }
  loading.value = false
}

async function onDetailFileChange(e) {
  const fls = Array.from(e.target?.files || [])
  if (!fls.length) return
  const fd = new FormData()
  for (const f of fls) fd.append('files', f)
  try {
    await api.post(`/product-tech/${product.value.id}/files`, fd)
    ElMessage.success('已上传')
    await loadProduct()
  } catch { ElMessage.error('上传失败') }
  e.target.value = ''
}

function downloadFile(fileId, filename) {
  api.get(`/product-tech/${product.value.id}/files/${fileId}/download`, { responseType: 'blob' }).then(res => {
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a'); a.href = url; a.download = filename; a.click()
    URL.revokeObjectURL(url)
  }).catch(() => ElMessage.error('下载失败'))
}

async function deleteFile(fileId) {
  try {
    await api.delete(`/product-tech/${product.value.id}/files/${fileId}`)
    ElMessage.success('已删除')
    await loadProduct()
  } catch { ElMessage.error('删除失败') }
}

function openEdit() {
  form.value = { ...product.value }
  showEdit.value = true
}

async function saveEdit() {
  if (!form.value.product_model) { ElMessage.warning('请输入产品型号'); return }
  saving.value = true
  try {
    await api.put(`/product-tech/${product.value.id}`, form.value)
    ElMessage.success('已保存')
    showEdit.value = false
    await loadProduct()
  } catch (e) { ElMessage.error(e?.response?.data?.detail || '保存失败') }
  saving.value = false
}

onMounted(loadProduct)
</script>

<style scoped>
.pd-page { max-width: 1000px; margin: 0 auto; }
.detail-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0; }
.detail-item { padding: 10px 16px; border-bottom: 1px solid var(--border); }
.detail-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.detail-value { font-size: 14px; font-weight: 500; }
</style>
