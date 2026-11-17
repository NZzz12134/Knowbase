<template>
  <main id="main-content" tabindex="-1" class="profile-page">
    <RouterLink to="/" aria-label="知库，返回聊天"><BrandLogo /></RouterLink>
    <el-card class="profile-card">
      <template #header>
        <div style="display: flex; align-items: center; justify-content: space-between">
          <h1 style="font-size: 20px">账号与安全</h1>
          <RouterLink to="/" style="font-size: 12px">返回知识对话 ↗</RouterLink>
        </div>
      </template>

      <p class="profile-intro">管理你的个人信息，保护你的知识空间。</p>
      <p style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:24px"><RouterLink to="/space/library">我的知识库 ↗</RouterLink><RouterLink to="/space/models">我的模型 ↗</RouterLink><RouterLink to="/space/data">数据导出与删除 ↗</RouterLink></p>
      <el-descriptions :column="1" border style="margin-bottom: 24px">
        <el-descriptions-item label="用户名">{{ auth.user?.username }}</el-descriptions-item>
        <el-descriptions-item label="邮箱">{{ auth.user?.email || '未填写' }}</el-descriptions-item>
      </el-descriptions>

      <h2 style="margin-bottom: 12px; font-size: 16px">修改密码</h2>
      <el-form :model="form" label-position="top" @submit.prevent="submit">
        <el-form-item label="原密码" for="profile-old_password" :error="errors.old_password">
          <el-input id="profile-old_password" v-model="form.old_password" aria-label="原密码" name="old-password" autocomplete="current-password" type="password" show-password />
        </el-form-item>
        <el-form-item label="新密码（至少 6 位）" for="profile-new_password" :error="errors.new_password">
          <el-input id="profile-new_password" v-model="form.new_password" aria-label="新密码" name="new-password" autocomplete="new-password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码" for="profile-confirm" :error="errors.confirm">
          <el-input id="profile-confirm" v-model="form.confirm" aria-label="确认新密码" name="confirm-password" autocomplete="new-password" type="password" show-password />
        </el-form-item>
        <el-button native-type="submit" type="primary" :loading="loading">{{ loading ? '正在修改…' : '确认修改' }}</el-button>
      </el-form>
    </el-card>
  </main>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { authApi } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import BrandLogo from '../components/BrandLogo.vue'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const form = reactive({ old_password: '', new_password: '', confirm: '' })
const errors = reactive({})
function invalid(field, message) { errors[field] = message; document.getElementById(`profile-${field}`)?.focus() }

async function submit() {
  if (loading.value) return
  for (const field of Object.keys(errors)) delete errors[field]
  if (!form.old_password) return invalid('old_password', '请输入原密码。')
  if (form.new_password.length < 6) {
    invalid('new_password', '新密码至少需要 6 位。')
    return
  }
  if (form.new_password !== form.confirm) {
    invalid('confirm', '两次新密码不一致，请重新输入。')
    return
  }
  loading.value = true
  try {
    await authApi.changePassword({ old_password: form.old_password, new_password: form.new_password })
    await ElMessageBox.alert('密码修改成功，请重新登录', '提示')
    auth.logout()
    router.push('/login')
  } catch (_) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}
</script>
