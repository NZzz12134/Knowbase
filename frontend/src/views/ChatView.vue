<template>
  <div class="chat-layout">
    <SessionSidebar :open="sidebarOpen" @close="sidebarOpen = false" @changed="onSessionChanged" @retry="initializeHistory" />

    <main id="main-content" tabindex="-1" class="chat-main" :inert="sidebarOpen">
      <header class="chat-header">
        <div class="header-left">
          <button class="icon-button mobile-menu" aria-label="打开会话列表" :aria-expanded="sidebarOpen" @click="sidebarOpen = true"><el-icon aria-hidden="true"><Fold /></el-icon></button>
          <span class="workspace-label">知识对话</span><span class="header-slash" aria-hidden="true">/</span>
          <h1>{{ currentTitle }}</h1>
        </div>
        <div class="header-right">
          <span class="scope-pill"><span></span>{{ currentKbName || '全部知识库' }}</span>
          <el-dropdown @command="onCommand">
            <button class="user-chip" aria-label="打开账户菜单">
              <el-avatar :size="29">{{ userInitial }}</el-avatar><span class="user-name">{{ auth.user?.username }}</span><el-icon aria-hidden="true"><ArrowDown /></el-icon>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="space">我的知识空间</el-dropdown-item>
                <el-dropdown-item command="models">我的模型设置</el-dropdown-item>
                <el-dropdown-item command="profile">个人中心 / 修改密码</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <FirstSteps @ready="refreshKnowledge" @models-ready="modelsReady = $event" />
      <MessageList
        ref="messageListRef"
        :messages="messages"
        :streaming="isStreaming"
        :loading="isLoadingMessages"
        :disabled="isStreaming || isLoadingMessages || !modelsReady"
        @feedback="onFeedback"
        @quick-ask="onSend"
        @retry="retryAnswer"
      />

      <ChatInput :disabled="isStreaming || isLoadingMessages || !modelsReady" :streaming="isStreaming" @stop="stopCurrentStream" @send="onSend" />
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ArrowDown, Fold } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { chatApi } from '../api/chat'
import { kbApi } from '../api/admin'
import { sessionApi } from '../api/session'
import ChatInput from '../components/chat/ChatInput.vue'
import FirstSteps from '../components/FirstSteps.vue'
import MessageList from '../components/chat/MessageList.vue'
import SessionSidebar from '../components/chat/SessionSidebar.vue'
import { useAuthStore } from '../stores/auth'
import { useSessionStore } from '../stores/session'

const router = useRouter()
const auth = useAuthStore()
const sessionStore = useSessionStore()

const messages = ref([])
const modelsReady = ref(false)
const sidebarOpen = ref(false)
const isLoadingMessages = ref(true)
// 当前活动流的会话 id；null = 无流。绑定到会话而非全局，切换会话时可中止旧流
const streamingSessionId = ref(null)
let currentStreamAbort = null
let loadSeq = 0 // loadMessages 竞态守卫：只接受最新一次请求的结果
let localMessageId = 0
let displayedSessionId = null
let scrollFrame = 0
let historyInitController = null

const kbs = ref([])
const messageListRef = ref(null)

const currentTitle = computed(
  () => sessionStore.sessions.find((s) => s.id === sessionStore.currentId)?.title || '新会话'
)
const currentKbName = computed(() => {
  const session = sessionStore.sessions.find((s) => s.id === sessionStore.currentId)
  if (!session?.kb_id) return null
  return kbs.value.find((k) => k.id === session.kb_id)?.name || null
})
const userInitial = computed(() => (auth.user?.username || '?').slice(0, 1).toUpperCase())
const isStreaming = computed(() => streamingSessionId.value !== null)

onMounted(() => {
  // kb 列表只用于展示 tag，失败不应拖垮会话列表（独立容错）
  kbApi.list().then((data) => (kbs.value = data)).catch(() => {})
  initializeHistory()
})

