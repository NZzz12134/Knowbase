<template>
  <AuthShell>
      <span class="eyebrow">START WITH KNOWLEDGE</span>
      <h1 class="title">建立你的知识空间</h1>
      <p class="subtitle">创建账号，开始整理你的知识空间。</p>
      <el-form :model="form" @submit.prevent="submit" label-position="top">
        <el-form-item label="用户名（3-50 位，字母/数字/下划线/中文）" for="register-username" :error="errors.username">
          <el-input id="register-username" v-model="form.username" name="username" autocomplete="username" aria-label="用户名" :spellcheck="false" placeholder="例如：knowbase_user…" size="large" />
        </el-form-item>
        <el-form-item label="邮箱（可选）" for="register-email" :error="errors.email">
          <el-input id="register-email" v-model="form.email" name="email" type="email" autocomplete="email" aria-label="邮箱" :spellcheck="false" placeholder="例如：you@example.com…" size="large" />
        </el-form-item>
        <el-form-item label="密码（至少 6 位）" for="register-password" :error="errors.password">
          <el-input id="register-password" v-model="form.password" name="password" autocomplete="new-password" aria-label="密码" type="password" placeholder="设置至少 6 位密码…" size="large" show-password />
        </el-form-item>
        <el-form-item label="确认密码" for="register-confirm" :error="errors.confirm">
          <el-input id="register-confirm" v-model="form.confirm" name="confirm" autocomplete="new-password" aria-label="确认密码" type="password" placeholder="再次输入密码…" size="large" show-password />
        </el-form-item>
        <el-button native-type="submit" type="primary" size="large" style="width: 100%" :loading="loading">
          {{ loading ? '正在创建…' : '创建账号' }}
        </el-button>
        <div class="footer">
          <span>已有账号？</span>
          <RouterLink to="/login">登录知库</RouterLink>
        </div>
      </el-form>
  </AuthShell>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import AuthShell from '../components/AuthShell.vue'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ username: '', email: '', password: '', confirm: '' })
const errors = reactive({})
function invalid(field, message) { errors[field] = message; document.getElementById(`register-${field}`)?.focus() }

async function submit() {
  if (loading.value) return
  for (const field of Object.keys(errors)) delete errors[field]
  if (!/^[a-zA-Z0-9_一-龥]{3,50}$/.test(form.username)) return invalid('username', '请输入 3–50 位用户名，仅支持字母、数字、下划线和中文。')
  if (form.password.length < 6) {
    invalid('password', '密码至少需要 6 位。')
    return
  }
  if (form.password !== form.confirm) {
    invalid('confirm', '两次密码不一致，请重新输入。')
    return
  }
  loading.value = true
  try {
    const data = await authApi.register({
      username: form.username,
      password: form.password,
      email: form.email || null,
    })
    auth.setAuth(data.access_token, data.user)
    ElMessage.success('注册成功')
    await router.replace('/')
  } catch (_) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.title { font-size: 28px; font-weight: 600; margin-top: 16px; }.subtitle { color: var(--muted); font-size: 13px; margin: 12px 0 28px; }.footer { margin-top: 24px; text-align: center; font-size: 12px; color: var(--muted); }.footer a { margin-left: 8px; font-weight: 600; }
</style>
