<template>
  <div class="conversation-area">
  <p class="sr-only" role="status" aria-live="polite">{{ loading ? '正在加载对话' : streaming ? '知库正在生成回答' : '可以发送问题' }}</p>
  <div ref="containerRef" class="message-list" @scroll.passive="onScroll" :aria-busy="loading">
    <div v-if="loading" class="message-skeleton" role="status" aria-label="正在加载对话">
      <div></div><div></div><div></div><span>正在整理你的对话…</span>
    </div>
    <div v-else-if="!messages.length" class="welcome">
      <div class="welcome-badge"><span></span> YOUR KNOWLEDGE WORKSPACE</div>
      <div class="welcome-icon"><BrandLogo compact :size="58" /></div>
      <h2>好问题，<span>值得好答案。</span></h2>
      <p>问资料时结合知识库，聊其他话题时直接回答。<br />从一个问题开始，探索知识，也交流想法。</p>
      <div class="suggestions">
        <button v-for="(item,index) in suggestions" :key="item.title" class="suggestion-chip" :disabled="disabled" @click="$emit('quickAsk', item.question)">
          <span class="suggestion-top"><el-icon aria-hidden="true"><component :is="item.icon" /></el-icon><span class="suggestion-index">0{{ index + 1 }}</span></span>
          <strong>{{ item.title }}</strong><span class="suggestion-description">{{ item.description }}</span><span class="suggestion-arrow" aria-hidden="true">↗</span>
        </button>
      </div>
      <div class="welcome-note"><el-icon aria-hidden="true"><Connection /></el-icon>可以先直接聊聊，也可以上传资料后提问。</div>
    </div>
    <TransitionGroup v-else name="message" tag="div" class="message-stack">
    <article v-for="(msg, idx) in messages" :key="msg._key || msg.id" class="message-row" :class="msg.role" :aria-label="msg.role === 'user' ? '你的提问' : '知库的回答'">
      <div class="message-byline" :class="msg.role"><BrandLogo v-if="msg.role === 'assistant'" compact :size="24" /><span>{{ msg.role === 'user' ? '你' : '知库' }}</span><span v-if="msg.role === 'assistant'" class="assistant-label">知识助手</span></div>
      <MessageItem
        :message="msg"
        :streaming="streaming && idx === messages.length - 1"
        :can-retry="!disabled && idx === messages.length - 1"
        @retry="$emit('retry', msg)"
        @feedback="(r) => $emit('feedback', msg, r)"
      />
    </article>
    </TransitionGroup>
    <div class="conversation-end" aria-hidden="true"></div>
  </div>
  <Transition name="route"><button v-if="!atBottom && messages.length" class="jump-latest" aria-label="回到最新消息" @click="jumpToLatest"><el-icon aria-hidden="true"><Bottom /></el-icon>最新消息</button></Transition>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import MessageItem from './MessageItem.vue'
import BrandLogo from '../BrandLogo.vue'
import { Bottom, Collection, Connection, Document, Search } from '@element-plus/icons-vue'

const props = defineProps({
  messages: { type: Array, default: () => [] },
  streaming: { type: Boolean, default: false },
  loading: Boolean,
  disabled: Boolean,
})
defineEmits(['feedback', 'quickAsk', 'retry'])

const containerRef = ref(null)
const atBottom = ref(true)
const suggestions = [
  { icon: Collection, title: '快速了解', description: '掌握知识库的核心内容', question: '知识库中有哪些重要内容？' },
  { icon: Search, title: '深入探索', description: '寻找问题背后的具体答案', question: '请介绍知识库中最重要的规则和注意事项。' },
  { icon: Document, title: '提炼要点', description: '把长文档读成清晰的重点', question: '请总结知识库文档的要点，并列出引用来源。' },
]

function scrollToBottom(smooth = true) {
  const el = containerRef.value
  if (!el || !atBottom.value) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth && !window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'smooth' : 'auto' })
}
function onScroll() { const el = containerRef.value; if (el) atBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 110 }
function jumpToLatest() { atBottom.value = true; scrollToBottom(true) }
watch(() => props.loading, (loading) => { if (loading) atBottom.value = true })

defineExpose({ scrollToBottom })

onMounted(() => scrollToBottom(false))
</script>

