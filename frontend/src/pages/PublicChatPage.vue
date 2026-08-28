<template>
  <div class="pub-page">
    <!-- Header -->
    <div class="pub-header">
      <div class="pub-title">{{ kbInfo.name || '智能知识库' }}</div>
      <div class="pub-subtitle">{{ kbInfo.welcome || '扫码查看资料，AI 智能问答' }}</div>
      <div v-if="qrUrl" class="pub-qr">
        <img :src="qrUrl" width="80" height="80" alt="二维码" />
        <div>手机扫码访问</div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="pub-tabs">
      <button :class="{active:tab==='docs'}" @click="tab='docs'">📄 文档 ({{ documents.length }})</button>
      <button :class="{active:tab==='chat'}" @click="tab='chat'">💬 AI 问答</button>
    </div>

    <!-- Documents Tab -->
    <div v-show="tab==='docs'" class="pub-docs">
      <div v-if="!documents.length" class="pub-empty">暂无共享文档</div>
      <div v-for="d in documents" :key="d.id" class="pub-doc-card">
        <div class="pub-doc-head">
          <span>{{ fileIcon(d.doc_type) }}</span>
          <span class="pub-doc-name">{{ d.title }}</span>
        </div>
        <div class="pub-doc-meta">{{ typeLabel(d.doc_type) }}<span v-if="d.file_size"> · {{ fmtSize(d.file_size) }}</span></div>
        <div class="pub-doc-preview">{{ d.preview || '(无文字内容)' }}</div>
      </div>
    </div>

    <!-- Chat Tab -->
    <div v-show="tab==='chat'" class="pub-chat-wrap">
      <div ref="chatBox" class="pub-chat-box">
        <div v-if="!messages.length" class="pub-empty">
          <div style="font-size:40px;margin-bottom:12px">🤖</div>
          <div style="font-weight:600;margin-bottom:4px">有什么可以帮助您的？</div>
          <div style="font-size:12px;color:#8f959e">基于 {{ documents.length }} 篇文档内容回答</div>
        </div>
        <div v-for="(m,i) in messages" :key="i" class="pub-msg-row">
          <div v-if="m.role==='user'" class="pub-msg-user">{{ m.content }}</div>
          <div v-else class="pub-msg-ai">
            <div class="pub-msg-content">{{ m.content }}</div>
            <div v-if="m.sources?.length" class="pub-msg-src">参考: {{ m.sources.join(' · ') }}</div>
          </div>
        </div>
        <div v-if="typing" class="pub-msg-ai">
          <div class="pub-msg-content"><span class="dot">●</span><span class="dot">●</span><span class="dot">●</span></div>
        </div>
      </div>
      <div class="pub-input-row">
        <input v-model="input" placeholder="输入问题..." @keyup.enter="send" :disabled="typing" class="pub-input" />
        <button @click="send" :disabled="!input.trim()||typing" class="pub-send">发送</button>
      </div>
    </div>

    <div class="pub-footer">由 AI 知识库提供支持 · 回答仅供参考</div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const token = route.params.token
const kbInfo = ref({ name: '智能知识库', welcome: '' })
const qrUrl = ref('')
const documents = ref([])
const messages = ref([])
const input = ref('')
const typing = ref(false)
const chatBox = ref(null)
const tab = ref('docs')

function fileIcon(t) { const m={'技术类':'📘','项目类':'📁','运营类':'📋','销售类':'📊','模板类':'📝'}; return m[t]||'📄' }
function typeLabel(t) { return t||'其他' }
function fmtSize(b) { return b<1024?b+'B':b<1024*1024?(b/1024).toFixed(1)+'KB':(b/1024/1024).toFixed(1)+'MB' }

async function loadData() {
  try {
    const r = await axios.get(`/api/public/kb/${token}`)
    kbInfo.value = r.data
    documents.value = r.data.documents || []
    document.title = kbInfo.value.name || '智能知识库'
  } catch {
    kbInfo.value = { name: '链接已失效', welcome: '分享链接不存在或已停用' }
  }
}

onMounted(() => {
  qrUrl.value = `https://api.qrserver.com/v1/create-qr-code/?size=100x100&data=${encodeURIComponent(window.location.href)}`
  loadData()
})

