<template>
  <div>
    <!-- Prompt Management -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">提示词管理</span>
        </div>
      </template>
      <el-tabs v-model="activePrompt" @tab-change="handleTabChange" class="prompt-tabs">
        <el-tab-pane v-for="p in prompts" :key="p.name" :label="promptLabels[p.name]" :name="p.name">
          <el-input
            v-model="p.content"
            type="textarea"
            :rows="16"
            class="prompt-editor"
          />
          <div class="prompt-actions">
            <el-button @click="resetPrompt(p.name)">重置</el-button>
            <el-button type="primary" @click="savePrompt(p.name)" :loading="saving">保存</el-button>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- System Config -->
    <el-card class="section-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">系统配置</span>
        </div>
      </template>
      <el-form :model="sysConfig" label-width="160px" class="config-form">
        <el-form-item label="心跳间隔 (秒)">
          <el-input-number v-model="sysConfig.heartbeat_interval" :min="5" />
        </el-form-item>
        <el-form-item label="心跳超时 (秒)">
          <el-input-number v-model="sysConfig.heartbeat_timeout" :min="1" />
        </el-form-item>
        <el-form-item label="Token 刷新间隔 (秒)">
          <el-input-number v-model="sysConfig.token_refresh_interval" :min="60" />
        </el-form-item>
        <el-form-item label="人工接管超时 (秒)">
          <el-input-number v-model="sysConfig.manual_mode_timeout" :min="60" />
        </el-form-item>
        <el-form-item label="消息过期时间 (毫秒)">
          <el-input-number v-model="sysConfig.message_expire_time" :min="10000" />
        </el-form-item>
        <el-form-item label="模拟人工输入">
          <el-switch v-model="sysConfig.simulate_human_typing" />
        </el-form-item>
        <el-form-item label="接管关键词">
          <el-input v-model="sysConfig.toggle_keywords" placeholder="多个关键词用逗号分隔" />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="sysConfig.model_name" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="saveConfig" :loading="savingConfig">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api'

const promptLabels: Record<string, string> = {
  classify: '分类路由', price: '价格专家', tech: '技术专家', default: '默认回复',
}

const prompts = ref<any[]>([])
const activePrompt = ref('classify')
const saving = ref(false)
const savingConfig = ref(false)
const sysConfig = reactive<Record<string, any>>({})

async function fetchPrompts() {
  const { data } = await api.get('/config/prompts')
  prompts.value = data
}

function handleTabChange() { /* no-op, content is reactive */ }

function resetPrompt(name: string) {
  const p = prompts.value.find(p => p.name === name)
  if (p) fetchPrompts()
}

async function savePrompt(name: string) {
  const p = prompts.value.find(p => p.name === name)
  if (!p) return
  saving.value = true
  try {
    await api.put(`/config/prompts/${name}`, { content: p.content })
    ElMessage.success('提示词已保存')
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}

async function fetchConfig() {
  const { data } = await api.get('/config/system')
  Object.assign(sysConfig, data)
}

async function saveConfig() {
  savingConfig.value = true
  try {
    await api.put('/config/system', sysConfig)
    ElMessage.success('配置已保存（部分需重启生效）')
  } catch { ElMessage.error('保存失败') }
  finally { savingConfig.value = false }
}

onMounted(() => { fetchPrompts(); fetchConfig() })
</script>

<style scoped>
.section-card {
  margin-bottom: var(--space-5);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 600;
  font-size: var(--text-base);
}

.prompt-tabs :deep(.el-tabs__header) {
  margin-bottom: var(--space-4);
}

.prompt-editor :deep(.el-textarea__inner) {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  line-height: 1.7;
  border-radius: var(--radius-md);
}

.prompt-actions {
  margin-top: var(--space-4);
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.config-form {
  max-width: 640px;
}

.config-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: var(--color-text-secondary);
}
</style>
