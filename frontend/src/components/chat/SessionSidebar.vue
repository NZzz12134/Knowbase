<template>
  <button v-if="open" class="sidebar-backdrop" @click="$emit('close')" aria-label="关闭会话导航" tabindex="-1"></button>
  <aside ref="sidebarRef" class="sidebar" :class="{ 'sidebar--open': open }" :role="open ? 'dialog' : undefined" :aria-modal="open ? true : undefined" aria-label="会话导航" @keydown="onSidebarKeyDown">
    <div class="sidebar-brand"><BrandLogo :size="34" /><button class="icon-button sidebar-close" aria-label="关闭会话列表" @click="$emit('close')"><el-icon aria-hidden="true"><Close /></el-icon></button></div>
    <div class="sidebar-header">
      <el-button type="primary" style="width: 100%" @click="openCreateDialog">
        <el-icon aria-hidden="true"><Plus /></el-icon>&nbsp;开启新对话<span class="new-shortcut" aria-hidden="true">↗</span>
      </el-button>
      <div class="session-search"><el-icon aria-hidden="true"><Search /></el-icon><input v-model="search" aria-label="搜索会话" name="session-search" autocomplete="off" placeholder="搜索你的对话…" /></div>
    </div>
    <div class="session-caption">最近对话<span>{{ store.loaded ? filteredSessions.length : '—' }}</span></div>
    <div class="session-list" :aria-busy="store.loading">
      <TransitionGroup name="session">
      <div
        v-for="s in filteredSessions"
        :key="s.id"
        class="session-item"
        :class="{ active: s.id === currentId }"
      >
        <button class="session-info" :aria-current="s.id === currentId ? 'true' : undefined" @click="onSelect(s)">
          <span class="session-title">
            {{ s.title }}
            <el-tag v-if="s.kb_id" size="small" type="info" effect="plain" class="kb-tag">
              {{ kbName(s.kb_id) }}
            </el-tag>
          </span>
          <span class="session-preview">{{ s.last_message_preview || '从一个问题开始' }}</span>
        </button>
        <el-dropdown trigger="click" @command="(cmd) => onItemCommand(cmd, s)">
          <button class="icon-button more-btn" :aria-label="`管理会话：${s.title}`"><el-icon aria-hidden="true"><MoreFilled /></el-icon></button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="rename">重命名</el-dropdown-item>
              <el-dropdown-item command="delete" divided>
                <span style="color: #f56c6c">删除会话</span>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      </TransitionGroup>
      <div v-if="store.loading && !store.loaded" class="no-sessions" role="status">正在加载最近对话…</div>
      <div v-else-if="store.loadError" class="session-load-error" role="alert"><p>{{ store.loadError }}</p><el-button link type="primary" :loading="store.loading" @click="$emit('retry')">重新加载</el-button></div>
      <div v-else-if="!filteredSessions.length" class="no-sessions">{{ search ? '没有找到匹配的对话' : '你的思考，从这里开始。' }}</div>
    </div>
    <div class="sidebar-bottom">
      <RouterLink to="/space/library" class="sidebar-admin"><el-icon aria-hidden="true"><Collection /></el-icon><span>我的知识空间</span><span aria-hidden="true">↗</span></RouterLink>
      <div class="sidebar-note"><span class="note-mark" aria-hidden="true">↗</span><div><strong>让知识触手可及</strong><p>提问、探索，连接每一份知识。</p></div></div>
      <div class="sidebar-foot"><span>KNOWBASE</span><span>知识，有据可循。</span></div>
    </div>

    <!-- 新建会话弹窗：标题 + 检索范围（知识库） -->
    <el-dialog v-model="createDialogVisible" title="新建会话" width="440px">
      <el-form label-width="90px">
        <el-form-item label="会话标题">
          <el-input v-model="createForm.title" name="session-title" autocomplete="off" aria-label="会话标题" maxlength="200" placeholder="可留空，自动生成标题…" />
        </el-form-item>
        <el-form-item label="检索范围">
          <el-select v-model="createForm.kbId" aria-label="检索范围" style="width: 100%" placeholder="选择知识库…">
            <el-option :value="null" label="全部知识库" />
            <el-option v-for="k in kbs" :key="k.id" :value="k.id" :label="k.name" />
          </el-select>
          <div class="kb-hint">选择后该会话只检索对应知识库；「全部」则跨库检索取最相关</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </aside>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Close, Collection, MoreFilled, Plus, Search } from '@element-plus/icons-vue'
