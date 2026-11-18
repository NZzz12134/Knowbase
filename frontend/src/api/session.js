import request from './request'

export const sessionApi = {
  list(params, config = {}) {
    return request.get('/sessions', { ...config, params })
  },
  create(data) {
    return request.post('/sessions', data)
  },
  rename(id, title) {
    return request.patch(`/sessions/${id}`, { title })
  },
  remove(id) {
    return request.delete(`/sessions/${id}`)
  },
  messages(id, params) {
    return request.get(`/sessions/${id}/messages`, { params })
  },
}
