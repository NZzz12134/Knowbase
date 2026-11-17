import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue'), meta: { public: true } },
  { path: '/', name: 'chat', component: () => import('../views/ChatView.vue') },
  { path: '/profile', name: 'profile', component: () => import('../views/ProfileView.vue') },
  {
    path: '/space', component: () => import('../views/admin/AdminLayout.vue'),
    children: [
      { path: '', redirect: '/space/library' },
      { path: 'library', name: 'personal-library', component: () => import('../views/admin/KnowledgeBaseView.vue') },
      { path: 'documents', name: 'personal-documents', component: () => import('../views/admin/DocumentView.vue') },
      { path: 'models', name: 'personal-models', component: () => import('../views/admin/ModelConfigView.vue') },
      { path: 'stats', name: 'personal-stats', component: () => import('../views/admin/StatsView.vue') },
      { path: 'data', name: 'personal-data', component: () => import('../views/PersonalDataView.vue') },
    ],
  },
  { path: '/admin', redirect: '/space/library' },
  { path: '/admin/kbs', redirect: to => ({ path: '/space/library', query: to.query }) },
  { path: '/admin/documents', redirect: to => ({ path: '/space/documents', query: to.query }) },
  { path: '/admin/stats', redirect: '/space/stats' },
  { path: '/admin/models', redirect: '/space/models' },
  { path: '/forbidden', name: 'forbidden', component: () => import('../views/ForbiddenView.vue'), meta: { public: true } },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.meta.public) return true
  if (!auth.isLoggedIn) return { path: '/login', query: { redirect: to.fullPath } }
  return true
})

export default router

router.afterEach((to) => {
  if (String(to.name).startsWith('personal-')) { document.title = `${{ 'personal-library': '我的知识库', 'personal-documents': '我的文档', 'personal-models': '我的模型', 'personal-stats': '使用统计', 'personal-data': '数据与备份' }[to.name]} · 知库 Knowbase`; return }
  const titles = { login: '登录', register: '创建账号', chat: '知识对话', profile: '账号与安全', forbidden: '无权访问' }
  document.title = `${titles[to.name] || '知识工作台'} · 知库 Knowbase`
})