<style scoped>
.conversation-area { position: relative; flex: 1; min-height: 0; }.message-list { height: 100%; overflow-y: auto; overscroll-behavior: contain; scrollbar-gutter: stable; padding: 32px max(30px,calc((100% - 820px) / 2)); }
.welcome { min-height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: 24px 0 16px; animation: appear .5s var(--ease); }.welcome-badge { display: flex; gap: 8px; align-items: center; color: #7c886e; font-size: 9px; letter-spacing: 2px; margin-bottom: 32px; }.welcome-badge>span { width: 5px; height: 5px; background: #7a965d; border-radius: 50%; }.welcome-icon { margin-bottom: 24px; box-shadow: 0 12px 28px #21453012; border-radius: 18px; display: inline-flex; }.welcome h2 { font-size: clamp(28px,3vw,40px); font-weight: 550; letter-spacing: -1.7px; line-height: 1.4; }.welcome h2>span { color: #78935b; }.welcome>p { font-size: 12px; color: var(--muted); line-height: 2; margin-top: 18px; }
.suggestions { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 12px; margin-top: 36px; width: 100%; max-width: 700px; }.suggestion-chip { position: relative; padding: 19px 19px 23px; text-align: left; background: #fff; border: 1px solid var(--line); border-radius: 12px; transition: transform .22s var(--ease), border-color .22s, box-shadow .22s; color: var(--ink); }.suggestion-chip:hover:not(:disabled) { transform: translateY(-4px); border-color: #a8bd94; box-shadow: 0 10px 20px #23452b09; }.suggestion-chip:active { transform: translateY(-1px); }.suggestion-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; }.suggestion-top>.el-icon { color: #4b7046; font-size: 18px; }.suggestion-index { font-size: 9px; color: #89947f; }.suggestion-chip strong { display: block; font-size: 13px; font-weight: 550; }.suggestion-description { display: block; font-size: 10px; color: #77816f; margin-top: 8px; line-height: 1.6; }.suggestion-arrow { position: absolute; right: 16px; bottom: 18px; font-size: 15px; color: #8c9d7f; }.welcome-note { display: flex; gap: 7px; align-items: center; font-size: 10px; color: #7a8572; margin-top: 30px; }
.message-row { margin-bottom: 32px; content-visibility: auto; contain-intrinsic-size: auto 120px; }.message-row.user { display: flex; flex-direction: column; align-items: flex-end; }.message-byline { display: flex; align-items: center; gap: 8px; font-size: 11px; margin-bottom: 12px; font-weight: 600; }.message-byline.user { color: #77826f; padding-right: 3px; }.assistant-label { font-size: 9px; font-weight: 400; color: #7e8977; border: 1px solid #dce5d5; padding: 2px 5px; border-radius: 4px; }.conversation-end { height: 5px; }.message-enter-active { transition: opacity .28s var(--ease), transform .28s var(--ease); }.message-leave-active { transition: opacity .12s; }.message-enter-from { opacity: 0; transform: translateY(9px); }.message-leave-to { opacity: 0; }.jump-latest { position: absolute; bottom: 18px; left: 50%; transform: translateX(-50%); display: flex; align-items: center; gap: 8px; background: #fff; border: 1px solid var(--line); border-radius: 20px; padding: 8px 14px; box-shadow: 0 3px 15px #173b2010; font-size: 11px; color: var(--accent); }.message-skeleton { max-width: 680px; padding-top: 40px; }.message-skeleton div { background: #e6ebdf; height: 12px; border-radius: 6px; margin-bottom: 16px; animation: skeleton 1.2s ease-in-out 4; }.message-skeleton div:nth-child(2) { width: 85%; }.message-skeleton div:nth-child(3) { width: 60%; }.message-skeleton span { font-size: 11px; color: var(--muted); }@keyframes skeleton { 50% { opacity: .4; } }
@media (max-width: 800px) { .message-list { padding: 22px 18px; }.welcome { padding-top: 10px; }.welcome-badge { margin-bottom: 22px; }.welcome h2 { font-size: 29px; }.suggestions { margin-top: 28px; gap: 8px; }.suggestion-chip { padding: 14px 12px 20px; }.suggestion-top { margin-bottom: 18px; }.suggestion-description { font-size: 10px; }.welcome-note { margin-top: 22px; } }
@media (max-width: 440px) { .welcome h2 { font-size: 26px; }.suggestions { grid-template-columns: 1fr; gap: 8px; }.suggestion-chip { display: grid; grid-template-columns: 26px 1fr; gap: 4px 10px; padding: 13px 16px; }.suggestion-top { margin: 0; grid-row: span 2; }.suggestion-index { display: none; }.suggestion-description { margin: 0; }.suggestion-arrow { bottom: 22px; }.welcome-badge { letter-spacing: 1px; }.welcome-icon { margin-bottom: 16px; } }
</style>
