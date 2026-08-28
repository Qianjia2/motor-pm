<template>
  <el-dialog v-model="visible" :title="title" width="920px" top="4vh" @closed="onClosed">
    <div v-loading="loading" style="min-height:300px;max-height:70vh;overflow:auto;background:#f5f5f5;padding:12px;border-radius:6px">
      <div ref="container"></div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { renderAsync } from 'docx-preview'
import { init as initPptxPreview } from 'pptx-preview'
import * as XLSX from 'xlsx'

const visible = ref(false)
const title = ref('')
const loading = ref(false)
const container = ref(null)
let pptxViewer = null

const PREVIEW_EXTS = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'xls', 'xlsx']

function previewable(fileName) {
  if (!fileName) return false
  return PREVIEW_EXTS.includes(String(fileName).split('.').pop().toLowerCase())
}

/** 打开预览:支持 pdf(新窗口)/docx/pptx/xls/xlsx,其余返回 false */
async function openBlob(blob, fileName) {
  const ext = String(fileName).split('.').pop().toLowerCase()
  if (ext === 'pdf') {
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
    return true
  }
  if (ext !== 'docx' && ext !== 'doc' && ext !== 'pptx' && ext !== 'ppt' && ext !== 'xls' && ext !== 'xlsx') {
    ElMessage.info('该类型不支持在线预览，请下载查看')
    return false
  }
  title.value = '预览 - ' + fileName
  visible.value = true
  loading.value = true
  try {
    await nextTick()
    container.value.innerHTML = ''
    if (ext === 'docx' || ext === 'doc') {
      await renderAsync(blob, container.value, undefined, { ignoreLastRenderedBreak: false })
    } else if (ext === 'pptx' || ext === 'ppt') {
      const buf = await blob.arrayBuffer()
      pptxViewer = initPptxPreview(container.value, { width: 860, height: 484 })
      pptxViewer.preview(buf)
    } else {
      renderExcel(await blob.arrayBuffer())
    }
  } catch (e) {
    ElMessage.error('预览失败: ' + e.message)
  } finally {
    loading.value = false
  }
  return true
}

function renderExcel(buf) {
  const wb = XLSX.read(buf, { type: 'array' })
  let html = ''
  wb.SheetNames.forEach((name, idx) => {
    const ws = wb.Sheets[name]
    html += `<div class="xl-sheet-head">第 ${idx + 1} 个工作表 · ${name}</div>`
    if (ws && ws['!ref']) {
      html += XLSX.utils.sheet_to_html(ws, { header: '', footer: '' })
    } else {
      html += '<div class="xl-empty">（空表）</div>'
    }
  })
  container.value.innerHTML = html
}

function onClosed() {
  try { pptxViewer?.destroy?.() } catch (_) {}
  pptxViewer = null
  if (container.value) container.value.innerHTML = ''
}

defineExpose({ openBlob, previewable })
</script>

<style>
.xl-sheet-head {
  font: 13px/1.6 微软雅黑, sans-serif;
  font-weight: 600;
  color: #2f5597;
  margin: 14px 0 6px;
  padding-left: 8px;
  border-left: 3px solid #2f5597;
}
.xl-empty {
  color: #999;
  font-size: 12px;
  padding: 8px;
}
.xl-sheet-head ~ table {
  border-collapse: collapse;
  background: #fff;
  font: 12px/1.5 微软雅黑, sans-serif;
  max-width: 100%;
}
.xl-sheet-head ~ table td {
  border: 1px solid #c8c8c8;
  padding: 4px 8px;
  white-space: nowrap;
}
</style>
