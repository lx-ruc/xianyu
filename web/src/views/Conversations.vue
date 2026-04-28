<template>
  <div class="conversations-layout">
    <!-- Left: Conversation List -->
    <div class="conv-list-panel">
      <div class="panel-header">
        <span class="panel-title">会话列表</span>
        <el-tag size="small" type="info">{{ store.conversations.length }}</el-tag>
      </div>
      <div class="conv-list">
        <div
          v-for="conv in store.conversations"
          :key="conv.chat_id"
          class="conv-item"
          :class="{ active: store.currentChatId === conv.chat_id }"
          @click="selectConversation(conv.chat_id)"
        >
          <div class="conv-item-header">
            <span class="conv-user">{{ conv.user_id }}</span>
            <el-tag
              :type="conv.mode === 'manual' ? 'danger' : 'success'"
              size="small"
              effect="light"
            >
              {{ conv.mode === 'manual' ? '人工' : 'AI' }}
            </el-tag>
          </div>
          <div class="conv-preview">{{ conv.last_message }}</div>
          <div class="conv-time">{{ conv.last_time }}</div>
        </div>
        <el-empty v-if="!store.conversations.length" description="暂无会话" :image-size="60" />
      </div>
    </div>

    <!-- Right: Chat Detail -->
    <div class="conv-detail-panel">
      <div class="panel-header">
        <span class="panel-title">
          {{ store.currentChatId ? `会话 ${store.currentChatId}` : '选择会话' }}
        </span>
        <el-switch
          v-if="store.currentChatId"
          v-model="isManual"
          active-text="人工接管"
          inactive-text="AI自动"
          inline-prompt
          style="--el-switch-on-color: var(--color-danger); --el-switch-off-color: var(--color-success)"
          @change="handleToggleMode"
        />
      </div>

      <div ref="chatContainer" class="chat-messages">
        <div
          v-for="msg in store.currentMessages"
          :key="msg.id"
          class="chat-row"
          :class="msg.role === 'user' ? 'row-user' : 'row-bot'"
        >
          <div class="chat-bubble" :class="msg.role === 'user' ? 'user' : 'bot'">
            <div class="chat-role">{{ msg.role === 'user' ? '用户' : '机器人' }}</div>
            <div class="chat-text">{{ msg.content }}</div>
          </div>
        </div>
        <el-empty v-if="!store.currentMessages.length" description="选择一个会话查看" :image-size="80" />
      </div>

      <div class="chat-input-bar" v-if="store.currentChatId">
        <el-input
          v-model="replyText"
          placeholder="输入消息手动回复..."
          @keyup.enter="sendReply"
          clearable
        />
        <el-button type="primary" @click="sendReply" :disabled="!replyText.trim()">
          发送
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useConversationsStore } from '../stores/conversations'

const store = useConversationsStore()
const replyText = ref('')
const chatContainer = ref<HTMLElement>()

const isManual = computed({
  get: () => store.currentMode === 'manual',
  set: () => {},
})

async function selectConversation(chatId: string) {
  await store.fetchMessages(chatId)
  await nextTick()
  scrollBottom()
}

async function handleToggleMode(val: boolean) {
  if (!store.currentChatId) return
  const mode = val ? 'manual' : 'auto'
  await store.toggleMode(store.currentChatId, mode)
  ElMessage.success(mode === 'manual' ? '已切换为人工接管' : '已切换为AI自动')
}

async function sendReply() {
  if (!replyText.value.trim() || !store.currentChatId) return
  try {
    await store.sendReply(store.currentChatId, replyText.value)
    replyText.value = ''
    await store.fetchMessages(store.currentChatId)
    await nextTick()
    scrollBottom()
  } catch {
    ElMessage.error('发送失败')
  }
}

function scrollBottom() {
  if (chatContainer.value) {
    chatContainer.value.scrollTop = chatContainer.value.scrollHeight
  }
}

onMounted(() => store.fetchConversations())
</script>

<style scoped>
.conversations-layout {
  display: flex;
  gap: var(--space-4);
  height: calc(100vh - var(--header-height) - var(--space-6) * 2 - var(--space-5));
}

.conv-list-panel,
.conv-detail-panel {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-light);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conv-list-panel {
  width: 320px;
  flex-shrink: 0;
}

.conv-detail-panel {
  flex: 1;
  min-width: 0;
}

.panel-header {
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--color-border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.panel-title {
  font-weight: 600;
  font-size: var(--text-base);
  color: var(--color-text);
}

.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-2);
}

.conv-item {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
  margin-bottom: 2px;
}

.conv-item:hover {
  background: var(--color-bg);
}

.conv-item.active {
  background: var(--color-primary-lighter);
}

.conv-item-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.conv-user {
  font-weight: 600;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.conv-preview {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conv-time {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin-top: var(--space-1);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5);
}

.chat-row {
  display: flex;
  margin-bottom: var(--space-4);
}

.chat-row.row-user {
  justify-content: flex-start;
}

.chat-row.row-bot {
  justify-content: flex-end;
}

.chat-bubble {
  max-width: 65%;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  font-size: var(--text-sm);
  line-height: 1.6;
  word-break: break-word;
}

.chat-bubble.user {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  border-bottom-left-radius: var(--radius-sm);
}

.chat-bubble.bot {
  background: var(--color-primary);
  color: var(--color-text-inverse);
  border-bottom-right-radius: var(--radius-sm);
}

.chat-role {
  font-size: var(--text-xs);
  opacity: 0.7;
  margin-bottom: var(--space-1);
}

.chat-input-bar {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid var(--color-border-light);
  display: flex;
  gap: var(--space-2);
  flex-shrink: 0;
}

.chat-input-bar .el-input {
  flex: 1;
}
</style>
