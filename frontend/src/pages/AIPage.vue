<template>
  <div class="ai-page">
    <!-- Conversation sidebar -->
    <div class="conv-sidebar">
      <el-button type="primary" size="small" @click="newConv" style="width:100%;margin-bottom:8px">
        <el-icon><Plus /></el-icon> 新建对话
      </el-button>
      <div class="conv-list">
        <div v-for="c in conversations" :key="c.id" class="conv-item"
          :class="{active: c.id===activeConvId}" @click="switchConv(c.id)">
          <span class="conv-title" :title="c.title">{{ c.title }}</span>
          <span class="conv-actions" @click.stop>
            <el-button link size="small" @click="renameConv(c)"><el-icon><Edit /></el-icon></el-button>
            <el-button link size="small" @click="delConv(c.id)" v-if="conversations.length>1"><el-icon><Close /></el-icon></el-button>
          </span>
        </div>
      </div>
      <div class="conv-footer">
        <span class="dot" :class="online?'green':'gray'"></span>
        {{ online ? 'qwen2.5:3b 在线' : 'AI 离线' }}
      </div>
    </div>

    <!-- Main area -->
    <div class="chat-main">
      <div class="header-tabs">
        <el-radio-group v-model="mode" size="small">
          <el-radio-button value="chat">问答</el-radio-button>
          <el-radio-button value="image">图片识别</el-radio-button>
        </el-radio-group>
        <el-select v-if="mode==='chat'" v-model="chatMode" size="small" style="width:120px;margin-left:8px">
          <el-option label="自动识别" value="auto" />
          <el-option label="项目数据" value="project" />
          <el-option label="通用对话" value="general" />
        </el-select>
        <span style="margin-left:auto;font-size:12px;color:var(--text-muted)">
          {{ activeConv ? activeConv.title : '' }}
        </span>
      </div>

      <!-- Chat -->
      <div v-if="mode==='chat'" class="chat-area">
        <div class="chat-messages" ref="chatRef">
          <template v-for="(msg,i) in (activeConv ? activeConv.messages : [])" :key="i">
            <div class="chat-msg" :class="'msg-'+msg.role">
              <div class="msg-content" v-html="renderMd(msg.content)"></div>
            </div>
          </template>
          <div v-if="chatLoading" class="chat-msg msg-assistant"><div class="msg-content"><em>AI 思考中...</em></div></div>
          <div v-if="!chatLoading && (!activeConv || activeConv.messages.length===0)" class="chat-empty">
            <p>{{ online ? 'AI 已就绪，输入问题开始对话' : 'AI 服务未启动' }}</p>
            <div class="quick-qs">
              <span v-for="q in quickQuestions" :key="q" class="q-tag" @click="chatInput=q;sendChat()">{{ q }}</span>
            </div>
          </div>
        </div>
        <div class="chat-input-bar">
          <el-input v-model="chatInput" placeholder="输入问题..." @keyup.enter="sendChat"
            :disabled="!online||chatLoading" />
          <el-button type="primary" @click="sendChat" :loading="chatLoading" :disabled="!online">发送</el-button>
        </div>
      </div>

      <!-- Image to text -->
      <div v-if="mode==='image'" class="image-area">
        <div class="upload-zone">
          <input type="file" ref="imgInput" accept="image/*" multiple @change="onImagesSelected" style="display:none" />
          <el-button type="primary" size="large" @click="$refs.imgInput.click()" :loading="imgLoading">
            📷 选择图片（可多选 Ctrl+点击）
          </el-button>
          <p style="margin-top:8px;font-size:13px;color:var(--text-muted)">
            {{ imgFiles.length > 0 ? `已选 ${imgFiles.length} 张` : '支持 PNG/JPG/GIF/BMP/WebP' }}
          </p>
        </div>
        <div v-if="imgResult" class="img-result">
          <div class="result-header">
            <span>AI 识别结果</span>
            <el-button size="small" @click="copyResult">📋 复制</el-button>
          </div>
          <div class="result-content" v-html="renderMd(imgResult)"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Edit, Close } from '@element-plus/icons-vue'

const mode = ref('chat')
const chatMode = ref('auto')
const online = ref(false)
const chatInput = ref('')
const chatLoading = ref(false)
const chatRef = ref(null)
const imgFiles = ref([])
const imgLoading = ref(false)
const imgResult = ref('')
const conversations = ref([])
const activeConvId = ref(null)

const quickQuestions = ['哪些项目有风险？', '本周周报进展摘要', '帮我总结所有项目的里程碑状态', '最近有什么变更？']
const activeConv = computed(() => conversations.value.find(c => c.id === activeConvId.value))

const STORAGE_KEY = 'motorpm_ai_conversations'

function loadConvs() {
  try { const raw = localStorage.getItem(STORAGE_KEY); if (raw) conversations.value = JSON.parse(raw) } catch {}
  if (!conversations.value.length) {
    conversations.value = [{ id: Date.now(), title: '新对话', messages: [], createdAt: Date.now() }]
  }
  activeConvId.value = conversations.value[0].id
}
function saveConvs() {
  const slim = conversations.value.map(c => ({ ...c, messages: c.messages.slice(-50) }))
  localStorage.setItem(STORAGE_KEY, JSON.stringify(slim))
}
watch(conversations, saveConvs, { deep: true })