async function send() {
  const q = input.value.trim()
  if (!q || typing.value) return
  input.value = ''
  messages.value.push({ role: 'user', content: q })
  typing.value = true
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  try {
    const body = { question: q, history: messages.value.slice(-10).map(m => ({ q: m.role==='user'?m.content:'', a: m.role==='assistant'?m.content:'' })) }
    const r = await axios.post(`/api/public/kb/${token}/chat`, body, { timeout: 120000 })
    messages.value.push({ role: 'assistant', content: r.data.answer, sources: r.data.sources })
  } catch {
    messages.value.push({ role: 'assistant', content: '抱歉，服务暂时不可用，请稍后重试。' })
  }
  typing.value = false
  await nextTick()
  if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
}
</script>

<style scoped>
.pub-page { max-width:600px;margin:0 auto;padding:12px;min-height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif }
.pub-header { text-align:center;padding:20px 8px 12px;border-bottom:1px solid #f0f0f0;margin-bottom:8px }
.pub-title { font-size:20px;font-weight:700;color:#1f2329 }
.pub-subtitle { font-size:13px;color:#8f959e;margin-top:4px }
.pub-qr { margin-top:12px;display:inline-block;text-align:center }
.pub-qr img { border-radius:8px;border:1px solid #e5e6e8;display:block;margin:0 auto }
.pub-qr div { font-size:10px;color:#8f959e;margin-top:4px }
.pub-tabs { display:flex;border-bottom:2px solid #e5e6e8;margin-bottom:12px }
.pub-tabs button { flex:1;padding:10px 0;border:none;background:none;font-size:14px;color:#646a73;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-2px;transition:all .15s }
.pub-tabs button.active { color:#3370ff;border-bottom-color:#3370ff;font-weight:600 }
.pub-tabs button:hover { color:#3370ff }
.pub-docs { min-height:300px }
.pub-empty { text-align:center;padding:60px 20px;color:#8f959e;font-size:14px }
.pub-doc-card { padding:10px 12px;margin-bottom:8px;border:1px solid #e5e6e8;border-radius:8px;background:#fff }
.pub-doc-head { display:flex;align-items:center;gap:8px;margin-bottom:4px }
.pub-doc-name { font-weight:600;font-size:14px;color:#1f2329;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap }
.pub-doc-meta { font-size:11px;color:#8f959e;margin-bottom:6px;padding-left:26px }
.pub-doc-preview { font-size:12px;color:#646a73;line-height:1.7;padding:8px 10px;background:#fafafa;border-radius:6px;max-height:100px;overflow-y:auto;white-space:pre-wrap }
.pub-chat-wrap { display:flex;flex-direction:column;flex:1 }
.pub-chat-box { flex:1;overflow-y:auto;padding:8px;border:1px solid #e5e6e8;border-radius:8px;background:#f9fafb;min-height:350px;max-height:calc(100vh - 360px) }
.pub-msg-row { margin-bottom:12px }
.pub-msg-user { max-width:85%;margin-left:auto;padding:10px 14px;background:#3370ff;color:#fff;border-radius:12px 12px 0 12px;font-size:14px;line-height:1.6;white-space:pre-wrap;word-break:break-word }
.pub-msg-ai { display:flex;gap:8px }
.pub-msg-content { max-width:85%;padding:10px 14px;background:#fff;border-radius:0 12px 12px 12px;font-size:14px;line-height:1.7;white-space:pre-wrap;word-break:break-word;box-shadow:0 1px 3px rgba(0,0,0,0.06) }
.pub-msg-src { margin-top:3px;font-size:10px;color:#8f959e;padding-left:4px }
.pub-input-row { margin-top:10px;display:flex;gap:8px }
.pub-input { flex:1;border:1px solid #d0d5dd;border-radius:8px;padding:10px 14px;font-size:15px;outline:none }
.pub-input:focus { border-color:#3370ff }
.pub-send { background:#3370ff;color:#fff;border:none;border-radius:8px;padding:10px 18px;font-size:14px;cursor:pointer;white-space:nowrap }
.pub-send:disabled { background:#a0b4e0;cursor:not-allowed }
.pub-footer { text-align:center;margin-top:12px;font-size:11px;color:#c0c4cc }
.dot { animation:blink 1.4s infinite both;color:#ccc }
.dot:nth-child(2){animation-delay:.2s}.dot:nth-child(3){animation-delay:.4s}
@keyframes blink{0%{opacity:.2}20%{opacity:1}100%{opacity:.2}}
</style>
