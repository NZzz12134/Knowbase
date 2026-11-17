<template>
  <div class="admin-page">
    <div class="page-header">
      <div><span class="eyebrow">DOCUMENT COLLECTION</span><h1>让文档成为知识</h1><p>上传、解析与检索，在这里连接每一份内容。</p></div>
      <div class="header-actions">
        <el-select v-model="filterKb" aria-label="按知识库筛选" placeholder="全部知识库" clearable style="width: 180px" @change="onFilterKbChange">
          <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
        </el-select>
        <el-select v-model="filterStatus" aria-label="按解析状态筛选" placeholder="全部状态" clearable style="width: 140px" @change="onFilterChange">
          <el-option label="待解析" value="pending" />
          <el-option label="解析中" value="parsing" />
          <el-option label="解析成功" value="succeeded" />
          <el-option label="解析失败" value="failed" />
        </el-select>
        <el-input
          v-model="filterKeyword"
          placeholder="搜索文件名…"
          aria-label="搜索文件名"
          name="document-search"
          autocomplete="off"
          clearable
          style="width: 200px"
          @keyup.enter="onFilterChange"
          @clear="onFilterChange"
        >
          <template #append>
            <el-button aria-label="搜索文档" @click="onFilterChange"><el-icon aria-hidden="true"><Search /></el-icon></el-button>
          </template>
        </el-input>
        <el-upload
          :show-file-list="false"
          :http-request="onUpload"
          :disabled="!uploadKb || !modelsReady"
          accept=".pdf,.docx,.xlsx,.csv,.md,.markdown,.txt"
        >
          <el-button type="primary" :disabled="!uploadKb || !modelsReady">
            <el-icon><Upload /></el-icon>&nbsp;上传文档
          </el-button>
        </el-upload>
        <el-button @click="openUrlDialog" :disabled="!uploadKb || !modelsReady">
          <el-icon><Link /></el-icon>&nbsp;抓取网页
        </el-button>
      </div>
    </div>

    <div class="upload-tip">
      <span>上传目标知识库：</span>
      <el-select v-model="uploadKb" aria-label="上传目标知识库" placeholder="选择知识库…" size="small" style="width: 200px" @change="onUploadKbChange">
        <el-option v-for="k in kbs" :key="k.id" :label="k.name" :value="k.id" />
      </el-select>
      <span class="tip-text">支持 pdf / docx / xlsx / csv / md / txt，单文件 ≤ 50MB；切换后下方列表同步过滤</span>
      <el-button link type="primary" @click="createKnowledgeBase">新建知识库</el-button>
    </div>
    <el-alert v-if="!kbs.length && !loading" title="先创建一个知识库，再上传你的第一份资料。" type="info" :closable="false" style="margin-bottom:16px"><el-button type="primary" @click="createKnowledgeBase">创建我的知识库</el-button></el-alert>
    <el-alert v-if="modelsChecked && !modelsReady" title="请先配置自己的对话和 Embedding 模型，再上传或解析资料。" type="info" :closable="false" style="margin-bottom:16px"><RouterLink :to="{ path: '/space/models', query: { setup: '1' } }">配置我的模型 ↗</RouterLink></el-alert>
    <div v-if="failedUploads.length" class="upload-failures" role="status"><div v-for="item in failedUploads" :key="item.key"><span>{{ item.file.name }}：{{ item.error }}</span><el-button link :loading="item.busy" @click="retryUpload(item)">重新上传</el-button><el-button link @click="failedUploads = failedUploads.filter(x => x !== item)">移除</el-button></div></div>
    <div v-if="docs.some(d => d.parse_status === 'succeeded')" class="ready-banner"><span>资料已准备好，可以开始提问。</span><el-button type="primary" @click="startAsking">围绕这些资料提问 ↗</el-button></div>

    <el-table :data="docs" v-loading="loading" empty-text="当前没有匹配的文档。上传一份文档，开始构建知识。">
      <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <el-link v-if="row.file_type === 'url'" :href="row.source_url" target="_blank" type="primary">
            {{ row.filename }}
          </el-link>
          <span v-else>{{ row.filename }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="file_type" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.file_type.toUpperCase() }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="90" align="center">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column label="解析状态" width="140" align="center">
        <template #default="{ row }">
          <el-tag :type="statusType(row.parse_status)" size="small">
            {{ statusLabel(row.parse_status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度 / 分块" width="120" align="center">
        <template #default="{ row }">
          <el-progress
            v-if="row.parse_status === 'parsing'"
            :percentage="row.parse_progress"
            :stroke-width="8"
          />
          <span v-else-if="row.parse_status === 'succeeded'">{{ row.chunk_count }} 块</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="错误信息" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">
          <el-tooltip v-if="row.error_message" :content="row.error_message" placement="top">
            <span style="color: var(--el-color-danger); font-size: 12px">{{ row.error_message }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="160">
        <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="310" align="center">
        <template #default="{ row }">
          <el-button link type="primary" @click="originalPreview.open(row)">查看原文</el-button>
          <el-button v-if="row.parse_status === 'succeeded'" link type="primary" @click="showChunks(row)">
            分块预览
          </el-button>
          <el-button
            v-if="['succeeded', 'failed'].includes(row.parse_status)"
            link
            type="primary"
            @click="onReparse(row)"
          >
            重新解析
          </el-button>
          <el-button v-if="row.parse_status === 'failed'" link type="warning" @click="onRetry(row)">
            重试
          </el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 16px; justify-content: flex-end"
      @current-change="fetchList"
    />

    <el-dialog v-model="urlDialog" title="抓取网页" width="480px">
      <el-form label-width="70px">
        <el-form-item label="URL" required>
          <el-input v-model="urlInput" type="url" name="source-url" aria-label="网页地址" autocomplete="off" placeholder="https://example.com/article…" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="urlDialog = false">取消</el-button>
        <el-button type="primary" @click="submitUrl">开始抓取</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="chunkDialog" :title="`分块预览 - ${chunkDoc?.filename || ''}`" width="720px">
      <el-pagination
        v-model:current-page="chunkPage"
        :page-size="10"
        :total="chunkTotal"
        layout="total, prev, pager, next"
        small
        style="margin-bottom: 10px"
        @current-change="loadChunks"
      />
      <div v-for="c in chunks" :key="c.id" class="chunk-item">
        <div class="chunk-meta">
          #{{ c.seq }}
          <template v-if="c.page_number"> · 第 {{ c.page_number }} 页</template>
          <template v-if="c.row_start"> · 第 {{ c.row_start }}-{{ c.row_end }} 行</template>
          <template v-if="c.heading_path"> · {{ c.heading_path }}</template>
        </div>
        <div class="chunk-content">{{ c.content }}</div>
      </div>
    </el-dialog>
    <DocumentPreview ref="originalPreview" />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Link, Search, Upload } from '@element-plus/icons-vue'
import { documentApi, kbApi } from '../../api/admin'
import { personalApi } from '../../api/personal'
import { useRoute, useRouter } from 'vue-router'
import { useSessionStore } from '../../stores/session'
import DocumentPreview from '../../components/DocumentPreview.vue'
const route = useRoute(), router = useRouter()
const originalPreview = ref(null), failedUploads = ref([])
let uploadCounter = 0
async function createKnowledgeBase() {
  try {
    const { value } = await ElMessageBox.prompt('为你的资料起一个名字。', '新建知识库', { inputPlaceholder: '例如：学习笔记…', inputValidator: value => !!value?.trim() && value.trim().length <= 100 || '请输入 1–100 个字的名称', confirmButtonText: '创建', cancelButtonText: '取消' })
    const kb = await kbApi.create({ name: value.trim() }); kbs.value = await kbApi.all(); uploadKb.value = kb.id; filterKb.value = kb.id; page.value = 1; await fetchList()
  } catch (_) {}
}
async function startAsking() { await useSessionStore().createSession(undefined, filterKb.value || null); await router.push('/') }

const kbs = ref([])
const modelsReady = ref(false), modelsChecked = ref(false)
const docs = ref([])
const loading = ref(false)
const page = ref(1)
const pageSize = 20
const total = ref(0)
const filterKb = ref(null)
const filterStatus = ref(null)
const filterKeyword = ref('')
const uploadKb = ref(null)

const urlDialog = ref(false)
const urlInput = ref('')

const chunkDialog = ref(false)
const chunkDoc = ref(null)
const chunks = ref([])
const chunkPage = ref(1)
const chunkTotal = ref(0)

let pollTimer = null
let disposed = false, listRequest = 0

function statusType(status) {
  return { pending: 'info', parsing: 'warning', succeeded: 'success', failed: 'danger' }[status]
}
function statusLabel(status) {
  return { pending: '待解析', parsing: '解析中', succeeded: '解析成功', failed: '解析失败' }[status]
}
function formatSize(bytes) {
  if (bytes == null) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
function formatTime(t) {
  if (!t) return '—'
  const date = new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(t) ? t : `${t}Z`)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

/** 上传目标知识库变更：列表过滤双向联动（上传目标和列表过滤始终一致，避免传错库） */
function onUploadKbChange(val) {
  filterKb.value = val
  page.value = 1
  fetchList()
}

/** 列表过滤变更：同步上传目标 + 重置页码 */
function onFilterKbChange(val) {
  uploadKb.value = val
  page.value = 1
  fetchList()
}

/** 状态/关键词过滤变更：重置页码（防止停在越界页显示空表） */
function onFilterChange() {
  page.value = 1
  fetchList()
}

async function fetchList() {
  const sequence = ++listRequest
  loading.value = true
  try {
    const data = await documentApi.list({
      page: page.value,
      page_size: pageSize,
      kb_id: filterKb.value || undefined,
      status: filterStatus.value || undefined,
      keyword: filterKeyword.value || undefined,
    })
    if (disposed || sequence !== listRequest) return
    docs.value = data.items
    total.value = data.total
    // 有解析中的任务则 3s 轮询
    const hasActive = data.items.some((d) => ['pending', 'parsing'].includes(d.parse_status))
    if (hasActive && !pollTimer) {
      pollTimer = setInterval(fetchList, 3000)
    } else if (!hasActive && pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } catch (_) {
    if (disposed || sequence !== listRequest) return
    // Stop polling on an error and let the user retry.
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } finally {
    if (!disposed && sequence === listRequest) loading.value = false
  }
}

async function onUpload({ file }, existing = null) {
  if (!uploadKb.value) {
    ElMessage.warning('请先选择目标知识库')
    return
  }
  const targetKb = existing?.kbId || uploadKb.value
  try {
    await documentApi.upload(targetKb, file)
    if (existing) failedUploads.value = failedUploads.value.filter(item => item !== existing)
    ElMessage.success('上传成功，后台解析中')
  } catch (err) {
    const detail = err.response?.data?.detail
    if (detail?.code !== 'enqueue_failed') {
      const message = detail?.message || '上传未完成，请检查网络后重试。'
      if (existing) existing.error = message
      else failedUploads.value.push({ key: ++uploadCounter, file, kbId: targetKb, error: message, busy: false })
    }
  } finally { await fetchList() }
}
async function retryUpload(item) { if (item.busy) return; item.busy = true; try { await onUpload({ file: item.file }, item) } finally { item.busy = false } }

async function openUrlDialog() {
  urlInput.value = ''
  urlDialog.value = true
}

async function submitUrl() {
  if (!urlInput.value.startsWith('http')) {
    ElMessage.warning('请输入合法的 http(s) 链接')
    return
  }
  if (!uploadKb.value) {
    ElMessage.warning('请先选择目标知识库')
    return
  }
  try {
    await documentApi.createUrl(uploadKb.value, urlInput.value)
    ElMessage.success('已提交抓取任务')
    urlDialog.value = false
    fetchList()
  } catch (_) {
    /* 拦截器已提示 */
  }
}

async function onReparse(row) {
  try {
    await documentApi.reparse(row.id)
    ElMessage.success('已重新提交解析')
    fetchList()
  } catch (_) {
    /* 拦截器已提示 */
  }
}

async function onRetry(row) {
  try {
    await documentApi.retry(row.id)
    ElMessage.success('已重试')
    fetchList()
  } catch (_) {
    /* 拦截器已提示 */
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除「${row.filename}」吗？其分块与向量索引将一并删除。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await documentApi.remove(row.id)
    ElMessage.success('已删除')
    fetchList()
  } catch (_) { /* ignore */ }
}

async function showChunks(row) {
  chunkDoc.value = row
  chunkPage.value = 1
  chunkDialog.value = true
  await loadChunks()
}

async function loadChunks() {
  const data = await documentApi.chunks(chunkDoc.value.id, { page: chunkPage.value, page_size: 10 })
  chunks.value = data.items
  chunkTotal.value = data.total
}

onMounted(async () => {
  personalApi.onboarding().then(data => { modelsReady.value = !!data.personal_models; modelsChecked.value = true }).catch(() => {})
  kbs.value = await kbApi.all()
  if (kbs.value.length) {
    uploadKb.value = kbs.value.find(k => k.id === route.query.kb)?.id || kbs.value[0].id
    filterKb.value = uploadKb.value
  }
  fetchList()
})

onBeforeUnmount(() => {
  disposed = true
  listRequest++
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 10px;
}
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.upload-tip {
  margin-bottom: 14px;
  font-size: 13px;
  color: #606266;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tip-text { color: #909399; font-size: 12px; }
.chunk-item { border: 1px solid #e4e7ed; border-radius: 8px; padding: 10px 12px; margin-bottom: 8px; }
.chunk-meta { font-size: 12px; color: #909399; margin-bottom: 6px; }
.chunk-content { font-size: 13px; color: #303133; white-space: pre-wrap; word-break: break-word; }
.upload-failures { padding: 14px; background: #fff1ed; border: 1px solid #edccc2; border-radius: 10px; margin-bottom: 16px; }.upload-failures>div { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 12px; }.ready-banner { display: flex; gap: 16px; align-items: center; justify-content: space-between; flex-wrap: wrap; background: var(--accent-soft); padding: 14px 18px; border-radius: 10px; margin-bottom: 18px; font-size: 12px; }
</style>