function newConv() {
  const c = { id: Date.now(), title: '新对话', messages: [], createdAt: Date.now() }
  conversations.value.unshift(c); activeConvId.value = c.id; chatInput.value = ''
}
function switchConv(id) { activeConvId.value = id }
function renameConv(c) {
  ElMessageBox.prompt('修改对话名称', '重命名', { inputValue: c.title }).then(({ value }) => { if (value) c.title = value }).catch(() => {})
}
function delConv(id) {
  ElMessageBox.confirm('删除此对话？', '确认删除', { type: 'warning' }).then(() => {
    conversations.value = conversations.value.filter(c => c.id !== id)
    if (activeConvId.value === id) activeConvId.value = conversations.value[0]?.id
  }).catch(() => {})
}

function renderMd(text) {
  if (!text) return ''
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\n## (.+)/g, '\n<h4>$1</h4>').replace(/\n- (.+)/g, '\n• $1').replace(/\n/g, '<br>')
}

async function checkOnline() {
  try { const r = await fetch('http://localhost:11434/api/tags'); online.value = r.ok } catch { online.value = false }
}

async function sendChat() {
  const q = chatInput.value.trim()
  if (!q || !activeConv.value) return
  activeConv.value.messages.push({ role: 'user', content: q })
  if (activeConv.value.title === '新对话' && activeConv.value.messages.length === 1) {
    activeConv.value.title = q.slice(0, 30) + (q.length > 30 ? '...' : '')
  }
  chatInput.value = ''; chatLoading.value = true
  await nextTick(); if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
  try {
    const resp = await fetch('/api/ai/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('access_token')}` },
      body: JSON.stringify({ question: q, mode: chatMode.value }),
    })
    const data = await resp.json()
    activeConv.value.messages.push({ role: 'assistant', content: data.reply || data.content || data.answer || data.detail || '无回复' })
  } catch (e) {
    activeConv.value.messages.push({ role: 'assistant', content: '请求失败: ' + e.message })
  }
  chatLoading.value = false
  await nextTick(); if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight
}

async function onImagesSelected(e) {
  const files = e.target.files; if (!files?.length) return
  imgFiles.value = Array.from(files); imgLoading.value = true; imgResult.value = ''
  const fd = new FormData(); for (const f of files) fd.append('files', f)
  try {
    const resp = await fetch('/api/report-gen/image-to-report', {
      method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('access_token')}` }, body: fd,
    })
    const data = await resp.json().catch(() => ({}))
    if (!resp.ok) imgResult.value = data.detail || `请求失败(${resp.status})`
    else if (data.ok === false) imgResult.value = data.detail || data.error || '识别失败'
    else imgResult.value = data.content || '无结果'
  } catch (e) { imgResult.value = '识别失败: ' + e.message }
  imgLoading.value = false; e.target.value = ''
}

async function copyResult() {
  try { await navigator.clipboard.writeText(imgResult.value); ElMessage.success('已复制') } catch { ElMessage.error('复制失败') }
}

onMounted(() => { loadConvs(); checkOnline() })
</script>

<style scoped>
.ai-page { display: flex; gap: 0; height: calc(100vh - 100px); max-width: 100%; }
.conv-sidebar { width: 220px; flex-shrink: 0; border-right: 1px solid var(--border); background: var(--bg-white); display: flex; flex-direction: column; padding: 8px; border-radius: 8px 0 0 8px; }
.conv-list { flex: 1; overflow-y: auto; }
.conv-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; margin-bottom: 2px; transition: background .12s; }
.conv-item:hover { background: var(--bg); }
.conv-item.active { background: var(--primary-light); color: var(--primary); font-weight: 500; }
.conv-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-actions { display: none; gap: 2px; }
.conv-item:hover .conv-actions { display: flex; }
.conv-footer { padding: 8px 10px; font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 4px; border-top: 1px solid var(--border); }
.dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.dot.green { background: #22c55e; }
.dot.gray { background: #9ca3af; }

.chat-main { flex: 1; display: flex; flex-direction: column; background: var(--bg-white); border-radius: 0 8px 8px 0; min-width: 0; }
.header-tabs { display: flex; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--border); gap: 8px; }
.chat-area { display: flex; flex-direction: column; flex: 1; }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px 20px; }
.chat-msg { margin-bottom: 14px; display: flex; }
.msg-user { justify-content: flex-end; }
.msg-user .msg-content { background: var(--primary); color: #fff; border-radius: 12px 12px 0 12px; max-width: 72%; padding: 10px 14px; font-size: 14px; }
.msg-assistant .msg-content { background: var(--bg); border-radius: 12px 12px 12px 0; max-width: 85%; padding: 12px 16px; font-size: 14px; line-height: 1.65; }
.chat-empty { text-align: center; padding: 40px; color: var(--text-muted); }
.chat-input-bar { display: flex; gap: 8px; padding: 10px 16px; border-top: 1px solid var(--border); }
.quick-qs { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 12px; }
.q-tag { background: var(--primary-light); color: var(--primary); padding: 4px 12px; border-radius: 12px; font-size: 12px; cursor: pointer; }
.q-tag:hover { background: var(--primary); color: #fff; }

.image-area { padding: 16px; overflow-y: auto; }
.upload-zone { text-align: center; padding: 50px 20px; border: 2px dashed var(--border); border-radius: 8px; }
.img-result { margin-top: 16px; }
.result-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; border: 1px solid var(--border); border-radius: 8px 8px 0 0; font-weight: 600; }
.result-content { padding: 14px; border: 1px solid var(--border); border-top: none; border-radius: 0 0 8px 8px; max-height: 500px; overflow-y: auto; line-height: 1.7; font-size: 14px; }
</style>
