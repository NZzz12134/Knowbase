import { defineStore } from 'pinia'
import { sessionApi } from '../api/session'

const activeLoads = new WeakMap()

export const useSessionStore = defineStore('session', {
  state: () => ({
    sessions: [],
    currentId: null,
    loaded: false,
    loading: false,
    loadError: '',
  }),
  actions: {
    async fetchSessions({ retry = false, signal } = {}) {
      const token = localStorage.getItem('token')
      const requestId = Symbol()
      activeLoads.set(this, requestId)
      const stale = () => signal?.aborted || token !== localStorage.getItem('token') || activeLoads.get(this) !== requestId
      this.loading = true
      this.loadError = ''
      try {
        for (let attempt = 0; ; attempt++) {
          try {
            const data = await sessionApi.list({ page: 1, page_size: 100 }, {
              signal, skipErrorNotification: true, ...(retry ? { timeout: 10000 } : {}),
            })
            if (stale()) return []
            this.sessions = data.items
            this.loaded = true
            return data.items
          } catch (error) {
            if (stale()) return []
            const status = error.response?.status
            if (!retry || attempt >= 2 || (status && ![502, 503, 504].includes(status))) throw error
            // API 刚启动时可能尚未就绪；只对网络错误和网关错误做有限重试。
            await new Promise(resolve => {
              const finish = () => { clearTimeout(timer); signal?.removeEventListener('abort', finish); resolve() }
              const timer = setTimeout(finish, [400, 1200][attempt])
              signal?.addEventListener('abort', finish, { once: true })
            })
            if (stale()) return []
          }
        }
      } catch (error) {
        if (!stale()) this.loadError = '最近对话加载失败，请重试。'
        throw error
      } finally {
        if (activeLoads.get(this) === requestId) this.loading = false
      }
    },
    async createSession(title, kbId = null) {
      const session = await sessionApi.create({ title, kb_id: kbId })
      this.sessions.unshift(session)
      this.currentId = session.id
      return session
    },
    async renameSession(id, title) {
      await sessionApi.rename(id, title)
      const s = this.sessions.find((x) => x.id === id)
      if (s) s.title = title
    },
    async removeSession(id) {
      await sessionApi.remove(id)
      this.sessions = this.sessions.filter((x) => x.id !== id)
      if (this.currentId === id) {
        // 删除当前会话后自动选中剩余第一个，避免回到空欢迎页
        this.currentId = this.sessions.length ? this.sessions[0].id : null
      }
    },
    setCurrent(id) {
      this.currentId = id
    },
  },
})
