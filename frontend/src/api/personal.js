import request from './request'

export const personalModels = {
  get: () => request.get('/me/model-config'),
  save: data => request.put('/me/model-config', data),
  test: (role, endpoint) => request.post('/me/model-config/test', { role, endpoint }, { timeout: 200000 }),
  reset: () => request.delete('/me/model-config'),
}

export const personalApi = {
  onboarding: () => request.get('/me/onboarding'),
  export: () => request.get('/me/export', { responseType: 'blob', timeout: 300000 }),
  clear: data => request.post('/me/delete-data', data, { timeout: 300000 }),
  import: file => { const data = new FormData(); data.append('file', file); return request.post('/me/import', data, { timeout: 300000 }) },
  file: (id, inline = false) => request.get(`/documents/${id}/file`, { params: { inline }, responseType: 'blob' }),
  preview: (id, page = 1) => request.get(`/documents/${id}/preview`, { params: { page } }),
}

export function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = name; document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
