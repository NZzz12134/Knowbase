<template>
  <div class="message-item">
    <div v-if="message.role === 'user'" class="bubble user-bubble">{{ message.content }}</div>

    <div v-else class="assistant-block">
      <div class="bubble assistant-bubble">
        <p v-if="message.answer_mode" class="answer-source">{{ message.answer_mode === 'knowledge' ? '结合知识库回答' : '模型直接回答' }}</p>
        <CitationCard
          v-if="message.citations?.length"
          :citations="message.citations"
          style="margin-bottom: 10px"
        />
        <!-- 历史消息的引用：按需拉取详情 -->
        <button
          v-if="!message.citations?.length && (message.citations_count || 0) > 0"
          class="citation-hint"
          type="button"
          @click="loadHistoryCitations"
        >
          <el-icon><Document /></el-icon>
          引用 {{ message.citations_count }} 个知识库片段
          <el-icon v-if="historyLoading" class="is-loading"><Loading /></el-icon>
        </button>
        <!-- 生成中状态提示：检索中 → 生成中 → 流式输出 -->
        <div v-if="message.status === 'generating' && !message.content" class="thinking-tip">
          <el-icon class="is-loading"><Loading /></el-icon>
          <template v-if="message.citations?.length">
            已找到 {{ message.citations.length }} 个相关片段，正在生成回答…
          </template>
          <template v-else-if="message.answer_mode === 'general'">正在生成回答…</template>
          <template v-else>
            正在检索知识库…
          </template>
        </div>
        <div
          v-else-if="message.content"
          class="markdown-body"
          :class="{ 'streaming-cursor': streaming && message.status === 'generating' }"
          v-html="renderMarkdown(message.content)"
        ></div>
        <div v-if="message.status === 'failed'" class="error-tip">
          <el-icon><WarningFilled /></el-icon>
          {{ message.error_message || '生成失败，请重试' }}
        </div>
        <div v-if="message.status === 'stopped' && message.content" class="stopped-tip">
          已停止生成
        </div>
      </div>

      <div v-if="message.status !== 'generating'" class="actions">
        <el-button v-if="canRetry" link type="primary" @click="$emit('retry')">{{ message.status === 'failed' ? '重试回答' : '重新生成' }}</el-button>
        <button v-if="message.content" class="copy-action" :aria-label="copied ? '已复制回答' : '复制回答'" @click="copyAnswer"><el-icon aria-hidden="true"><Check v-if="copied" /><CopyDocument v-else /></el-icon><span>{{ copied ? '已复制' : '复制' }}</span></button>
        <template v-if="message.id && message.status === 'completed'">
        <el-button
          link
          size="small"
          :type="message.feedback === 'like' ? 'primary' : 'info'"
          :aria-pressed="message.feedback === 'like'"
          @click="$emit('feedback', 'like')"
        >
          <el-icon><CaretTop /></el-icon> 有帮助
        </el-button>
        <el-button
          link
          size="small"
          :type="message.feedback === 'dislike' ? 'danger' : 'info'"
          :aria-pressed="message.feedback === 'dislike'"
          @click="$emit('feedback', 'dislike')"
        >
          <el-icon><CaretBottom /></el-icon> 无帮助
        </el-button>
        </template>
        <el-button v-if="message._stop && streaming" link size="small" type="danger" @click="message._stop()">
          停止生成
        </el-button>
      </div>

      <!-- 历史引用详情弹窗 -->
      <el-dialog v-model="historyDialogVisible" title="引用片段详情" width="640px">
        <div v-loading="historyLoading">
          <div v-for="(c, idx) in historyCitations" :key="c.chunk_id" class="history-cite">
            <div class="cite-meta">
              <span class="citation-badge">{{ idx + 1 }}</span>
              {{ c.filename || '未知来源' }}
              <template v-if="c.page"> · 第 {{ c.page }} 页</template>
              <template v-else-if="c.row_start"> · 第 {{ c.row_start }}-{{ c.row_end }} 行</template>
              <template v-if="c.heading_path"> · {{ c.heading_path }}</template>
            </div>
            <div class="cite-text">{{ c.text }}</div>
            <el-button v-if="c.document_id" link type="primary" @click="originalPreview.open(c)">查看原文{{ c.page ? ` · 第 ${c.page} 页` : '' }}</el-button>
          </div>
          <el-empty v-if="!historyLoading && !historyCitations.length" description="暂无引用" />
        </div>
      </el-dialog>
      <DocumentPreview ref="originalPreview" />
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CaretBottom, CaretTop, Check, CopyDocument, Document, Loading, WarningFilled } from '@element-plus/icons-vue'
import { chatApi } from '../../api/chat'
import { renderMarkdown } from '../../utils/markdown'
import CitationCard from './CitationCard.vue'
import DocumentPreview from '../DocumentPreview.vue'
const originalPreview = ref(null)

