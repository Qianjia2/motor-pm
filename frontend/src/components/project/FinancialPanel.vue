<template>
  <div>
    <!-- Project-level financial summary -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="6" v-for="c in cards" :key="c.label">
        <div class="fin-card" :class="c.cls">
          <div class="fin-value">
            {{ c.value }}{{ c.unit }}
            <el-icon v-if="c.editable" class="edit-icon" title="编辑合同总额" @click="openEditContract">
              <EditPen />
            </el-icon>
          </div>
          <div class="fin-label">{{ c.label }}</div>
        </div>
      </el-col>
    </el-row>

    <!-- Budget vs Actual progress -->
    <el-row :gutter="16" style="margin-bottom:20px">
      <el-col :span="12">
        <div class="card">
          <div class="card-title" style="margin-bottom:16px">回款进度</div>
          <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary)">
            合同总额 {{ data.contract_amount }}万 · 已回 {{ data.received_amount }}万
          </div>
          <el-progress :percentage="receiveRate" :stroke-width="20" :color="'#10b981'">
            <span style="font-size:12px;font-weight:600">{{ receiveRate }}%</span>
          </el-progress>
          <div style="margin-top:4px;font-size:11px;color:var(--text-muted)">
            待回款 {{ receivable }}万
          </div>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="card">
          <div class="card-title" style="margin-bottom:16px">预算执行</div>
          <div style="margin-bottom:8px;font-size:12px;color:var(--text-secondary)">
            预算 {{ data.budget }}万 · 实际 {{ data.actual_cost }}万
          </div>
          <el-progress :percentage="costRate" :stroke-width="20"
            :color="costRate > 90 ? '#ef4444' : costRate > 70 ? '#f59e0b' : '#3b82f6'">
            <span style="font-size:12px;font-weight:600">{{ costRate }}%</span>
          </el-progress>
          <div style="margin-top:4px;font-size:11px;color:var(--text-muted)">
            {{ costRate > 100 ? '超预算' : '剩余' }} {{ Math.abs(budgetRemaining) }}万
            <span v-if="costRate > 100" style="color:#ef4444">⚠</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- P&L Summary -->
    <div class="card" style="margin-bottom:20px">
      <div class="card-header">
        <div class="card-title">收支概览</div>
      </div>
      <div class="pnl-grid">
        <div class="pnl-item income">
          <span>已回款</span><strong>+{{ data.received_amount }}万</strong>
        </div>
        <div class="pnl-item expense">
          <span>实际成本</span><strong>-{{ data.actual_cost }}万</strong>
        </div>
        <div class="pnl-item" :class="profit >= 0 ? 'income' : 'expense'">
          <span>毛利</span><strong>{{ profit >= 0 ? '+' : '' }}{{ profit }}万</strong>
        </div>
        <div class="pnl-item" :class="margin >= 0 ? 'income' : 'expense'">
          <span>利润率</span><strong>{{ margin }}%</strong>
        </div>
      </div>
    </div>

    <!-- Transaction records -->
    <div class="card">
      <div class="card-header">
        <div class="card-title">收支明细</div>
        <el-button size="small" type="primary" @click="showAdd=true">
          <el-icon><Plus /></el-icon> 添加记录
        </el-button>
      </div>
      <el-table :data="transactions" stripe size="small">
        <el-table-column prop="trans_date" label="日期" width="100" />
        <el-table-column label="类型" width="70">
          <template #default="{row}">
            <span :style="{color:row.type==='income'?'#10b981':'#ef4444',fontWeight:600}">
              {{ row.type === 'income' ? '收入' : '支出' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="类别" width="100" />
        <el-table-column label="金额" width="100">
          <template #default="{row}">
            <span :style="{color:row.type==='income'?'#10b981':'#ef4444',fontWeight:600}">
              {{ row.type === 'income' ? '+' : '-' }}{{ row.amount }}万
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" />
        <el-table-column label="操作" width="60">
          <template #default="{row}">
            <el-popconfirm title="删除?" @confirm="delTrans(row.id)">
              <template #reference><el-button link size="small" type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Edit contract amount dialog -->
    <el-dialog v-model="showEditContract" title="设置合同总额" width="360px">
      <el-form label-width="100px">
        <el-form-item label="合同总额(万)" required>
          <el-input-number v-model="editContractAmount" :min="0" :precision="1" style="width:100%" />
        </el-form-item>
        <div style="font-size:12px;color:var(--text-muted);padding-left:100px">
          手工设置后不再随「合同回款」记录自动累计
        </div>
      </el-form>
      <template #footer>
        <el-button @click="showEditContract=false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveContract">保存</el-button>
      </template>
    </el-dialog>

    <!-- Add transaction dialog -->
    <el-dialog v-model="showAdd" title="添加收支记录" width="420px">
      <el-form :model="form" label-width="70px">
        <el-form-item label="类型" required>
          <el-radio-group v-model="form.type">
            <el-radio value="income">收入</el-radio>
            <el-radio value="expense">支出</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="类别" required>
          <el-select v-model="form.category" style="width:100%">
            <template v-if="form.type==='income'">
              <el-option label="合同回款" value="合同回款" />
              <el-option label="技术服务" value="技术服务" />
              <el-option label="其他收入" value="其他收入" />
            </template>
            <template v-else>
              <el-option label="材料采购" value="材料采购" />
              <el-option label="外协加工" value="外协加工" />
              <el-option label="测试费" value="测试费" />
              <el-option label="差旅费" value="差旅费" />
              <el-option label="其他支出" value="其他支出" />
            </template>
          </el-select>
        </el-form-item>
        <el-form-item label="金额(万)" required>
          <el-input-number v-model="form.amount" :min="0.1" :precision="1" style="width:100%" />
        </el-form-item>
        <el-form-item label="日期" required>
          <el-date-picker v-model="form.trans_date" type="date" style="width:100%" value-format="YYYY-MM-DD" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd=false">取消</el-button>
        <el-button type="primary" @click="saveTrans" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, EditPen } from '@element-plus/icons-vue'
import api, { updateProject } from '../../api/index.js'

const props = defineProps({ projectId: { type: Number, required: true } })

const data = reactive({ contract_amount: 0, received_amount: 0, budget: 0, actual_cost: 0 })
const transactions = ref([])
const showAdd = ref(false)
const saving = ref(false)
const showEditContract = ref(false)
const editContractAmount = ref(0)
const form = reactive({ type: 'income', category: '合同回款', amount: 0, trans_date: '', description: '' })

const receiveRate = computed(() => data.contract_amount > 0 ? Math.round(data.received_amount / data.contract_amount * 100) : 0)
const costRate = computed(() => data.budget > 0 ? Math.round(data.actual_cost / data.budget * 100) : 0)
const receivable = computed(() => Math.round((data.contract_amount - data.received_amount) * 10) / 10)
const budgetRemaining = computed(() => Math.round((data.budget - data.actual_cost) * 10) / 10)
const profit = computed(() => Math.round((data.received_amount - data.actual_cost) * 10) / 10)
const margin = computed(() => data.received_amount > 0 ? Math.round(profit.value / data.received_amount * 100) : 0)

const cards = computed(() => [
  { label: '合同总额', value: data.contract_amount, unit: '万', cls: 'fin-blue', editable: true },
  { label: '已回款', value: data.received_amount, unit: '万', cls: 'fin-green' },
  { label: '项目预算', value: data.budget, unit: '万', cls: 'fin-purple' },
  { label: '实际成本', value: data.actual_cost, unit: '万', cls: data.actual_cost > data.budget ? 'fin-red' : 'fin-orange' },
])

function openEditContract() {
  editContractAmount.value = data.contract_amount || 0
  showEditContract.value = true
}
async function saveContract() {
  if (editContractAmount.value == null || editContractAmount.value < 0) { ElMessage.warning('请输入有效的合同总额'); return }
  saving.value = true
  try {
    await updateProject(props.projectId, { contract_amount: editContractAmount.value })
    ElMessage.success('合同总额已更新')
    showEditContract.value = false
    await load()
  } catch (e) { ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message)) } finally { saving.value = false }
}

