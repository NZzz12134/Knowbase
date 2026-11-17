<template>
  <div v-loading="loading" class="model-config admin-page">
    <div class="page-header">
      <div>
        <span class="eyebrow">MODEL CONNECTIONS</span>
        <h1>为知识连接智能</h1>
        <p>选择适合你的模型。云端 API、本地 Ollama，灵活组合。</p>
      </div>
      <div class="save-actions"><span v-if="dirty" class="unsaved-indicator" role="status">有未保存的更改</span><el-button type="primary" :loading="saving" :disabled="loading || !ready || !!testing" @click="save">{{ saving ? '正在保存…' : '保存并生效' }}</el-button></div>
    </div>
    <section v-if="ready && !personalSaved" class="setup-guide" aria-label="模型配置引导">
      <span class="eyebrow">WELCOME TO KNOWBASE</span><h2>先连接你的模型</h2>
      <p>这是开始使用的第一步。配置对话和 Embedding 模型后，就能上传资料、开始问答。Rerank 可稍后添加。</p>
      <ol><li>选择云端 API 或本地 Ollama</li><li>填写模型名称、服务地址；API 模式还需填写自己的密钥</li><li>测试连接，点击「保存并生效」</li></ol>
    </section>
    <div class="model-flow"><div v-for="(item,index) in roles" :key="item.key"><span class="model-step">0{{ index + 1 }}</span><div><strong>{{ item.title }}</strong><p>{{ ['理解问题与生成回答', '把文档变成可检索的知识', '把相关的内容排在前面'][index] }}</p></div><span v-if="index < 2" class="flow-arrow" aria-hidden="true">→</span></div></div>
    <el-alert v-if="ready" :title="personalSaved ? '正在使用你的个人模型配置，仅影响你的问答与文档解析。' : '模型配置为空。请填写自己的配置，系统不会提供默认模型或共享密钥。'" :type="personalSaved ? 'success' : 'info'" :closable="false" class="notice"><el-button v-if="personalSaved" link :disabled="saving || !!testing" @click="resetPersonal">清空模型配置</el-button></el-alert>
    <div v-if="setupComplete" class="setup-complete" role="status"><span>模型配置已保存，可以添加你的第一份资料了。</span><RouterLink to="/space/library">下一步：添加我的资料 ↗</RouterLink></div>
    <p class="description">Ollama 地址必须由运行知库后端的机器访问；网站部署在远程服务器时，localhost 指该服务器。</p>
    <el-alert title="保存后，新请求使用最新配置。API Key 加密保存；留空保留原密钥。" type="info" :closable="false" show-icon />
    <el-alert title="更换 Embedding 模型、服务地址或部署方式后，请到文档管理重新解析已有文档，生成匹配的新向量索引。" type="warning" :closable="false" show-icon class="notice" />

    <el-form v-if="ready" label-position="top" :disabled="saving || !!testing">
      <el-card v-for="(item,index) in roles" :key="item.key" class="model-card" shadow="never">
        <template #header>
          <div class="card-header">
            <strong><span class="model-step">0{{ index + 1 }}</span>{{ item.title }}</strong>
            <el-switch v-if="item.key === 'rerank'" v-model="form.rerank_enabled" aria-label="启用重排" active-text="启用重排" />
          </div>
        </template>
        <p class="description">{{ item.description }}</p>
        <p v-if="item.key === 'rerank' && !form.rerank_enabled" class="description">可选功能，默认关闭。先配置对话和 Embedding 模型即可开始使用。</p>
        <div v-if="item.key !== 'rerank' || form.rerank_enabled" class="fields">
          <el-form-item label="部署方式">
            <el-radio-group v-model="form[item.key].mode" :aria-label="`${item.title}部署方式`" @change="changeMode(item.key)">
              <el-radio-button value="api">API 服务</el-radio-button>
              <el-radio-button value="ollama">Ollama 本地</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="item.key === 'rerank' && form.rerank.mode === 'api'" label="API 协议">
            <el-select v-model="form.rerank.protocol" aria-label="重排 API 协议">
              <el-option label="通用 Rerank（/rerank）" value="openai" />
              <el-option label="阿里云 DashScope 原生" value="dashscope" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型名称" required>
            <el-input v-model="form[item.key].model" :name="`${item.key}-model`" :aria-label="`${item.title}名称`" autocomplete="off" :spellcheck="false" :placeholder="placeholder(item.key) + '…'" maxlength="200" />
          </el-form-item>
          <el-form-item label="服务地址（Base URL）" required>
            <el-input v-model="form[item.key].base_url" :name="`${item.key}-base-url`" :aria-label="`${item.title}服务地址`" type="url" autocomplete="off" :spellcheck="false" :placeholder="form[item.key].mode === 'ollama' ? 'http://localhost:11434…' : 'https://服务商地址/v1…'" />
          </el-form-item>
          <el-form-item :label="form[item.key].mode === 'ollama' ? 'API Key（可选，用于受保护的服务）' : 'API Key'">
            <el-input v-model="form[item.key].api_key" :name="`${item.key}-api-key`" :aria-label="`${item.title} API Key`" type="password" show-password autocomplete="new-password" :disabled="form[item.key].clear_key" :placeholder="form[item.key].api_key_configured ? '已配置，留空保留原密钥…' : '输入 API Key…'" />
            <el-checkbox v-if="form[item.key].api_key_configured" v-model="form[item.key].clear_key">清除已保存密钥</el-checkbox>
          </el-form-item>
        </div>
        <el-alert v-if="form[item.key].mode === 'ollama' && (item.key !== 'rerank' || form.rerank_enabled)" :closable="false" type="info" :title="item.key === 'rerank' ? 'Ollama 没有原生 Rerank 接口：此模式使用支持 JSON 输出的对话模型逐文档评分，例如 qwen3:8b，速度取决于本地硬件。专用重排模型请选择 API 服务。' : '请先在 Ollama 拉取模型。服务地址由后端和解析 worker 访问；Docker 部署访问宿主机通常使用 http://host.docker.internal:11434。'" />
        <div v-if="item.key !== 'rerank' || form.rerank_enabled" class="test-row">
          <el-button :loading="testing === item.key" @click="test(item.key)">{{ testing === item.key ? '正在测试…' : '测试连接' }}</el-button>
          <span v-if="results[item.key]" role="status" :class="results[item.key].success ? 'success' : 'failure'">{{ results[item.key].message }}</span>
        </div>
      </el-card>
    </el-form>
    <el-empty v-else-if="!loading" description="模型配置加载失败">
      <el-button @click="load">重新加载</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { personalModels } from '../../api/personal'
