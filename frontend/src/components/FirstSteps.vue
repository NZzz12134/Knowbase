<template>
  <section v-if="status && (!status.personal_models || !status.ready)" class="first-steps" aria-label="开始使用知库">
    <div><span class="eyebrow">GET STARTED</span><h2>{{ !status.personal_models ? '按需连接你的模型' : status.processing ? '资料正在变成可检索的知识' : status.failed ? '还有一步，让资料准备就绪' : '从你的第一份资料开始' }}</h2><p>{{ !status.personal_models ? '可以先浏览会话、创建知识库或管理账号。准备聊天或解析资料时，再连接自己的 API 或本地 Ollama 模型。' : status.processing ? '解析完成后，就可以围绕资料提问。现在也可以直接聊聊，任务会在后台继续。' : status.failed ? '部分文档解析失败，可在我的文档中查看原因并重试。也可以先直接聊天。' : '可以直接聊天，或创建知识库、上传资料，让相关问题的回答更有依据。资料仅自己可见。' }}</p></div>
    <ol v-if="status.personal_models" class="setup-steps"><li :class="{ done: status.personal_models }"><span>1</span>配置我的模型</li><li :class="{ done: status.ready }"><span>2</span>创建知识库并上传资料</li><li><span>3</span>开始提问</li></ol>
    <div class="setup-actions"><template v-if="!status.personal_models"><RouterLink class="setup-link" :to="{ path: '/space/models', query: { setup: '1' } }">配置我的模型 ↗</RouterLink><RouterLink to="/space/library">先浏览知识空间 ↗</RouterLink></template><template v-else><RouterLink class="setup-link" :to="status.knowledge_bases ? '/space/documents' : '/space/library'">{{ status.failed ? '查看失败文档' : status.knowledge_bases ? '上传我的资料' : '创建我的知识库' }} ↗</RouterLink><el-button v-if="!status.documents" :loading="busy" @click="trySample">先体验示例资料</el-button><RouterLink to="/space/models">我的模型</RouterLink><el-button v-if="status.processing" link @click="refresh">刷新进度</el-button></template></div>
    <p v-if="error" role="alert" class="setup-error">{{ error }} <el-button link @click="refresh">重新检查</el-button></p>
  </section>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { kbApi, documentApi } from '../api/admin'
import { personalApi } from '../api/personal'
const emit = defineEmits(['ready', 'models-ready'])
const status = ref(null), busy = ref(false), error = ref('')
let timer, disposed = false
async function refresh() {
  clearTimeout(timer)
  try { const data = await personalApi.onboarding(); if (disposed) return; status.value = data; error.value = ''; emit('models-ready', !!data.personal_models); if (data.ready && data.personal_models) emit('ready') }
  catch (_) { status.value ||= { knowledge_bases: 0, documents: 0, ready: 0 }; error.value = '暂时无法读取资料进度，请稍后重试。' }
  if (!disposed && status.value?.processing) timer = setTimeout(refresh, 5000)
}
async function trySample() {
  if (busy.value) return
  busy.value = true
  try {
    const kbs = await kbApi.list()
    const kb = kbs[0] || await kbApi.create({ name: '我的第一份知识', description: '个人知识库使用示例' })
    const file = new File(['知库使用指南\n\n知库支持 PDF、Word、Excel、CSV、Markdown 和 TXT。单份文档最大为 50MB。\n上传后会自动解析，解析成功即可提问。\n回答中的引用可以打开原文，帮助核对事实。\n个人模型可使用云端 API 或后端可访问的 Ollama，本地地址指运行后端的机器。\n'], '知库使用指南.txt', { type: 'text/plain' })
    await documentApi.upload(kb.id, file)
    await refresh()
  } catch (_) { await refresh(); error.value = '示例资料导入未完成，请到我的文档查看状态；失败任务可重试。' }
  finally { busy.value = false }
}
onMounted(refresh)
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
</script>
<style scoped>
.first-steps { flex-shrink: 0; margin: 20px 30px 0; padding: 22px 25px; border: 1px solid #d6e2cc; background: #edf3e6; border-radius: 14px; }.first-steps h2 { margin-top: 8px; font-size: 19px; }.first-steps p { margin-top: 8px; color: var(--muted); line-height: 1.7; font-size: 12px; }.setup-steps { display: flex; gap: 25px; flex-wrap: wrap; list-style: none; margin: 18px 0; }.setup-steps li { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--muted); }.setup-steps li>span { border: 1px solid #c4d2ba; border-radius: 50%; width: 23px; height: 23px; display: grid; place-items: center; }.setup-steps .done { color: var(--accent); }.done>span { background: var(--accent); color: #fff; }.setup-actions { margin-top: 16px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; font-size: 12px; }.setup-link { background: var(--accent); color: #fff; border-radius: 8px; padding: 10px 14px; }.setup-error { color: var(--el-color-danger); }@media(max-width:800px) { .first-steps { margin: 12px 16px 0; padding: 16px; }.setup-steps { gap: 12px; }.first-steps h2 { font-size: 17px; } }
</style>
