<template>
  <el-dialog v-model="visible" :title="document?.filename || '原文预览'" width="1000px" append-to-body @closed="cleanup">
    <div class="preview-toolbar">
      <span>{{ document?.page ? `引用位置：第 ${document.page} 页` : document?.row_start ? `引用位置：第 ${document.row_start} 行` : document?.heading_path || '原文内容' }}</span>
      <el-button v-if="document?.file_type !== 'url'" :loading="downloading" @click="download">下载原文件</el-button>
    </div>
    <blockquote v-if="document?.text" class="source-excerpt">{{ document.text }}</blockquote>
    <div v-loading="loading" class="document-preview" :aria-busy="loading">
      <el-alert v-if="error" :title="error" type="error" :closable="false"><el-button link @click="load">重试预览</el-button></el-alert>
      <iframe v-else-if="pdfUrl" :src="pdfUrl" title="PDF 原文预览" class="pdf-preview"></iframe>
      <template v-else-if="preview">
        <pre class="original-text">{{ preview.text || '暂无可预览的内容，文档可能尚未解析完成。' }}</pre>
        <el-pagination v-if="preview.pages > 1" :current-page="textPage" :page-count="preview.pages" layout="prev, pager, next" @current-change="changePage" />
      </template>
    </div>
    <p class="preview-note">PDF 按引用页打开；Word、表格和文本显示提取的原文。设备不支持 PDF 预览时，可下载查看。</p>
  </el-dialog>
</template>
<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { documentApi } from '../api/admin'
import { personalApi, saveBlob } from '../api/personal'
const visible = ref(false), document = ref(null), loading = ref(false), downloading = ref(false), error = ref(''), pdfUrl = ref(''), preview = ref(null), textPage = ref(1)
let objectUrl = '', generation = 0
function cleanup() { generation++; if (objectUrl) URL.revokeObjectURL(objectUrl); objectUrl = ''; pdfUrl.value = ''; preview.value = null }
async function open(source) { cleanup(); document.value = { ...source }; textPage.value = 1; visible.value = true; await load() }
async function load() {
  const seq = ++generation; loading.value = true; error.value = ''
  try {
    const id = document.value.document_id || document.value.id
    const info = await documentApi.detail(id)
    if (seq !== generation) return
    document.value = { ...info, ...document.value, document_id: id }
    if (info.file_type === 'pdf') {
      const blob = await personalApi.file(id, true)
      if (seq !== generation) return
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      objectUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }))
      pdfUrl.value = `${objectUrl}#page=${Math.max(1, document.value.page || 1)}`
    } else {
      const data = await personalApi.preview(id, textPage.value)
      if (seq === generation) preview.value = data
    }
  } catch (_) { if (seq === generation) error.value = '原文暂时无法打开，请重试或下载原文件。' }
  finally { if (seq === generation) loading.value = false }
}
async function changePage(page) { textPage.value = page; await load() }
async function download() { downloading.value = true; try { saveBlob(await personalApi.file(document.value.document_id || document.value.id), document.value.filename) } catch (_) {} finally { downloading.value = false } }
onBeforeUnmount(cleanup)
defineExpose({ open })
</script>
<style scoped>
.preview-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: var(--muted); margin-bottom: 15px; font-size: 12px; }.source-excerpt { border-left: 3px solid var(--accent); background: var(--accent-soft); padding: 12px 16px; margin-bottom: 16px; max-height: 150px; overflow: auto; white-space: pre-wrap; line-height: 1.8; }.document-preview { min-height: 160px; }.pdf-preview { width: 100%; height: min(65dvh,760px); border: 1px solid var(--line); border-radius: 9px; }.original-text { max-height: 60dvh; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; line-height: 1.9; background: var(--canvas); border-radius: 9px; padding: 18px; }.preview-note { color: var(--muted); font-size: 11px; line-height: 1.8; margin-top: 12px; }
</style>