const modelConfigApi = personalModels
const personalSaved = ref(false)
const setupComplete = ref(false)
async function resetPersonal() {
  try { await ElMessageBox.confirm('将清除已保存的模型配置和密钥。资料与聊天会保留；重新配置前无法解析文档或生成回答。', '清空模型配置', { confirmButtonText: '清空配置', cancelButtonText: '取消' }) } catch (_) { return }
  saving.value = true
  try { await personalModels.reset(); setupComplete.value = false; await load(); ElMessage.success('配置已清空，请重新配置自己的模型。') } catch (_) {} finally { saving.value = false }
}

const roles = [
  { key: 'llm', title: '对话模型', description: '用于生成回答、改写多轮问题和生成会话标题。API 模式使用 OpenAI 兼容协议。' },
  { key: 'embedding', title: 'Embedding 模型', description: '用于文档和问题向量化。请使用同一模型建立索引和检索。' },
  { key: 'rerank', title: 'Rerank 模型', description: '对检索候选内容重新排序；关闭后使用原检索顺序。' },
]
const form = reactive({ revision: 0, rerank_enabled: false })
const loading = ref(false)
const ready = ref(false)
const saving = ref(false)
const testing = ref('')
const results = reactive({})
let savedEmbedding = ''
const savedSnapshot = ref('')
const dirty = computed(() => ready.value && savedSnapshot.value !== JSON.stringify(form))

function identity(endpoint) {
  return JSON.stringify([endpoint.mode, endpoint.model.trim(), endpoint.base_url.trim().replace(/\/+$/, '')])
}

function applyConfig(config) {
  personalSaved.value = !!config.personal
  form.revision = config.revision
  form.rerank_enabled = config.rerank_enabled
  for (const { key } of roles) {
    form[key] = { ...config[key], api_key: '', clear_key: false }
    delete results[key]
  }
  savedEmbedding = identity(form.embedding)
  ready.value = true
  savedSnapshot.value = JSON.stringify(form)
}

async function load() {
  loading.value = true
  try { applyConfig(await modelConfigApi.get()) }
  catch (_) { ElMessage.error('模型配置加载失败，请重试') }
  finally { loading.value = false }
}

function changeMode(role) {
  const endpoint = form[role]
  endpoint.base_url = ''
  endpoint.model = ''
  endpoint.protocol = 'openai'
  endpoint.api_key = ''
  endpoint.clear_key = endpoint.mode === 'ollama' && endpoint.api_key_configured
  delete results[role]
}

function placeholder(role) {
  if (form[role].mode === 'ollama') return role === 'embedding' ? '例如 bge-m3:latest' : '例如 qwen3:8b'
  return { llm: '例如 qwen-plus / deepseek-chat', embedding: '例如 text-embedding-v3', rerank: '例如 gte-rerank / BAAI/bge-reranker-v2-m3' }[role]
}

