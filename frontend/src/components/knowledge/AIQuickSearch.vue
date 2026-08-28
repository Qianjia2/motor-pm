<template>
  <div style="position:fixed;bottom:24px;right:24px;z-index:1000">
    <el-button type="primary" circle size="large" @click="showDlg=true" style="width:48px;height:48px;font-size:20px;box-shadow:0 4px 12px rgba(59,130,246,.4)">
      ?
    </el-button>

    <el-dialog v-model="showDlg" title="AI 智能搜索" width="550px" top="5vh">
      <el-input v-model="query" size="large" placeholder="输入问题，搜索知识库+BOM+产品库..." @keyup.enter="search" clearable />
      <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap">
        <el-checkbox v-model="searchKb" size="small">知识库</el-checkbox>
        <el-checkbox v-model="searchBom" size="small">BOM</el-checkbox>
        <el-checkbox v-model="searchPt" size="small">产品技术库</el-checkbox>
        <el-button size="small" type="primary" @click="search" :loading="searching" style="margin-left:auto">搜索</el-button>
      </div>

      <!-- Results -->
      <div v-if="result.summary" style="margin-top:12px;padding:12px;background:#f0f9ff;border-radius:6px;font-size:13px;color:var(--text)">
        <b>AI 综合回答：</b>{{ result.summary }}
      </div>

      <div v-if="result.kb && result.kb.length" style="margin-top:12px">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px">知识库 ({{ result.kb.length }})</div>
        <div v-for="item in result.kb.slice(0,3)" :key="item.doc_id" style="padding:4px 0;font-size:12px;border-bottom:1px solid #f3f4f6">
          <a :href="'/knowledge?doc='+item.doc_id" target="_blank" style="color:var(--primary)">{{ item.title }}</a>
          <span style="color:var(--text-muted);margin-left:8px">{{ (item.snippet||'').slice(0,60) }}</span>
        </div>
      </div>

      <div v-if="result.bom && result.bom.length" style="margin-top:12px">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px">BOM物料 ({{ result.bom.length }})</div>
        <div v-for="item in result.bom.slice(0,3)" :key="item.name" style="padding:4px 0;font-size:12px">
          {{ item.name }} {{ item.spec }} <span class="tag tag-blue" style="font-size:10px">{{ item.brand }}</span>
        </div>
      </div>

      <div v-if="result.product_tech && result.product_tech.length" style="margin-top:12px">
        <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px">产品技术库 ({{ result.product_tech.length }})</div>
        <div v-for="item in result.product_tech.slice(0,3)" :key="item.name" style="padding:4px 0;font-size:12px">
          {{ item.name }} <span class="tag tag-green" style="font-size:10px">{{ item.model }}</span>
        </div>
      </div>

      <div v-if="!searching && searched && !result.summary && !result.kb?.length && !result.bom?.length && !result.product_tech?.length"
        style="margin-top:16px;text-align:center;color:var(--text-muted);font-size:13px">未找到相关结果</div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import api from '../../api/index.js'

const showDlg = ref(false)
const query = ref('')
const searching = ref(false)
const searched = ref(false)
const searchKb = ref(true)
const searchBom = ref(true)
const searchPt = ref(true)
const result = reactive({ summary: '', kb: [], bom: [], product_tech: [] })

async function search() {
  if (!query.value.trim()) return
  searching.value = true
  Object.assign(result, { summary: '', kb: [], bom: [], product_tech: [] })
  try {
    const r = await api.get('/knowledge/search-unified', { params: { q: query.value } })
    Object.assign(result, r.data || {})
    searched.value = true
  } catch(e) {
    result.summary = '搜索失败，请重试'
    searched.value = true
  }
  searching.value = false
}
</script>
