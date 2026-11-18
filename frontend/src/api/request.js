import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '../router'

const request = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

request.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

/** 从 FastAPI 错误响应中提取用户可读信息（detail 可能是对象或 422 校验数组） */
export function extractErrorMessage(detail) {
  if (Array.isArray(detail)) {
    // FastAPI 422 校验错误：[{loc, msg, type}, ...]
    return detail.map((d) => d.msg || String(d)).join('；')
  }
  if (typeof detail === 'object' && detail !== null) {
    return detail.message
  }
  return detail
}

/** 401 全局处理：清 Pinia + localStorage 并跳登录（动态 import 避免循环依赖） */
export async function handleUnauthorized(message) {
  const { useAuthStore } = await import('../stores/auth')
  await useAuthStore().logout()
  if (router.currentRoute.value.path !== '/login') {
    ElMessage.error(message || '登录已过期，请重新登录')
    router.push('/login')
  }
}

request.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status
    if (error.response?.data instanceof Blob) {
      try { error.response.data = JSON.parse(await error.response.data.text()) } catch (_) {}
    }
    const message = extractErrorMessage(error.response?.data?.detail)

    if (status === 401) {
      await handleUnauthorized(message)
    } else if (error.config?.skipErrorNotification) {
      // 调用方提供了错误状态与重试入口（例如首次加载会话列表）。
    } else if (status === 403) {
      ElMessage.error(message || '无权访问')
    } else if (status === 429) {
      ElMessage.warning(message || '请求过于频繁，请稍后再试')
    } else if (status === 428 && error.response?.data?.detail?.code === 'model_config_required') {
      ElMessage.warning(message || '请先配置自己的模型')
    } else if (message) {
      ElMessage.error(message)
    } else if (!status) {
      ElMessage.error('网络连接失败或请求超时，请检查网络后重试。')
    }
    return Promise.reject(error)
  }
)

export default request
