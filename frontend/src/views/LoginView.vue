<template>
  <AuthShell>
      <span class="eyebrow">WELCOME BACK</span>
      <h1 class="title">欢迎回到知库</h1>
      <p class="subtitle">继续探索你的知识，找到下一份灵感。</p>
      <el-form :model="form" @submit.prevent="submit" label-position="top">
        <el-form-item label="用户名" for="login-username">
          <el-input id="login-username" v-model="form.username" name="username" autocomplete="username" :spellcheck="false" placeholder="输入你的用户名…" size="large" />
        </el-form-item>
        <el-form-item label="密码" for="login-password">
          <el-input id="login-password" v-model="form.password" name="password" autocomplete="current-password" type="password" placeholder="输入你的密码…" size="large" show-password />
        </el-form-item>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <el-button native-type="submit" type="primary" size="large" style="width: 100%; margin-top: 8px" :loading="loading">
          {{ loading ? '正在登录…' : '登录知库' }}<span style="margin-left: auto" aria-hidden="true">↗</span>
        </el-button>
        <div class="footer">
          <span>还没有账号？</span>
          <RouterLink to="/register">创建账号</RouterLink>
        </div>
      </el-form>
  </AuthShell>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import AuthShell from '../components/AuthShell.vue'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })

async function submit() {
  if (loading.value) return
  error.value = ''
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码。'
    document.getElementById(!form.username ? 'login-username' : 'login-password')?.focus()
    return
  }
  loading.value = true
  try {
    const data = await authApi.login(form)
    auth.setAuth(data.access_token, data.user)
    ElMessage.success('登录成功')
    const redirect = typeof route.query.redirect === 'string' && route.query.redirect.startsWith('/') && !route.query.redirect.startsWith('//') ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (err) {
    error.value = err.response?.status === 401 ? '用户名或密码不正确，请重新输入。' : '登录未完成，请检查网络后重试。'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.title { font-size: 30px; font-weight: 600; margin-top: 16px; }.subtitle { color: var(--muted); font-size: 13px; margin: 12px 0 36px; line-height: 1.8; }.footer { margin-top: 25px; text-align: center; font-size: 12px; color: var(--muted); }.footer a { margin-left: 8px; font-weight: 600; }.form-error { color: var(--el-color-danger); font-size: 12px; margin-bottom: 12px; }
</style>
