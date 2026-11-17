<template>
  <div class="chat-input-wrap">
    <form class="chat-input-box" @submit.prevent="send">
      <el-input
        v-model="text"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        resize="none"
        name="question"
        aria-label="向知库提问"
        autocomplete="off"
        placeholder="问问知识库，或直接聊聊…"
        @keydown="onKeyDown"
      />
      <div class="input-footer">
        <span class="hint"><el-icon aria-hidden="true"><Connection /></el-icon><span>自动结合相关知识</span></span>
        <div class="composer-actions"><span class="keyboard-hint"><kbd>Enter</kbd> 发送<span> · Shift + Enter 换行</span></span>
        <button v-if="streaming" type="button" class="send-button stop-button" aria-label="停止生成" @click="$emit('stop')"><span class="stop-square" aria-hidden="true"></span></button>
        <button v-else type="submit" class="send-button" :disabled="disabled || !text.trim()" aria-label="发送问题"><el-icon aria-hidden="true"><Top /></el-icon></button></div>
      </div>
    </form>
    <p class="composer-note">相关问题结合知识库，无关问题直接回答。重要信息请核实。</p>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Connection, Top } from '@element-plus/icons-vue'

const props = defineProps({ disabled: { type: Boolean, default: false }, streaming: Boolean })
const emit = defineEmits(['send', 'stop'])

const text = ref('')

function send() {
  const question = text.value.trim()
  if (!question || props.disabled) return
  emit('send', question)
  text.value = ''
}

/** 中文输入法组词回车（isComposing）不触发发送 */
function onKeyDown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  send()
}
</script>

<style scoped>
.chat-input-wrap {
  padding: 8px max(30px,calc((100% - 820px) / 2)) max(14px,env(safe-area-inset-bottom));
  flex-shrink: 0;
}
.chat-input-box {
  background: #fff;
  border: 1px solid #d7dfcf;
  border-radius: 16px;
  padding: 16px 18px 12px;
  box-shadow: 0 4px 20px #28442406;
  transition: border-color .2s, box-shadow .2s;
}
.chat-input-box:focus-within { border-color: #8fae79; box-shadow: 0 0 0 3px #a9c78520,0 5px 25px #28442408; }
.chat-input-box :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 1px 0;
  font-size: 13px;
  line-height: 1.8;
  color: var(--ink);
  background: transparent;
}
.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}
.hint { display: flex; gap: 6px; align-items: center; font-size: 10px; color: #718067; }.hint .el-icon { font-size: 13px; }.composer-actions { display: flex; align-items: center; gap: 14px; }.keyboard-hint { font-size: 9px; color: #7b8672; }kbd { font: inherit; }.send-button { display: grid; place-items: center; width: 33px; height: 33px; border: 0; border-radius: 9px; background: var(--accent); color: #fff; font-size: 17px; transition: transform .18s, background-color .18s; }.send-button:hover:not(:disabled) { background: #0b4836; transform: translateY(-2px); }.send-button:active { transform: scale(.94); }.send-button:disabled { background: #e8ede2; color: #809174; }.stop-square { width: 10px; height: 10px; background: currentColor; border-radius: 2px; }.composer-note { font-size: 9px; color: #7c8675; text-align: center; margin-top: 12px; }
@media (max-width: 800px) { .chat-input-wrap { padding: 6px 16px max(12px,env(safe-area-inset-bottom)); }.keyboard-hint { display: none; }.chat-input-box { padding: 13px 14px 10px; }.composer-note { font-size: 9px; } }
@media (pointer: coarse) { .send-button { width: 42px; height: 42px; } }
</style>