import { kbApi } from '../../api/admin'
import { useSessionStore } from '../../stores/session'
import BrandLogo from '../BrandLogo.vue'

const props = defineProps({ open: Boolean })
const sidebarRef = ref(null)
let returnFocus
const search = ref('')

const store = useSessionStore()
const sessions = computed(() => store.sessions)
const currentId = computed(() => store.currentId)
const filteredSessions = computed(() => sessions.value.filter(s => `${s.title} ${s.last_message_preview || ''}`.toLowerCase().includes(search.value.toLowerCase())))

const emit = defineEmits(['changed', 'close', 'retry'])
watch(() => props.open, async open => {
  if (open) { returnFocus = document.activeElement; await nextTick(); sidebarRef.value?.querySelector('.sidebar-close')?.focus() }
  else returnFocus?.focus()
})
function onSidebarKeyDown(event) {
  if (!props.open || createDialogVisible.value) return
  if (event.key === 'Escape') emit('close')
  if (event.key !== 'Tab') return
  const focusable = [...sidebarRef.value.querySelectorAll('button:not(:disabled),a,input,[tabindex="0"]')].filter(el => el.getClientRects().length)
  const first = focusable[0], last = focusable.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}

const kbs = ref([])
const createDialogVisible = ref(false)
const creating = ref(false)
const createForm = reactive({ title: '', kbId: null })

onMounted(async () => {
  kbApi.list().then((data) => (kbs.value = data)).catch(() => {})
  window.addEventListener('keydown', closeOnEscape)
  window.addEventListener('resize', closeOnDesktop)
})
function closeOnEscape(event) { if (event.key === 'Escape' && props.open && !createDialogVisible.value) emit('close') }
function closeOnDesktop() { if (props.open && window.innerWidth > 800) emit('close') }
onBeforeUnmount(() => { window.removeEventListener('keydown', closeOnEscape); window.removeEventListener('resize', closeOnDesktop) })

function kbName(kbId) {
  return kbs.value.find((k) => k.id === kbId)?.name || ''
}

function openCreateDialog() {
  createForm.title = ''
  createForm.kbId = null
  createDialogVisible.value = true
}

async function submitCreate() {
  creating.value = true
  try {
    const session = await store.createSession(createForm.title.trim() || '新会话', createForm.kbId)
    createDialogVisible.value = false
    emit('changed', session.id)
  } catch (_) {
    /* 拦截器已提示 */
  } finally {
    creating.value = false
  }
}

async function onSelect(session) {
  store.setCurrent(session.id)
  emit('changed', session.id)
}

