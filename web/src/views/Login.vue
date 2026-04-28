<template>
  <div class="login-page">
    <div class="login-bg-pattern"></div>
    <div class="login-container">
      <div class="login-brand">
        <div class="brand-icon">
          <el-icon :size="28"><Monitor /></el-icon>
        </div>
        <h1 class="brand-title">闲鱼智能助手</h1>
        <p class="brand-subtitle">AI 智能客服管理平台</p>
      </div>
      <el-form :model="form" @submit.prevent="handleLogin" class="login-form">
        <el-form-item>
          <el-input
            v-model="form.username"
            placeholder="用户名"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="loading"
            native-type="submit"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', password: '' })

async function handleLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    router.push('/')
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } } }
    ElMessage.error(err.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
  position: relative;
  overflow: hidden;
}

.login-bg-pattern {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(circle at 20% 50%, rgba(37, 99, 235, 0.15) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, rgba(59, 130, 246, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 50% 80%, rgba(249, 115, 22, 0.08) 0%, transparent 50%);
  pointer-events: none;
}

.login-container {
  width: 400px;
  background: rgba(255, 255, 255, 0.97);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg), 0 0 80px rgba(37, 99, 235, 0.1);
  padding: var(--space-8) var(--space-8) var(--space-6);
  position: relative;
  z-index: 1;
}

.login-brand {
  text-align: center;
  margin-bottom: var(--space-8);
}

.brand-icon {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-primary), var(--color-primary-light));
  color: #fff;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: var(--space-4);
}

.brand-title {
  margin: 0;
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.5px;
}

.brand-subtitle {
  margin: var(--space-2) 0 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.login-form :deep(.el-input__wrapper) {
  border-radius: var(--radius-md);
  padding: 4px 12px;
}

.login-form :deep(.el-button) {
  height: 44px;
  font-size: var(--text-lg);
  font-weight: 600;
  border-radius: var(--radius-md);
}
</style>