async function initializeHistory() {
  historyInitController?.abort()
  const controller = new AbortController()
  historyInitController = controller
  const selectionAtStart = sessionStore.currentId
  const seqAtStart = loadSeq
  isLoadingMessages.value = true
  try {
    const sessions = await sessionStore.fetchSessions({ retry: true, signal: controller.signal })
    // 离开页面或用户已选择/创建会话时，初始化响应不能覆盖新状态。
    if (controller.signal.aborted || seqAtStart !== loadSeq || selectionAtStart !== sessionStore.currentId) return
    // 校验 currentId 仍在列表中（换账号登录等场景下可能残留），不在则纠正
    if (
      sessionStore.currentId &&
      !sessions.some((s) => s.id === sessionStore.currentId)
    ) {
      sessionStore.setCurrent(null)
    }
    if (sessionStore.currentId) {
      await loadMessages(sessionStore.currentId)
    } else if (sessions.length) {
      sessionStore.setCurrent(sessions[0].id)
      await loadMessages(sessions[0].id)
    }
  } catch (_) {
    /* 侧边栏显示加载失败及重试入口。 */
  } finally {
    if (!controller.signal.aborted && seqAtStart === loadSeq) isLoadingMessages.value = false
  }
}

/** 加载历史消息（带竞态守卫：快速切换会话时旧响应被丢弃） */
async function loadMessages(sessionId) {
  const seq = ++loadSeq
  isLoadingMessages.value = true
  try {
    const data = await sessionApi.messages(sessionId, { page: 1, page_size: 200 })
    if (seq !== loadSeq || sessionStore.currentId !== sessionId) return
    displayedSessionId = sessionId
    messages.value = data.items.map((m) => ({ ...m, _key: m.id, citations: [] }))
    scrollToBottom(false)
  } finally {
    if (seq === loadSeq) isLoadingMessages.value = false
  }
}

/** 侧边栏会话切换 / 新建 / 删除：中止不属于目标会话的流，重载消息区 */
async function onSessionChanged(sessionId) {
  historyInitController?.abort()
  sidebarOpen.value = false
  // 点击当前会话时保留正在流式更新的消息，避免历史响应覆盖它。
  if (sessionId && displayedSessionId === sessionId && streamingSessionId.value === sessionId) return
  if (streamingSessionId.value && streamingSessionId.value !== sessionId) {
    currentStreamAbort?.()
  }
  if (sessionId) {
    displayedSessionId = null
    messages.value = []
    await loadMessages(sessionId)
  } else {
    displayedSessionId = null
    loadSeq++ // 使在途的旧加载结果失效
    isLoadingMessages.value = false
    messages.value = []
  }
}

function refreshKnowledge() { kbApi.list().then(data => { kbs.value = data }).catch(() => {}) }

async function retryAnswer(message) {
  if (!modelsReady.value || isStreaming.value || isLoadingMessages.value || message !== messages.value.at(-1)) return
  const question = messages.value.at(-2)?.content
  if (!question) return
  if (!message.id) {
    try {
      const data = await sessionApi.messages(sessionStore.currentId, { page: 1, page_size: 200 })
      const last = data.items.at(-1)
      if (last?.role === 'assistant' && data.items.at(-2)?.content === question) message.id = last.id
      else { messages.value.splice(-2, 2); await onSend(question); return }
    } catch (_) { return }
  }
  await onSend(question, message)
}