const props = defineProps({
  message: { type: Object, required: true },
  streaming: { type: Boolean, default: false },
  canRetry: Boolean,
})
defineEmits(['feedback', 'retry'])

const historyDialogVisible = ref(false)
const historyLoading = ref(false)
const historyCitations = ref([])
const copied = ref(false)
let copyTimer
async function copyAnswer() {
  try { await navigator.clipboard.writeText(props.message.content); copied.value = true; clearTimeout(copyTimer); copyTimer = setTimeout(() => { copied.value = false }, 1800) }
  catch { ElMessage.warning('复制未完成，请选中文字后复制。') }
}
onBeforeUnmount(() => clearTimeout(copyTimer))

async function loadHistoryCitations() {
  if (!props.message.id) return
  historyDialogVisible.value = true
  historyLoading.value = true
  try {
    historyCitations.value = await chatApi.citations(props.message.id)
  } catch (_) {
    /* 拦截器已提示 */
    historyCitations.value = []
  } finally {
    historyLoading.value = false
  }
}
</script>

<style scoped>
.message-item { width: 100%; min-width: 0; }.user .message-item { max-width: 85%; width: auto; }
.bubble {
  padding: 17px 21px;
  border-radius: 14px;
  font-size: 13px;
  line-height: 1.7;
}
.user-bubble {
  background: #e8eede;
  color: #2b4331;
  border-radius: 14px 3px 14px 14px;
  white-space: pre-wrap;
  word-break: break-word;
}
.assistant-block { width: 100%; }
.answer-source { font-size: 11px; color: var(--muted); margin-bottom: 10px; }
.assistant-bubble {
  background: #fff;
  color: var(--ink);
  border: 1px solid #e3e9dc;
  word-break: break-word;
  min-width: 0;
  border-radius: 3px 14px 14px 14px;
}
.thinking-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 12px;
  padding: 4px 0;
}
.citation-hint {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  cursor: pointer;
  background: #edf3e7;
  border: 1px solid #dbe5d1;
  color: var(--accent);
  border-radius: 6px;
  padding: 7px 10px;
  margin-bottom: 10px;
}
.citation-hint:hover { background: #e0e9d6; }
.actions { margin-top: 7px; padding-left: 4px; display: flex; align-items: center; gap: 5px; }.actions :deep(.el-button) { font-size: 10px; padding: 3px 6px; }.copy-action { background: transparent; border: 0; display: inline-flex; gap: 5px; align-items: center; color: var(--muted); font-size: 10px; border-radius: 5px; padding: 8px 6px; }.copy-action:hover { color: var(--accent); background: #e9eee2; }
.error-tip {
  color: var(--el-color-danger);
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
}
.stopped-tip { color: #909399; font-size: 13px; margin-top: 8px; }
.history-cite { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
.cite-meta { font-size: 12px; color: #909399; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.citation-badge {
  width: 18px;
  height: 18px;
  min-width: 18px;
  background: var(--accent);
  color: #fff;
  border-radius: 50%;
  font-size: 11px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.cite-text { font-size: 13px; color: #303133; white-space: pre-wrap; word-break: break-word; }
</style>
