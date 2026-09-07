<template>
  <div>
    <!-- Floating AI button -->
    <div class="ai-fab" @click="toggle" :class="{active: open}">
      <span class="ai-fab-icon">AI</span>
    </div>

    <!-- AI Panel -->
    <transition name="slide">
      <div v-if="open" class="ai-panel">
        <div class="ai-header">
          <span class="ai-title">AI 助手</span>
          <div style="display:flex;gap:4px">
            <el-button link size="small" @click="mode='chat'" :class="{activeMode:mode==='chat'}">问答</el-button>
            <el-button link size="small" @click="mode='actions'" :class="{activeMode:mode==='actions'}">工具</el-button>
            <el-button link size="small" @click="open=false"><el-icon><Close /></el-icon></el-button>
          </div>
        </div>

        <!-- Chat Mode -->
        <div v-if="mode==='chat'" class="ai-body">
          <div class="chat-messages" ref="chatRef">
            <div v-for="(msg,i) in chatHistory" :key="i" class="chat-msg" :class="'msg-'+msg.role">
              <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
            </div>
            <div v-if="chatLoading" class="chat-msg msg-assistant">
              <div class="msg-content"><em>思考中...</em></div>
            </div>
            <div v-if="chatHistory.length===0 && !chatLoading" style="text-align:center;padding:40px;color:var(--text-muted);font-size:13px">
              {{ online ? 'AI已就绪，输入问题开始对话' : 'AI未启用，请检查 Ollama 是否运行' }}
            </div>
          </div>
          <div class="chat-input">
            <el-input v-model="chatInput" placeholder="提问，如：哪些项目有风险？" size="small"
              @keyup.enter="sendChat" :disabled="chatLoading || !online" />
            <el-button size="small" type="primary" @click="sendChat" :loading="chatLoading" :disabled="!online">发送</el-button>
          </div>
          <div class="chat-suggestions">
            <span v-for="q in quickQuestions" :key="q" class="sug-tag" @click="chatInput=q;sendChat()">{{ q }}</span>
          </div>
        </div>

        <!-- Actions Mode -->
        <div v-if="mode==='actions'" class="ai-body">
          <div class="action-list">
            <div class="action-card" @click="goReport">
              <span class="action-icon">📄</span>
              <div>
                <div class="action-name">AI 生成报告</div>
                <div class="action-desc">基于模板库+项目数据自动生成各类报告</div>
              </div>
            </div>
            <div class="action-card" @click="openProjectReport">
              <span class="action-icon">📝</span>
              <div>
                <div class="action-name">AI 生成周报</div>
                <div class="action-desc">基于技术线数据自动生成周报内容</div>
              </div>
            </div>
            <div class="action-card" @click="triggerImageUpload">
              <span class="action-icon">📷</span>
              <div>
                <div class="action-name">图片转报告</div>
                <div class="action-desc">上传截图/白板/文档照片 → AI 生成报告</div>
              </div>
            </div>
            <div class="action-card" @click="mode='chat'">
              <span class="action-icon">💬</span>
              <div>
                <div class="action-name">智能问答</div>
                <div class="action-desc">提问任何项目管理相关问题</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Status indicator -->
        <div class="ai-footer">
          <span class="ai-status" :class="online ? 'online' : 'offline'"></span>
          {{ online ? modelName : 'AI未启用 — 请启动 Ollama' }}
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { Close } from '@element-plus/icons-vue'
import api from '../../api/index.js'
import { useRouter } from 'vue-router'

const router = useRouter()

const open = ref(false)
const mode = ref('actions')
const online = ref(false)
const modelName = ref('')
const chatInput = ref('')
const chatHistory = ref([])
const chatLoading = ref(false)
const chatRef = ref(null)

const quickQuestions = [
  '哪些项目处于阻塞状态？',
  '本周周报提交情况如何？',
  '当前最大的风险是什么？',
  '总结所有项目的整体健康状况',
]

onMounted(async () => {
  try {
    const res = await api.get('/ai/config')
    online.value = res.data?.enabled || false
    modelName.value = res.data?.model || ''
  } catch (e) {
    online.value = false
  }
})

function toggle() { open.value = !open.value }

function goReport() {
  open.value = false
  const match = window.location.pathname.match(/\/projects\/(\d+)/)
  if (match) {
    router.push(`/projects/${match[1]}?tab=report`)
  } else {
    router.push('/projects')
  }
}

function openProjectReport() {
  open.value = false
  const match = window.location.pathname.match(/\/projects\/(\d+)/)
  if (match) {
    router.push(`/projects/${match[1]}?tab=weekly`)
  } else {
    router.push('/my-work')
  }
}