async function onSend(question, retryMessage = null) {
  // 并发保护：流进行中直接拒绝（双 Enter/连点场景）
  if (!modelsReady.value || isStreaming.value || isLoadingMessages.value) return
  streamingSessionId.value = '' // 先占位，防 createSession 网络窗口期重复进入

  try {
    // 未选择会话时自动创建
    if (!sessionStore.currentId) {
      await sessionStore.createSession()
    }
    const sessionId = sessionStore.currentId
    displayedSessionId = sessionId
    streamingSessionId.value = sessionId

    const userMsg = reactive({ _key: `local-${++localMessageId}`, role: 'user', content: question, status: 'completed' })
    const assistantMsg = reactive({
      _key: `local-${++localMessageId}`,
      role: 'assistant',
      content: '',
      reasoning_content: '',
      status: 'generating',
      citations: [],
      feedback: null,
    })
    if (retryMessage) {
      assistantMsg.id = retryMessage.id
      messages.value.splice(-1, 1, assistantMsg)
    } else messages.value.push(userMsg, assistantMsg)
    scrollToBottom()

    const stopStreaming = () => {
      currentStreamAbort?.()
      assistantMsg.status = assistantMsg.content ? 'stopped' : 'failed'
      assistantMsg.error_message = '已停止生成'
    }
    assistantMsg._stop = stopStreaming
    const applyEvent = (ev) => {
        if (ev.event === 'start') {
          assistantMsg.id = ev.data?.message_id
        } else if (ev.event === 'citations') {
          assistantMsg.citations = ev.data?.citations || []
          assistantMsg.answer_mode = ev.data?.answer_mode || (assistantMsg.citations.length ? 'knowledge' : 'general')
        } else if (ev.event === 'token') {
          assistantMsg.content += ev.data?.content || ''
          scrollToBottom(false)
        } else if (ev.event === 'reasoning') {
          assistantMsg.reasoning_content += ev.data?.content || ''
          scrollToBottom(false)
        } else if (ev.event === 'done') {
          assistantMsg.id = ev.data?.message_id
          assistantMsg.status = assistantMsg.content.trim() ? 'completed' : 'failed'
          if (assistantMsg.status === 'failed') assistantMsg.error_message = '模型没有返回回答正文，请重试或检查模型的输出长度设置。'
          assistantMsg.citations_count = assistantMsg.citations.length
        } else if (ev.event === 'error') {
          assistantMsg.status = 'failed'
          assistantMsg.error_message = ev.data?.message || '生成失败'
        }
    }
    const { abort, promise } = chatApi.stream(sessionId, question, applyEvent, retryMessage?.id)
    currentStreamAbort = abort
    try {
      await promise
      if (assistantMsg.status === 'generating') {
        assistantMsg.status = 'failed'
        assistantMsg.error_message = '回答连接已中断，请重试。'
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        assistantMsg.status = assistantMsg.content ? 'stopped' : 'failed'
      } else {
        assistantMsg.status = 'failed'
        assistantMsg.error_message = err.message || '生成失败'
      }
    } finally {
      streamingSessionId.value = null
      currentStreamAbort = null
      // 标题可能已被后端自动生成，刷新会话列表
      sessionStore.fetchSessions().catch(() => {})
    }
  } catch (_) {
    streamingSessionId.value = null
    currentStreamAbort = null
  }
}

async function onFeedback(message, rating) {
  if (message.feedback === rating) {
    await chatApi.removeFeedback(message.id)
    message.feedback = null
  } else {
    await chatApi.feedback(message.id, { rating })
    message.feedback = rating
  }
}

function onCommand(command) {
  if (command === 'logout') {
    auth.logout()
    router.push('/login')
  } else if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'space') {
    router.push('/space/library')
  } else if (command === 'models') {
    router.push('/space/models')
  }
}

function scrollToBottom(smooth = true) {
  if (scrollFrame) return
  scrollFrame = requestAnimationFrame(() => {
    scrollFrame = 0
    messageListRef.value?.scrollToBottom(smooth)
  })
}

function stopCurrentStream() {
  const message = messages.value.at(-1)
  if (message?._stop) message._stop()
  else currentStreamAbort?.()
}

onBeforeUnmount(() => { historyInitController?.abort(); currentStreamAbort?.(); if (scrollFrame) cancelAnimationFrame(scrollFrame); loadSeq++ })
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100dvh;
  background: var(--canvas);
  overflow: hidden;
}
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
.chat-header {
  min-height: 76px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}
.header-left { display: flex; align-items: center; gap: 14px; min-width: 0; }.header-left h1 { font-size: 13px; font-weight: 550; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }.workspace-label { color: var(--muted); font-size: 12px; white-space: nowrap; }.header-slash { color: #bbc6b7; }.header-right { display: flex; align-items: center; gap: 22px; flex-shrink: 0; }.scope-pill { display: flex; align-items: center; gap: 7px; color: var(--muted); font-size: 11px; }.scope-pill>span { width: 5px; height: 5px; border-radius: 50%; background: #5e8a55; }
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--ink);
  font-size: 12px;
  background: transparent;
  border: 0;
  padding: 6px;
  border-radius: 8px;
}
.user-chip:hover { background: #e9ede4; }.user-chip .el-avatar { background: #e2e9d9; color: #46653d; font-size: 12px; }.mobile-menu { display: none; }
@media (max-width: 800px) { .chat-header { min-height: 62px; padding: 0 15px; }.mobile-menu { display: flex; }.workspace-label,.header-slash,.scope-pill,.user-name { display: none; }.header-right { gap: 0; }.header-left { gap: 10px; } }
</style>