function payload(role) {
  if (role === 'rerank' && !form.rerank_enabled) return null
  const endpoint = form[role]
  return {
    mode: endpoint.mode, protocol: endpoint.protocol,
    model: endpoint.model.trim(), base_url: endpoint.base_url.trim().replace(/\/+$/, ''),
    api_key: endpoint.clear_key ? '' : endpoint.api_key.trim() || null,
  }
}

function valid(role) {
  const endpoint = payload(role)
  if (role === 'rerank' && !form.rerank_enabled) return true
  if (!endpoint.model || !/^https?:\/\//i.test(endpoint.base_url)) {
    ElMessage.warning('请填写模型名称和有效的 HTTP/HTTPS 服务地址')
    return false
  }
  if (endpoint.mode === 'api' && !endpoint.api_key && (endpoint.api_key === '' || !form[role].api_key_configured) && (role !== 'rerank' || form.rerank_enabled)) {
    ElMessage.warning('请填写 API Key，或选择 Ollama 本地部署')
    return false
  }
  return true
}

async function test(role) {
  if (!valid(role)) return
  testing.value = role
  delete results[role]
  try { results[role] = await modelConfigApi.test(role, payload(role)) }
  catch (_) { results[role] = { success: false, message: '连接测试未完成，请检查后台服务或稍后重试。' } }
  finally { testing.value = '' }
}

async function save() {
  if (!ready.value || !roles.every(({ key }) => valid(key))) return
  if (personalSaved.value && savedEmbedding !== identity(form.embedding)) {
    try {
      await ElMessageBox.confirm('Embedding 配置已变化。保存后请在文档管理重新解析已有文档，新向量索引建立前可能无法检索旧内容。', '更换 Embedding 模型', { confirmButtonText: '保存配置', cancelButtonText: '继续编辑', type: 'warning' })
    } catch (_) { return }
  }
  saving.value = true
  try {
    const data = { revision: form.revision, rerank_enabled: form.rerank_enabled }
    for (const { key } of roles) data[key] = payload(key)
    const response = await modelConfigApi.save(data)
    const firstSave = !personalSaved.value
    applyConfig(response)
    setupComplete.value ||= firstSave
    ElMessage.success(response.embedding_changed ? '配置已生效，请重新解析已有文档' : '模型配置已保存并生效')
  } catch (_) { /* 请求拦截器显示具体错误，保留编辑内容 */ }
  finally { saving.value = false }
}

for (const { key } of roles) watch(() => form[key], () => { delete results[key] }, { deep: true })
onMounted(load)
function beforeUnload(event) { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => window.addEventListener('beforeunload', beforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload))
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true
  try { await ElMessageBox.confirm('模型配置尚未保存。离开后，本次编辑将丢失。', '离开模型配置？', { confirmButtonText: '放弃更改并离开', cancelButtonText: '继续编辑', type: 'warning' }); return true }
  catch { return false }
})
</script>

<style scoped>
.setup-guide { padding: 24px; margin-bottom: 20px; background: var(--accent-soft); border: 1px solid var(--line); border-radius: 12px; }.setup-guide h2 { margin: 10px 0; font-size: 21px; }.setup-guide p,.setup-guide ol { font-size: 13px; line-height: 1.9; color: var(--muted); }.setup-guide ol { padding-left: 20px; margin-top: 12px; }.setup-complete { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px; padding: 18px; margin-top: 16px; border-radius: 10px; background: var(--accent-soft); font-size: 13px; }.setup-complete a { font-weight: 600; }
.model-config { max-width: 1100px; margin: 0 auto; }.save-actions { display: flex; align-items: center; gap: 12px; }.unsaved-indicator { font-size: 11px; color: #9a6d29; }.model-flow { display: grid; grid-template-columns: repeat(3,1fr); margin-bottom: 24px; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 22px; gap: 20px; }.model-flow>div { display: flex; align-items: center; gap: 12px; min-width: 0; }.model-flow strong { font-size: 12px; font-weight: 550; }.model-flow p { font-size: 10px; color: var(--muted); margin-top: 6px; }.flow-arrow { color: #a5b493; margin-left: auto; }.model-flow .model-step { flex-shrink: 0; }
.page-header, .card-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
h3 { margin: 0; }
.page-header { margin-bottom: 20px; }
.page-header p, .description { color: #606266; font-size: 14px; line-height: 1.6; }
.notice, .model-card { margin-top: 16px; }
.fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 24px; }
.description { margin: 0 0 20px; }
.test-row { display: flex; align-items: center; gap: 14px; margin-top: 16px; line-height: 1.6; }
.success { color: #16813c; }
.failure { color: #c0392b; }
@media (max-width: 900px) { .fields { grid-template-columns: 1fr; } .page-header { align-items: flex-start; } }
@media (max-width: 600px) { .model-flow { grid-template-columns: 1fr; gap: 20px; }.flow-arrow { display: none; }.save-actions { width: 100%; justify-content: space-between; } }
</style>
