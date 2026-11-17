<template>
  <div class="admin-layout">
    <aside class="admin-sidebar" aria-label="个人空间导航">
      <RouterLink to="/" class="admin-brand" aria-label="知库，返回知识对话"><BrandLogo :size="34" /></RouterLink>
      <div class="nav-caption">MY WORKSPACE<span>个人知识空间</span></div>
      <nav class="admin-nav"><RouterLink v-for="item in navigation" :key="item.path" :to="item.path" class="nav-item"><el-icon aria-hidden="true"><component :is="item.icon" /></el-icon><span>{{ item.title }}</span><span v-if="route.path === item.path" class="nav-dot" aria-hidden="true"></span></RouterLink></nav>
      <div class="admin-side-bottom"><div class="workspace-card"><span class="workspace-card-icon"><el-icon aria-hidden="true"><Collection /></el-icon></span><strong>你的知识，由你管理</strong><p>整理内容、连接模型，<br />为每个问题准备好答案。</p></div><RouterLink to="/" class="back-link"><el-icon aria-hidden="true"><Back /></el-icon><span>返回知识对话</span><span aria-hidden="true">↗</span></RouterLink><div class="side-signature">KNOWBASE <span>PERSONAL SPACE</span></div></div>
    </aside>
    <div class="admin-body">
      <header class="admin-topbar"><div><span class="topbar-label">个人空间</span><span class="topbar-slash">/</span><span>{{ currentPage }}</span></div><RouterLink to="/profile" class="admin-account"><span class="admin-role">仅自己可见</span><el-avatar :size="30">{{ (auth.user?.username || 'A').slice(0,1).toUpperCase() }}</el-avatar><span>{{ auth.user?.username }}</span></RouterLink></header>
      <main id="main-content" tabindex="-1" class="admin-main"><router-view v-slot="{ Component, route: childRoute }"><Transition name="route" mode="out-in"><component :is="Component" :key="childRoute.path" /></Transition></router-view></main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Back, Collection, DataAnalysis, Document, FolderOpened, Setting } from '@element-plus/icons-vue'
import BrandLogo from '../../components/BrandLogo.vue'
import { useAuthStore } from '../../stores/auth'
const route = useRoute()
const auth = useAuthStore()
const navigation = [{ path: '/space/library', icon: FolderOpened, title: '我的知识库' }, { path: '/space/documents', icon: Document, title: '我的文档' }, { path: '/space/models', icon: Setting, title: '我的模型' }, { path: '/space/stats', icon: DataAnalysis, title: '使用统计' }, { path: '/space/data', icon: DataAnalysis, title: '数据与备份' }]
const currentPage = computed(() => navigation.find(item => item.path === route.path)?.title || '个人知识空间')
</script>

<style scoped>
.admin-layout { height: 100dvh; display: flex; overflow: hidden; }.admin-sidebar { width: 236px; flex-shrink: 0; display: flex; flex-direction: column; background: var(--sidebar); border-right: 1px solid var(--line); }.admin-brand { display: flex; height: 76px; align-items: center; padding: 0 21px; flex-shrink: 0; }.nav-caption { padding: 32px 25px 18px; color: #849078; font-size: 9px; letter-spacing: 1.6px; }.nav-caption span { display: block; letter-spacing: 0; margin-top: 10px; font-size: 11px; color: #6b7862; }.admin-nav { padding: 0 13px; display: flex; flex-direction: column; gap: 7px; }.nav-item { display: flex; align-items: center; gap: 12px; padding: 14px 13px; color: #65735d; font-size: 12px; border-radius: 8px; transition: color .18s, background-color .18s, transform .18s; }.nav-item>.el-icon { font-size: 17px; }.nav-item:hover { background: #e1e8db; color: var(--accent); }.nav-item.router-link-active { background: #fff; color: var(--accent); box-shadow: 0 2px 4px #233b2610; font-weight: 600; }.nav-dot { width: 5px; height: 5px; background: var(--accent); border-radius: 50%; margin-left: auto; }.admin-side-bottom { margin-top: auto; padding: 26px 19px 20px; }.workspace-card { padding: 21px 16px; border: 1px solid #d7e0cd; border-radius: 11px; background: #e6ecde; }.workspace-card-icon { display: block; font-size: 23px; color: #6c8759; margin-bottom: 14px; }.workspace-card strong { display: block; font-size: 12px; font-weight: 550; }.workspace-card p { margin-top: 9px; font-size: 11px; color: #748267; line-height: 1.9; }.back-link { display: flex; gap: 9px; align-items: center; padding: 22px 4px; font-size: 12px; }.back-link span:last-child { margin-left: auto; }.side-signature { display: flex; justify-content: space-between; padding-top: 13px; border-top: 1px solid #dbe2d4; color: #7f8c74; font-size: 8px; letter-spacing: 1px; }.side-signature>span { letter-spacing: .5px; }.admin-body { flex: 1; min-width: 0; display: flex; flex-direction: column; }.admin-topbar { height: 76px; flex-shrink: 0; padding: 0 38px; border-bottom: 1px solid var(--line); display: flex; align-items: center; justify-content: space-between; font-size: 12px; }.admin-topbar>div { display: flex; gap: 16px; }.topbar-label { color: var(--muted); }.topbar-slash { color: #bdc7b5; }.admin-account { display: flex; align-items: center; gap: 10px; color: var(--ink); font-size: 11px; }.admin-role { color: #6d7b63; border: 1px solid #d9e2d1; padding: 4px 7px; border-radius: 4px; font-size: 9px; }.admin-account .el-avatar { background: #e3ebda; color: #4d6944; font-size: 12px; }.admin-main { overflow-y: auto; min-height: 0; padding: 38px; overscroll-behavior: contain; scrollbar-gutter: stable; }
@media (max-width: 1000px) { .admin-sidebar { width: 205px; }.admin-brand { padding: 0 14px; }.admin-main { padding: 26px; }.admin-topbar { padding: 0 26px; } }
@media (max-width: 700px) { .admin-layout { flex-direction: column; }.admin-sidebar { width: 100%; border-right: 0; border-bottom: 1px solid var(--line); flex-direction: row; flex-wrap: wrap; }.admin-brand { height: 61px; width: 100%; padding: 0 20px; }.nav-caption,.admin-side-bottom { display: none; }.admin-nav { flex-direction: row; width: 100%; padding: 0 10px 9px; gap: 3px; overflow-x: auto; }.nav-item { flex: 1; justify-content: center; gap: 6px; padding: 10px 7px; white-space: nowrap; font-size: 11px; }.nav-item>.el-icon { font-size: 14px; }.nav-dot { display: none; }.admin-body { min-height: 0; }.admin-topbar { height: 50px; padding: 0 18px; }.admin-main { padding: 24px 16px; }.admin-account .admin-role { display: none; } }
</style>
