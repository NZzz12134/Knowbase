<template>
  <div class="markdown-content">
    <div class="markdown-body" :class="{ 'streaming-cursor': streaming }" @click="onCopyCode" v-html="rendered.html"></div>
    <span class="sr-only" role="status" aria-live="polite">{{ copyStatus }}</span>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '../../utils/markdown'
import { copyText } from '../../utils/clipboard'

const props = defineProps({ content: { type: String, default: '' }, streaming: Boolean })
const copiedIndex = ref(-1)
const copyStatus = ref('')
let copyTimer
const rendered = computed(() => {
  const env = { copiedIndex: copiedIndex.value }
  return { html: renderMarkdown(props.content, env), codeBlocks: env.codeBlocks }
})

async function onCopyCode(event) {
  const button = event.target.closest?.('button[data-code-index]')
  if (!button || !event.currentTarget.contains(button)) return
  const index = Number(button.dataset.codeIndex)
  const code = rendered.value.codeBlocks[index]
  if (typeof code !== 'string') return
  const root = event.currentTarget
  const restoreFocus = document.activeElement === button
  try {
    await copyText(code)
    copiedIndex.value = index
    copyStatus.value = '代码已复制'
    await nextTick()
    if (restoreFocus) root.querySelector(`button[data-code-index="${index}"]`)?.focus({ preventScroll: true })
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedIndex.value = -1; copyStatus.value = '' }, 1800)
  } catch (_) {
    ElMessage.warning('复制未完成，请选中代码后复制。')
  }
}
onBeforeUnmount(() => clearTimeout(copyTimer))
</script>

<style scoped>
.markdown-content { min-width: 0; }
:deep(.code-block) { margin: 14px 0; border: 1px solid #dce2e8; border-radius: 10px; overflow: hidden; background: #f6f8fa; }
:deep(.code-block-toolbar) { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 4px 10px; border-bottom: 1px solid #dce2e8; background: #eef2f5; }
:deep(.code-language) { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-left: 8px; font-size: 12px; color: #425466; }
:deep(.code-copy-button) { display: inline-flex; flex-shrink: 0; align-items: center; justify-content: center; min-height: 36px; padding: 4px 10px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: #425466; font-size: 12px; line-height: 1.4; white-space: nowrap; transition: background-color .18s, color .18s; }
:deep(.code-copy-button:hover) { background: #dfe7ed; color: #163b2f; }
:deep(.code-copy-button:focus-visible) { outline: 2px solid var(--accent); outline-offset: -2px; }
:deep(.code-block pre) { margin: 0; border-radius: 0; padding: 18px; }
:deep(.code-block code.hljs) { display: block; padding: 0; background: transparent; overflow: visible; }
:deep(.code-block .hljs-name), :deep(.code-block .hljs-quote), :deep(.code-block .hljs-selector-tag), :deep(.code-block .hljs-selector-pseudo) { color: #1b6b32; }
:deep(.code-block .hljs-built_in), :deep(.code-block .hljs-symbol) { color: #a84600; }
@media (max-width: 600px) { :deep(.code-block pre) { padding: 14px; } }
</style>
