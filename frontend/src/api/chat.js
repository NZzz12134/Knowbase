import request from './request'
import { streamPost } from './sse'

export const chatApi = {
  /** SSE 流式问答 */
  stream(sessionId, question, onEvent, retryMessageId) {
    return streamPost('/api/v1/chat/stream', { session_id: sessionId, question, retry_message_id: retryMessageId || null }, onEvent)
  },
  citations(messageId) {
    return request.get(`/messages/${messageId}/citations`)
  },
  feedback(messageId, data) {
    return request.post(`/messages/${messageId}/feedback`, data)
  },
  removeFeedback(messageId) {
    return request.delete(`/messages/${messageId}/feedback`)
  },
}
