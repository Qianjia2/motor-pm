<template>
  <!-- Public pages: clean, no shell -->
  <div v-if="isPublicPage" class="app-public">
    <router-view v-slot="{ Component }">
      <component :is="Component" />
    </router-view>
  </div>
  <!-- Normal pages: full app shell -->
  <div v-else class="app-shell">
    <aside class="app-sidebar">
      <AppSidebar />
    </aside>
    <div class="app-main">
      <header class="app-topbar">
        <AppHeader @openSearch="searchRef?.open()" />
      </header>
      <GlobalSearch ref="searchRef" />
      <div class="app-breadcrumb" v-if="breadcrumbs.length">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{path:'/'}">首页</el-breadcrumb-item>
          <el-breadcrumb-item v-for="b in breadcrumbs" :key="b.path" :to="b.path ? {path:b.path} : undefined">
            {{ b.title }}
          </el-breadcrumb-item>
        </el-breadcrumb>
      </div>
      <main class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
    <AIAssistant />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from './stores/auth'
import AppSidebar from './components/layout/AppSidebar.vue'
import AppHeader from './components/layout/AppHeader.vue'
import GlobalSearch from './components/common/GlobalSearch.vue'
import AIAssistant from './components/ai/AIAssistant.vue'

const route = useRoute()
const searchRef = ref(null)

// Public pages get a clean layout without sidebar/header/breadcrumb
const isPublicPage = computed(() => {
  if (route.meta.public === true) return true
  if (route.path.startsWith('/kb/chat/')) return true
  if (route.path.startsWith('/portal/')) return true
  return false
})

const router = useRouter()
const authStore = useAuthStore()

onMounted(() => {
  if (localStorage.getItem('access_token')) {
    authStore.ensureNameMap()  // 刷新页面后仍显示中文名
  }

  if (route.query.bind_ok) {
    const name = route.query.name || '成员'
    ElMessage.success(`${decodeURIComponent(name)} 钉钉绑定成功！`)
    router.replace({ path: '/my-work', query: {} })
  }
})

function onAiDiagnose() {
  const match = window.location.pathname.match(/\/projects\/(\d+)/)
  if (match) router.push(`/projects/${match[1]}`)
}
function onAiWeekly() { router.push('/my-work') }
function onAiRisk() {
  const match = window.location.pathname.match(/\/projects\/(\d+)/)
  if (match) router.push(`/projects/${match[1]}`)
}

const breadcrumbs = computed(() => {
  const crumbs = []
  const meta = route.meta || {}
  if (meta.parent) crumbs.push({ title: meta.parent, path: null })
  if (meta.title && meta.title !== '项目驾驶舱') {
    crumbs.push({ title: meta.title, path: null })
  }
  // Handle project detail sub-pages
  if (route.params.id && meta.subtitle) {
    crumbs.push({ title: meta.subtitle, path: null })
  }
  return crumbs
})
</script>

<style>
:root {
  --primary: #3b82f6;
  --primary-light: #eff6ff;
  --primary-dark: #1d4ed8;
  --success: #10b981;
  --warning: #f59e0b;
  --danger: #ef4444;
  --text: #1f2937;
  --text-secondary: #6b7280;
  --text-muted: #9ca3af;
  --bg: #f3f4f6;
  --bg-white: #ffffff;
  --border: #e5e7eb;
  --sidebar-w: 220px;
  --topbar-h: 56px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,.05);
  --shadow: 0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.04);
  --shadow-md: 0 4px 6px rgba(0,0,0,.06), 0 2px 4px rgba(0,0,0,.04);
  --radius: 8px;
  --radius-sm: 6px;
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
  font-family: -apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;
  color: var(--text);
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}

.app-public { min-height:100vh; }
.app-shell { display:flex; min-height:100vh; }

.app-sidebar {
  width: var(--sidebar-w);
  background: var(--bg-white);
  border-right: 1px solid var(--border);
  flex-shrink: 0;
  display:flex; flex-direction:column;
  position: fixed; top:0; left:0; bottom:0; z-index:100;
}

.app-main {
  margin-left: var(--sidebar-w);
  flex:1; display:flex; flex-direction:column;
  min-width: 0;
}

.app-topbar {
  height: var(--topbar-h);
  background: var(--bg-white);
  border-bottom: 1px solid var(--border);
  padding: 0 24px;
  display:flex; align-items:center;
  position: sticky; top:0; z-index:50;
}

.app-breadcrumb {
  padding: 12px 24px 0;
  background: var(--bg);
}

.app-content {
  flex:1; padding: 16px 24px 32px;
}

/* Card */
.card {
  background: var(--bg-white);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
  padding: 20px;
}
.card-header {
  display:flex; justify-content:space-between; align-items:center;
  margin-bottom: 16px;
}
.card-title {
  font-size: 15px; font-weight: 600; color: var(--text);
  display:flex; align-items:center; gap:8px;
}
.card-title::before {
  content:''; display:inline-block; width:3px; height:16px;
  background: var(--primary); border-radius:2px;
}

/* Stat card */
.stat-grid {
  display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:16px;
}
.stat-card {
  background: var(--bg-white);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border);
  padding: 20px;
  transition: box-shadow .2s;
}
.stat-card:hover { box-shadow: var(--shadow-md); }
.stat-card .stat-value { font-size: 28px; font-weight: 700; color: var(--text); line-height:1.2; }
.stat-card .stat-label { font-size: 13px; color: var(--text-secondary); margin-top:4px; }
.stat-card .stat-icon { font-size: 24px; opacity: .7; }

/* Tags */
.tag { display:inline-block; padding:2px 10px; border-radius:10px; font-size:12px; font-weight:500; }
.tag-blue { background:#eff6ff; color:#3b82f6; }
.tag-green { background:#ecfdf5; color:#10b981; }
.tag-orange { background:#fff7ed; color:#f97316; }
.tag-red { background:#fef2f2; color:#ef4444; }
.tag-gray { background:#f3f4f6; color:#6b7280; }

/* Transitions */
.fade-slide-enter-active, .fade-slide-leave-active {
  transition: opacity .2s ease, transform .2s ease;
}
.fade-slide-enter-from { opacity:0; transform:translateY(8px); }
.fade-slide-leave-to { opacity:0; transform:translateY(-4px); }

/* Override Element Plus */
.el-menu { border-right:none !important; }
.el-breadcrumb { font-size:13px; }
.el-button--primary { --el-button-bg-color:var(--primary); --el-button-border-color:var(--primary); }
.el-tag { border-radius:4px; }
</style>