onMounted(load)

async function load() {
  try {
    const res = await api.get(`/financials/projects`)
    const proj = (res.data || []).find(p => p.id === props.projectId)
    if (proj) Object.assign(data, proj)
  } catch (e) { /* may not have financial data yet */ }
  try {
    const res = await api.get(`/projects/${props.projectId}/transactions`)
    transactions.value = res.data || []
  } catch (e) { /* ok */ }
}

async function saveTrans() {
  if (!form.amount || !form.trans_date) { ElMessage.warning('请填写金额和日期'); return }
  saving.value = true
  try {
    await api.post(`/projects/${props.projectId}/transactions`, {
      type: form.type, category: form.category, amount: form.amount,
      trans_date: typeof form.trans_date === 'string' ? form.trans_date : form.trans_date.toISOString().slice(0, 10),
      description: form.description,
    })
    ElMessage.success('已添加')
    showAdd.value = false
    await load()
  } catch (e) { ElMessage.error('操作失败') } finally { saving.value = false }
}

async function delTrans(id) {
  try {
    await api.delete(`/transactions/${id}`)
    ElMessage.success('已删除')
    await load()
  } catch (e) { ElMessage.error('删除失败') }
}
</script>

<style scoped>
.fin-card {
  padding: 16px; border-radius: var(--radius); text-align: center;
  border: 1px solid var(--border); background: var(--bg-white);
  box-shadow: var(--shadow-sm); transition: box-shadow .2s;
}
.fin-card:hover { box-shadow: var(--shadow-md); }
.edit-icon { font-size: 14px; margin-left: 6px; cursor: pointer; color: var(--text-muted); vertical-align: 2px; }
.edit-icon:hover { color: var(--primary); }
.fin-value { font-size: 24px; font-weight: 700; color: var(--text); }
.fin-label { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.fin-blue .fin-value { color: #3b82f6; }
.fin-green .fin-value { color: #10b981; }
.fin-purple .fin-value { color: #8b5cf6; }
.fin-orange .fin-value { color: #f59e0b; }
.fin-red .fin-value { color: #ef4444; }

.pnl-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.pnl-item {
  text-align: center; padding: 12px; border-radius: 6px; background: #f9fafb;
}
.pnl-item span { display: block; font-size: 12px; color: var(--text-secondary); }
.pnl-item strong { font-size: 18px; margin-top: 4px; display: block; }
.pnl-item.income strong { color: #10b981; }
.pnl-item.expense strong { color: #ef4444; }
</style>