async function onItemCommand(command, session) {
  if (command === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('请输入新标题', '重命名会话', {
        inputValue: session.title,
        confirmButtonText: '确定',
        cancelButtonText: '取消',
      })
      await store.renameSession(session.id, value || session.title)
    } catch (_) { /* ignore */ }
  } else if (command === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除会话「${session.title}」吗？`, '提示', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      await store.removeSession(session.id)
      ElMessage.success('已删除')
      emit('changed', store.currentId)
    } catch (_) { /* ignore */ }
  }
}
</script>

<style scoped>
.sidebar {
  width: 272px;
  flex-shrink: 0;
  background: var(--sidebar);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sidebar-brand { height: 76px; display: flex; align-items: center; justify-content: space-between; padding: 0 22px; flex-shrink: 0; }.sidebar-close { display: none; }.sidebar-header { padding: 12px 18px 18px; }.sidebar-header>.el-button { height: 43px; border-radius: 9px; font-size: 12px; justify-content: flex-start; }.new-shortcut { margin-left: auto; font-size: 16px; opacity: .7; }
.session-search { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 8px 4px; color: #7c887b; border: 1px solid transparent; border-radius: 9px; transition: border-color .18s, background-color .18s, box-shadow .18s; }.session-search:focus-within { border-color: var(--accent); background: #fff; box-shadow: 0 0 0 3px #17634d14; }.session-search input { width: 100%; min-width: 0; border: 0; background: transparent; color: var(--ink); font-size: 12px; padding: 4px; }.session-search input:focus-visible { outline: none; }.session-search input::placeholder { color: #7c887b; }.session-caption { padding: 2px 23px 12px; font-size: 10px; color: #7a8578; display: flex; justify-content: space-between; }.session-caption span { font-variant-numeric: tabular-nums; }
.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 12px 16px;
  overscroll-behavior: contain;
}
.session-item {
  display: flex;
  align-items: center;
  padding: 3px 7px 3px 12px;
  border-radius: 9px;
  margin-bottom: 6px;
  transition: background-color .18s;
  content-visibility: auto;
  contain-intrinsic-size: auto 67px;
}
.session-item:hover { background: #e5eae0; }.session-item.active { background: #fff; box-shadow: 0 2px 6px #233a2510; }
.session-info { flex: 1; min-width: 0; display: block; text-align: left; background: transparent; border: 0; padding: 12px 0; color: var(--ink); }
.session-title {
  font-size: 12px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 4px;
}
.kb-tag { max-width: 90px; overflow: hidden; text-overflow: ellipsis; }
.session-preview {
  display: block;
  font-size: 11px;
  color: #6b7768;
  margin-top: 7px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.more-btn { width: 25px; height: 30px; color: #7c887b; }.more-btn:hover { color: var(--accent); }
.kb-hint { font-size: 12px; color: #909399; line-height: 1.5; margin-top: 4px; }
.sidebar-bottom { padding: 16px 18px 18px; }.sidebar-note { display: flex; align-items: center; gap: 12px; border: 1px solid #dbe3d3; padding: 14px 10px; border-radius: 9px; }.note-mark { font-size: 21px; color: #668153; }.sidebar-note strong { font-size: 11px; font-weight: 550; }.sidebar-note p { font-size: 10px; color: #74806e; margin-top: 5px; }.sidebar-admin { display: flex; align-items: center; gap: 10px; padding: 15px 4px; font-size: 12px; color: #52644e; }.sidebar-admin .el-icon:last-child { margin-left: auto; }.sidebar-admin:hover { color: var(--accent); }.sidebar-foot { display: flex; justify-content: space-between; font-size: 9px; color: #778370; padding-top: 12px; border-top: 1px solid #dce3d6; }.sidebar-foot span:first-child { letter-spacing: 1.7px; }.no-sessions { padding: 35px 10px; text-align: center; font-size: 11px; color: var(--muted); }
.session-enter-active,.session-move { transition: transform .25s var(--ease), opacity .25s; }.session-leave-active { transition: opacity .15s; }.session-enter-from { opacity: 0; transform: translateY(-5px); }.session-leave-to { opacity: 0; }.sidebar-backdrop { display: none; }
.session-load-error { padding: 24px 10px; text-align: center; color: var(--muted); font-size: 12px; line-height: 1.8; }.session-load-error .el-button { margin-top: 8px; }
@media (max-width: 800px) { .sidebar { position: fixed; top: 0; bottom: 0; left: 0; z-index: 101; width: min(300px,85vw); transform: translateX(-100%); visibility: hidden; transition: transform .28s var(--ease), visibility .28s; }.sidebar--open { transform: translateX(0); visibility: visible; }.sidebar-close { display: flex; }.sidebar-backdrop { display: block; position: fixed; inset: 0; z-index: 100; border: 0; background: #1a2b2366; animation: appear .16s; } }
</style>
