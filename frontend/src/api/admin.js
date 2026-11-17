import request from './request'

export const kbApi = {
  list() {
    return request.get('/kbs')
  },
  all() {
    return request.get('/kbs', { params: { include_inactive: true } })
  },
  create(data) {
    return request.post('/kbs', data)
  },
  update(id, data) {
    return request.patch(`/kbs/${id}`, data)
  },
  remove(id) {
    return request.delete(`/kbs/${id}`)
  },
}

export const documentApi = {
  list(params) {
    return request.get('/documents', { params })
  },
  upload(kbId, file) {
    const form = new FormData()
    form.append('file', file)
    return request.post(`/documents?kb_id=${kbId}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  createUrl(kbId, url) {
    return request.post(`/documents/url?kb_id=${kbId}`, { url })
  },
  detail(id) {
    return request.get(`/documents/${id}`)
  },
  reparse(id) {
    return request.post(`/documents/${id}/reparse`)
  },
  retry(id) {
    return request.post(`/documents/${id}/retry`)
  },
  remove(id) {
    return request.delete(`/documents/${id}`)
  },
  chunks(id, params) {
    return request.get(`/documents/${id}/chunks`, { params })
  },
}

export const statsApi = {
  overview() {
    return request.get('/me/stats/overview')
  },
  dailyQa() {
    return request.get('/me/stats/daily-qa')
  },
  documents() {
    return request.get('/me/stats/documents')
  },
}