const imageUploading = ref(false)
function triggerImageUpload() {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = 'image/png,image/jpeg,image/jpg,image/gif,image/bmp,image/webp'
  input.onchange = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    imageUploading.value = true
    mode.value = 'chat'
    const names = Array.from(files).map(f => f.name).join(', ')
    chatHistory.value.push({ role: 'user', content: `📷 正在识别 ${files.length} 张图片: ${names}...` })
    try {
      const fd = new FormData()
      for (const file of files) {
        fd.append('files', file)
      }
      fd.append('report_type', 'stage_report')
      fd.append('context', '')
      const res = await api.post('/report-gen/image-to-report', fd, {
        timeout: 180000,
      })
      const d = res.data
      if (d.ok === false) {
        const errs = (d.ocr_errors || []).map(x => '• ' + x).join('\n')
        chatHistory.value.push({ role: 'assistant', content: '⚠️ ' + (d.detail || d.error || '图片识别失败') + (errs ? '\n' + errs : '') })
      } else {
        chatHistory.value.push({ role: 'assistant', content: d.content || '未生成内容' })
      }
    } catch (e) {
      chatHistory.value.push({ role: 'assistant', content: '图片识别失败: ' + (e?.response?.data?.detail || e?.message || '未知错误') })
    } finally {
      imageUploading.value = false
    }
  }
  input.click()
}

async function sendChat() {
  const q = chatInput.value.trim()
  if (!q || !online.value) return
  chatHistory.value.push({ role: 'user', content: q })
  chatInput.value = ''
  chatLoading.value = true
  try {
    const res = await api.post('/ai/chat', { question: q, mode: 'auto' })
    chatHistory.value.push({ role: 'assistant', content: res.data.reply || res.data.content || JSON.stringify(res.data) })
  } catch (e) {
    chatHistory.value.push({ role: 'assistant', content: 'AI调用失败: ' + (e?.response?.data?.detail || e?.message || '未知错误') })
  } finally {
    chatLoading.value = false
    nextTick(() => { if (chatRef.value) chatRef.value.scrollTop = chatRef.value.scrollHeight })
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n## (.+)/g, '\n<h4>$1</h4>')
    .replace(/\n- (.+)/g, '\n• $1')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
.ai-fab {
  position:fixed; bottom:24px; right:24px; z-index:999;
  width:52px; height:52px; border-radius:50%;
  background:linear-gradient(135deg,#3b82f6,#8b5cf6);
  color:#fff; display:flex; align-items:center; justify-content:center;
  cursor:pointer; box-shadow:0 4px 16px rgba(59,130,246,.4);
  transition:transform .2s, box-shadow .2s;
}
.ai-fab:hover { transform:scale(1.1); box-shadow:0 6px 24px rgba(59,130,246,.5); }
.ai-fab.active { background:linear-gradient(135deg,#ef4444,#f59e0b); }
.ai-fab-icon { font-size:18px; font-weight:800; letter-spacing:1px; }

.ai-panel {
  position:fixed; bottom:88px; right:24px; z-index:998;
  width:420px; max-height:580px;
  background:var(--bg-white); border:1px solid var(--border);
  border-radius:12px; box-shadow:0 8px 32px rgba(0,0,0,.12);
  display:flex; flex-direction:column; overflow:hidden;
}

.ai-header {
  display:flex; justify-content:space-between; align-items:center;
  padding:12px 16px; border-bottom:1px solid var(--border);
  background:#fafafa;
}
.ai-title { font-weight:700; font-size:14px; color:var(--text); }
.activeMode { color:var(--primary) !important; font-weight:600; }

.ai-body { flex:1; overflow-y:auto; padding:12px; }

.chat-messages { max-height:300px; overflow-y:auto; margin-bottom:8px; }
.chat-msg { margin-bottom:10px; }
.msg-content { font-size:13px; line-height:1.6; padding:8px 12px; border-radius:8px; max-width:90%; }
.msg-content h4 { font-size:13px; margin:6px 0 4px; color:var(--text); }
.msg-user .msg-content { background:var(--primary-light); color:var(--text); margin-left:auto; }
.msg-assistant .msg-content { background:#f3f4f6; color:var(--text); }

.chat-input { display:flex; gap:6px; margin-bottom:8px; }
.chat-suggestions { display:flex; flex-wrap:wrap; gap:4px; }
.sug-tag { font-size:11px; color:var(--primary); background:var(--primary-light); padding:3px 8px; border-radius:10px; cursor:pointer; }
.sug-tag:hover { background:#dbeafe; }

.action-list { display:flex; flex-direction:column; gap:8px; }
.action-card {
  display:flex; align-items:center; gap:12px;
  padding:14px; border-radius:8px; border:1px solid var(--border);
  cursor:pointer; transition: all .15s;
}
.action-card:hover { border-color:var(--primary); background:var(--primary-light); }
.action-icon { font-size:24px; flex-shrink:0; }
.action-name { font-size:14px; font-weight:600; color:var(--text); }
.action-desc { font-size:12px; color:var(--text-muted); margin-top:2px; }

.ai-footer {
  padding:8px 16px; border-top:1px solid var(--border);
  font-size:11px; color:var(--text-muted); display:flex; align-items:center; gap:6px;
}
.ai-status { width:6px; height:6px; border-radius:50%; display:inline-block; }
.ai-status.online { background:#10b981; }
.ai-status.offline { background:#d1d5db; }

.slide-enter-active, .slide-leave-active { transition:all .25s ease; }
.slide-enter-from, .slide-leave-to { opacity:0; transform:translateY(20px); }
</style>
