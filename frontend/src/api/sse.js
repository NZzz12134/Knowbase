/**
 * SSE 流式请求：POST + fetch ReadableStream 解析 event:/data: 格式。
 * 返回 { abort, promise }，promise resolve 全部事件数组。
 * 401/429 与 axios 拦截器保持一致的处理（清凭证、提示、跳转）。
 */
import { ElMessage } from 'element-plus'
import { extractErrorMessage, handleUnauthorized } from './request'
import { consumeEventStream } from '../utils/eventStream'

export function streamPost(url, body, onEvent) {
  const controller = new AbortController()

  const promise = (async () => {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    if (!response.ok) {
      let message = `请求失败 (${response.status})`
      let detail
      try {
        const data = await response.json()
        detail = data?.detail
        message = extractErrorMessage(detail) || message
      } catch (_) {
        /* ignore */
      }
      if (response.status === 401) {
        await handleUnauthorized(message)
      } else if (response.status === 429) {
        ElMessage.warning(message || '请求过于频繁，请稍后再试')
      } else if (response.status === 428 && detail?.code === 'model_config_required') {
        ElMessage.warning(message)
      }
      throw new Error(message)
    }

    if (!response.body) {
      throw new Error('浏览器不支持流式响应')
    }

    return consumeEventStream(response.body, onEvent)
  })()

  return { abort: () => controller.abort(), promise }
}
