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

        <!-- 账号选择器 -->
        <div class="account-selector" v-if="!collapsed">
          <el-select
            v-model="activeAccountId"
            size="small"
            popper-class="account-popper"
            placeholder="选择账号"
            @change="onAccountChange"
            class="account-select"
          >
            <el-option
              v-for="acc in accounts"
              :key="acc.account_id"
              :label="acc.display_name"
              :value="acc.account_id"
            >
              <span style="float: left">{{ acc.display_name }}</span>
              <span style="float: right" :style="{ color: acc.online ? 'var(--color-success)' : 'var(--color-danger)' }">
                {{ acc.online ? '在线' : '离线' }}
              </span>
            </el-option>
          </el-select>
          <div class="account-status-row">
            <span class="status-dot" :class="currentAccountOnline ? 'online' : 'offline'"></span>
            <span class="status-text" v-if="!currentAccountOnline">Bot 离线</span>
            <button
              class="bot-toggle-btn"
              :class="currentAccountOnline ? 'bot-stop' : 'bot-start'"
              @click="toggleBot"
              :disabled="botToggling"
              :title="currentAccountOnline ? '停止当前账号' : '启动当前账号'"
            >
              {{ botToggling ? '...' : (currentAccountOnline ? '停止' : '启动') }}
            </button>
          </div>
        </div>
        <div class="sidebar-status-mini" v-else>
          <span class="status-dot" :class="anyBotOnline ? 'online' : 'offline'"></span>
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
        <el-menu-item index="/orders">
          <el-icon><Box /></el-icon>
          <span>订单管理</span>
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
          <div class="header-status" v-if="accounts.length > 1">
            <span class="accounts-summary">{{ accounts.filter(a => a.online).length }}/{{ accounts.length }} 在线</span>
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
        <router-view :key="activeAccountId" :account-id="activeAccountId" />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, provide, watch } from 'vue'
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

// 多账号状态
const accounts = ref<any[]>([])
const activeAccountId = ref(localStorage.getItem('active_account_id') || '')

let timer: number | null = null

const sidebarWidth = computed(() => collapsed.value ? '64px' : '220px')

const pageTitles: Record<string, string> = {
  '/': '仪表盘',
  '/conversations': '对话监控',
  '/items': '商品管理',
  '/orders': '订单管理',
  '/analytics': '数据分析',
  '/config': '配置管理',
  '/logs': '运行日志',
}

const pageTitle = computed(() => pageTitles[route.path] || '闲鱼智能助手')

const anyBotOnline = computed(() => accounts.value.some(a => a.online))

const currentAccount = computed(() =>
  accounts.value.find(a => a.account_id === activeAccountId.value)
)

const currentAccountOnline = computed(() =>
  currentAccount.value?.online ?? false
)

// 提供给子组件
provide('activeAccountId', activeAccountId)

async function fetchAccounts() {
  try {
    const { data } = await api.get('/accounts')
    accounts.value = data || []
    // 如果没有选中账号，选第一个
    if (!activeAccountId.value && accounts.value.length > 0) {
      activeAccountId.value = accounts.value[0].account_id
      localStorage.setItem('active_account_id', activeAccountId.value)
    }
  } catch {
    // 回退到单账号状态检查
    try {
      const { data } = await api.get('/status')
      botOnline.value = data.bot_online
      if (data.accounts && data.accounts.length > 0) {
        accounts.value = data.accounts
        if (!activeAccountId.value) {
          activeAccountId.value = accounts.value[0].account_id
          localStorage.setItem('active_account_id', activeAccountId.value)
        }
      }
    } catch { /* ignore */ }
  }
}

function onAccountChange(id: string) {
  localStorage.setItem('active_account_id', id)
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

async function toggleBot() {
  if (!activeAccountId.value) return
  botToggling.value = true
  try {
    const endpoint = currentAccountOnline.value ? '/bot/stop' : '/bot/start'
    const { data } = await api.post(`${endpoint}?account_id=${activeAccountId.value}`)
    if (data.error) {
      ElMessage.error(data.error)
    } else {
      ElMessage.success(data.message)
      await fetchAccounts()
    }
  } catch {
    ElMessage.error(currentAccountOnline.value ? '停止失败' : '启动失败')
  } finally {
    botToggling.value = false
  }
}

onMounted(() => {
  fetchAccounts()
  timer = window.setInterval(fetchAccounts, 30000)
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
  padding: var(--space-4) var(--space-5);
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

.account-select {
  margin-top: var(--space-3);
  width: 100%;
}

.account-status-row {
  display: flex;
  align-items: center;
  margin-top: var(--space-2);
  gap: var(--space-2);
}

.sidebar-status-mini {
  margin-top: var(--space-3);
  display: flex;
  justify-content: center;
}

.status-text {
  color: rgba(248, 250, 252, 0.5);
  font-size: var(--text-xs);
  flex: 1;
}

.bot-toggle-btn {
  padding: 2px 8px;
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

.accounts-summary {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
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
