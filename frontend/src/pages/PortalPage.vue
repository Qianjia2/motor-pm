<template>
  <div class="portal-wrap">
    <!-- Login -->
    <div v-if="!authorized" class="portal-login-card">
      <h2>客户项目访问</h2>
      <p style="color:var(--text-muted);margin-bottom:20px">请输入访问密码（如有设置）</p>
      <el-input v-model="pwd" placeholder="密码（留空直接进入）" size="large" @keyup.enter="doLogin" />
      <el-button type="primary" size="large" style="width:100%;margin-top:16px" @click="doLogin" :loading="loggingIn">进入</el-button>
      <div v-if="error" style="color:#ef4444;margin-top:8px;font-size:12px">{{ error }}</div>
    </div>

    <!-- Portal View -->
    <div v-else>
      <div class="portal-topbar">
        <h2>{{ project?.name }}</h2>
        <span class="tag" :class="'tag-'+statusCls">{{ statusLabel }}</span>
        <span style="margin-left:8px;font-size:13px;color:var(--text-secondary)">{{ project?.phase }}</span>
      </div>

      <el-row :gutter="16" style="margin-bottom:16px">
        <el-col :span="6" v-for="c in kpiCards" :key="c.label">
          <div class="p-stat"><div class="p-sval">{{ c.value }}</div><div class="p-slab">{{ c.label }}</div></div>
        </el-col>
      </el-row>

      <el-row :gutter="16">
        <el-col :span="12">
          <div class="card" style="margin-bottom:16px">
            <div class="card-title" style="margin-bottom:12px">里程碑</div>
            <div v-if="milestones.length===0" style="color:var(--text-muted);font-size:13px">暂无</div>
            <div v-for="m in milestones" :key="m.id" class="p-row">
              <span class="dot" :class="'dot-'+m.status" style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px"></span>
              <span>{{ m.name }}</span>
              <span style="margin-left:auto;font-size:12px;color:var(--text-muted)">{{ m.planned_date }}</span>
            </div>
          </div>
        </el-col>
        <el-col :span="12">
          <div class="card" style="margin-bottom:16px">
            <div class="card-title" style="margin-bottom:12px">交付物</div>
            <div v-if="deliverables.length===0" style="color:var(--text-muted);font-size:13px">暂无</div>
            <div v-for="d in deliverables" :key="d.id" class="p-row">
              <span class="tag tag-blue" style="font-size:10px">{{ d.phase }}</span>
              <span>{{ d.name }}</span>
              <span class="tag" :class="'tag-'+delStatusCls(d.status)" style="font-size:10px;margin-left:auto">{{ d.status }}</span>
            </div>
          </div>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api/index.js'

const route = useRoute()
const code = route.params.code
const authorized = ref(false)
const loggingIn = ref(false)
const pwd = ref('')
const error = ref('')
const project = ref(null)
const milestones = ref([])
const deliverables = ref([])

function statusLabel(s) { const m={normal:'正常',at_risk:'有风险',blocked:'阻塞'}; return m[s]||s }
function statusCls(s) { return s==='blocked'?'red':s==='at_risk'?'orange':'green' }
function delStatusCls(s) { return s==='approved'?'green':s==='submitted'?'blue':'gray' }

const kpiCards = computed(() => [
  { label:'项目阶段', value:project.value?.phase||'-' },
  { label:'完成率', value:(project.value?.completion_pct||0)+'%' },
  { label:'里程碑', value:milestones.value.length+'个' },
  { label:'交付物', value:deliverables.value.length+'个' },
])

async function doLogin() {
  loggingIn.value = true; error.value = ''
  try {
    const r = await api.post(`/portal/${code}/login`, { password: pwd.value })
    authorized.value = true
    await loadData()
  } catch(e) { error.value = e.response?.data?.detail || '访问失败' } finally { loggingIn.value = false }
}

async function loadData() {
  try { const r = await api.get(`/portal/${code}/project`); project.value = r.data } catch(e) {}
  try { const r = await api.get(`/portal/${code}/milestones`); milestones.value = r.data||[] } catch(e) {}
  try { const r = await api.get(`/portal/${code}/deliverables`); deliverables.value = r.data||[] } catch(e) {}
}
</script>

<style scoped>
.portal-wrap { max-width:900px; margin:0 auto; padding:40px 20px; }
.portal-login-card { max-width:400px; margin:120px auto; text-align:center; background:var(--bg-white); padding:40px; border-radius:12px; box-shadow:var(--shadow-md); }
.portal-topbar { display:flex; align-items:center; gap:12px; margin-bottom:20px; background:var(--bg-white); padding:16px 20px; border-radius:8px; box-shadow:var(--shadow-sm); }
.p-stat { background:var(--bg-white); padding:16px; border-radius:8px; box-shadow:var(--shadow-sm); text-align:center; }
.p-sval { font-size:22px; font-weight:700; color:var(--text); }
.p-slab { font-size:12px; color:var(--text-muted); margin-top:4px; }
.p-row { display:flex; align-items:center; gap:8px; padding:8px 0; border-bottom:1px solid #f3f4f6; font-size:13px; }
.dot-completed { background:#10b981; } .dot-in_progress { background:#3b82f6; } .dot-pending { background:#d1d5db; }
</style>
