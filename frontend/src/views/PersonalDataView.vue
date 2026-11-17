<template>
  <div class="admin-page data-page">
    <header class="page-header"><div><span class="eyebrow">YOUR DATA, YOUR CONTROL</span><h1>数据与备份</h1><p>把知识随身带走，也能随时重新开始。</p></div></header>
    <el-card shadow="never"><h2>导出我的数据</h2><p>下载 ZIP 备份，包含知识库、上传原文件、聊天 JSON、引用快照和 Markdown 聊天记录。密码与模型密钥不会导出。</p><el-button type="primary" :loading="exporting" :disabled="working" @click="exportData">{{ exporting ? '正在生成备份…' : '下载完整备份' }}</el-button></el-card>
    <el-card shadow="never"><h2>从备份恢复</h2><p>导入知库生成的 ZIP 备份。资料会作为新知识库添加，保留现有数据；原文件会重新解析，请先配置模型。聊天文字会恢复，原引用快照保存在备份 JSON 中，旧引用不与新索引重新关联。备份包及解压后内容均不超过 200MB。</p>
      <input ref="fileInput" type="file" accept=".zip" aria-label="选择知库备份包" :disabled="working" @change="chooseArchive" />
      <el-button :loading="importing" :disabled="working || !archive" @click="importData">恢复选中的备份</el-button>
      <p v-if="importResult" role="status">{{ importResult }}</p>
    </el-card>
    <el-card shadow="never" class="danger-zone"><h2>删除我的全部数据</h2><p>删除所有个人知识库、上传文件、聊天、引用、缓存和个人模型密钥。保留账号，删除后无法撤销。建议先下载备份；解析或生成任务完成后才能删除。</p><el-button type="danger" plain :disabled="working" @click="deleteDialog = true">删除我的全部数据</el-button></el-card>
    <p v-if="error" class="data-error" role="alert">{{ error }}</p>
    <el-dialog v-model="deleteDialog" title="确认删除个人数据" width="460px" :close-on-click-modal="!deleting" :show-close="!deleting" :close-on-press-escape="!deleting">
      <p class="delete-warning">这会永久删除你的资料与聊天，账号仍可登录。</p>
      <el-form label-position="top" @submit.prevent="clearData">
        <el-form-item label="当前密码"><el-input v-model="password" aria-label="当前密码" name="delete-password" type="password" autocomplete="current-password" :disabled="deleting" show-password /></el-form-item>
        <el-form-item label="输入：删除我的全部数据"><el-input v-model="confirmation" aria-label="删除确认文字" name="delete-confirmation" autocomplete="off" :disabled="deleting" /></el-form-item>
        <p v-if="deleteError" role="alert" class="data-error">{{ deleteError }}</p>
        <div class="delete-actions"><el-button :disabled="deleting" @click="deleteDialog = false">取消</el-button><el-button native-type="submit" type="danger" :loading="deleting">永久删除</el-button></div>
      </el-form>
    </el-dialog>
  </div>
</template>
<script setup>
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { personalApi, saveBlob } from '../api/personal'
import { useSessionStore } from '../stores/session'
const exporting = ref(false), importing = ref(false), deleting = ref(false), error = ref(''), importResult = ref(''), archive = ref(null), fileInput = ref(null), deleteDialog = ref(false), password = ref(''), confirmation = ref(''), deleteError = ref('')
const working = computed(() => exporting.value || importing.value || deleting.value)
async function exportData() { exporting.value = true; error.value = ''; try { saveBlob(await personalApi.export(), `knowbase-backup-${new Date().toISOString().slice(0,10)}.zip`) } catch (_) { error.value = '备份生成失败，请稍后重试。' } finally { exporting.value = false } }
function chooseArchive(event) { archive.value = event.target.files[0] || null; importResult.value = '' }
async function importData() {
  if (!archive.value || working.value) return
  try { await ElMessageBox.confirm('备份中的资料将添加到当前账号，并重新解析文档。确认恢复？', '恢复个人备份', { confirmButtonText: '开始恢复', cancelButtonText: '取消' }) } catch (_) { return }
  importing.value = true; error.value = ''
  try { const data = await personalApi.import(archive.value); importResult.value = `已恢复 ${data.knowledge_bases} 个知识库、${data.documents} 份文档和 ${data.sessions} 个会话。${data.queue_failed ? '部分解析任务入队失败，请到我的文档重试。' : '文档正在后台解析。'}`; archive.value = null; fileInput.value.value = ''; useSessionStore().$reset() } catch (_) { error.value = '恢复未完成，请检查备份格式或稍后重试。' } finally { importing.value = false }
}
async function clearData() {
  if (deleting.value) return
  if (!password.value || confirmation.value !== '删除我的全部数据') { deleteError.value = '请填写当前密码，并准确输入确认文字。'; return }
  deleting.value = true; deleteError.value = ''
  try { await personalApi.clear({ password: password.value, confirmation: confirmation.value }); useSessionStore().$reset(); deleteDialog.value = false; password.value = ''; confirmation.value = ''; ElMessage.success('个人数据已删除，账号已保留。') }
  catch (_) { deleteError.value = '删除未完成，请检查密码，或等待正在处理的任务完成后重试。' }
  finally { deleting.value = false }
}
</script>
<style scoped>
.data-page { max-width: 950px; }.data-page .el-card { margin-bottom: 20px; }.data-page h2 { font-size: 18px; margin-bottom: 12px; }.data-page p { font-size: 13px; line-height: 1.9; color: var(--muted); margin-bottom: 20px; }.data-page input[type=file] { display: block; max-width: 100%; margin: 20px 0; font-size: 12px; }.danger-zone { border-color: #e8c8c2; }.danger-zone h2 { color: var(--el-color-danger); }.data-page .data-error { color: var(--el-color-danger); }.delete-warning { line-height: 1.8; margin-bottom: 20px; }.delete-actions { display: flex; justify-content: flex-end; margin-top: 24px; }
</style>
