<template>
  <el-container style="height: 100vh">
    <el-aside :width="sidebarWidth" class="app-sidebar">
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <div class="brand-mark">
            <el-icon :size="20" color="#fff"><Monitor /></el-icon>
          </div>
          <transition name="fade">
            <span v-if="!collapsed" class="brand-name">闲鱼助手</span>
          </transition>
        </div>
        <div class="sidebar-status" v-if="!collapsed">
          <span class="status-dot" :class="botOnline ? 'online' : 'offline'"></span>
          <span class="status-text">{{ botOnline ? 'Bot 在线' : 'Bot 离线' }}</span>
          <button
            class="bot-toggle-btn"
            :class="botOnline ? 'bot-stop' : 'bot-start'"
            @click="toggleBot"
            :disabled="botToggling"
            :title="botOnline ? '停止机器人' : '启动机器人'"
          >
            {{ botToggling ? '...' : (botOnline ? '停止' : '启动') }}
          </button>
        </div>
      </div>

      <el-menu
        :default-active="route.path || '/'"
        router
        :collapse="collapsed"
        background-color="transparent"
        text-color="rgba(248, 250, 252, 0.65)"
        active-text-color="#fff"
        class="sidebar-menu"
      >
        <el-menu-item index="/">
          <el-icon><DataAnalysis /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/conversations">
          <el-icon><ChatDotRound /></el-icon>
          <span>对话监控</span>
        </el-menu-item>
        <el-menu-item index="/items">
          <el-icon><Goods /></el-icon>
          <span>商品管理</span>
        </el-menu-item>
        <el-menu-item index="/analytics">
          <el-icon><TrendCharts /></el-icon>
          <span>数据分析</span>
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>
          <span>配置管理</span>
        </el-menu-item>
        <el-menu-item index="/logs">
          <el-icon><Document /></el-icon>
          <span>运行日志</span>
        </el-menu-item>
      </el-menu>

      <div class="sidebar-footer">
        <button class="collapse-btn" @click="collapsed = !collapsed" :title="collapsed ? '展开' : '收起'">
          <el-icon :size="16">
            <DArrowLeft v-if="!collapsed" />
            <DArrowRight v-else />
          </el-icon>
        </button>
      </div>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <h2 class="page-title">{{ pageTitle }}</h2>
        </div>
        <div class="header-right">
          <div class="header-status" v-if="botOnline">
            <span class="status-dot online"></span>
            <span class="status-label">运行中</span>
          </div>
          <el-divider direction="vertical" />
          <span class="header-username">{{ auth.username }}</span>
          <el-button text class="logout-btn" @click="handleLogout">
            <el-icon :size="16"><SwitchButton /></el-icon>
            <span>退出</span>
          </el-button>
        </div>
      </el-header>
      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import api from '../api'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const botOnline = ref(false)
const collapsed = ref(false)
const botToggling = ref(false)
let timer: number | null = null

const sidebarWidth = computed(() => collapsed.value ? '64px' : '220px')

const pageTitles: Record<string, string> = {
  '/': '仪表盘',
  '/conversations': '对话监控',
  '/items': '商品管理',
  '/analytics': '数据分析',
  '/config': '配置管理',
  '/logs': '运行日志',
}

const pageTitle = computed(() => pageTitles[route.path] || '闲鱼智能助手')

async function checkStatus() {
  try {
    const { data } = await api.get('/status')
    botOnline.value = data.bot_online
  } catch {
    botOnline.value = false
  }
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

async function toggleBot() {
  botToggling.value = true
  try {
    const endpoint = botOnline.value ? '/bot/stop' : '/bot/start'
    const { data } = await api.post(endpoint)
    if (data.error) {
      ElMessage.error(data.error)
    } else {
      ElMessage.success(data.message)
      await checkStatus()
    }
  } catch {
    ElMessage.error(botOnline.value ? '停止失败' : '启动失败')
  } finally {
    botToggling.value = false
  }
}

onMounted(() => {
  checkStatus()
  timer = window.setInterval(checkStatus, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.app-sidebar {
  background: var(--color-bg-sidebar);
  display: flex;
  flex-direction: column;
  transition: width var(--transition-base);
  overflow: hidden;
}

.sidebar-header {
  padding: var(--space-5);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.brand-mark {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--color-primary), #60A5FA);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-name {
  color: #fff;
  font-size: var(--text-xl);
  font-weight: 700;
  white-space: nowrap;
  letter-spacing: -0.3px;
}

.sidebar-status {
  margin-top: var(--space-3);
  display: flex;
  align-items: center;
  padding-left: 4px;
}

.status-text {
  color: rgba(248, 250, 252, 0.5);
  font-size: var(--text-xs);
}

.bot-toggle-btn {
  margin-left: auto;
  padding: 2px 10px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-sans);
}

.bot-toggle-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.bot-toggle-btn.bot-start {
  background: rgba(16, 185, 129, 0.2);
  color: #34D399;
}

.bot-toggle-btn.bot-start:hover:not(:disabled) {
  background: rgba(16, 185, 129, 0.35);
}

.bot-toggle-btn.bot-stop {
  background: rgba(239, 68, 68, 0.2);
  color: #F87171;
}

.bot-toggle-btn.bot-stop:hover:not(:disabled) {
  background: rgba(239, 68, 68, 0.35);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  padding: var(--space-2) var(--space-3);
}

.sidebar-menu .el-menu-item {
  border-radius: var(--radius-md);
  margin-bottom: 2px;
  height: 42px;
  line-height: 42px;
  transition: all var(--transition-fast);
}

.sidebar-menu .el-menu-item:hover {
  background: var(--color-bg-sidebar-hover) !important;
  color: #fff !important;
}

.sidebar-menu .el-menu-item.is-active {
  background: var(--color-bg-sidebar-active) !important;
  color: #fff !important;
  font-weight: 500;
}

.sidebar-footer {
  padding: var(--space-3);
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.collapse-btn {
  width: 100%;
  height: 36px;
  border: none;
  background: rgba(255, 255, 255, 0.05);
  border-radius: var(--radius-md);
  color: rgba(248, 250, 252, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
}

.collapse-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}

.app-header {
  height: var(--header-height);
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-6);
  box-shadow: var(--shadow-sm);
}

.header-left {
  display: flex;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.header-status {
  display: flex;
  align-items: center;
}

.status-label {
  font-size: var(--text-sm);
  color: var(--color-success);
  font-weight: 500;
}

.header-username {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.logout-btn {
  color: var(--color-text-secondary) !important;
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: var(--space-1);
}

.logout-btn:hover {
  color: var(--color-danger) !important;
}

.app-main {
  background: var(--color-bg);
  padding: var(--space-6);
  overflow: auto;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity var(--transition-fast);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
