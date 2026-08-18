import { useCallback, useEffect, useState } from 'react'
import { loadAppData, type AppData } from './api'
import { clearSession, getSession, type SessionUser } from './auth'

export function usePlatform(mode: 'internet' | 'intranet') {
  const [user, setUser] = useState<SessionUser | null>(() => getSession()?.user ?? null)
  const [data, setData] = useState<AppData | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    if (!user) return
    setError('')
    try { setData(await loadAppData(mode)) }
    catch (reason) {
      if (reason instanceof Error && reason.message === 'AUTH_REQUIRED') { clearSession(); setUser(null); setData(null) }
      else setError(reason instanceof Error ? reason.message : '业务数据加载失败')
    }
  }, [mode, user])
  useEffect(() => { load() }, [load])
  const logout = () => { clearSession(); setUser(null); setData(null) }
  return { user, data, error, login: setUser, logout, reload: load }
}
