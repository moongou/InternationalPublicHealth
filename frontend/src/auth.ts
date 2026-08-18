const API = import.meta.env.VITE_API_BASE ?? '/api/v1'
const platform = import.meta.env.MODE === 'intranet' ? 'intranet' : 'internet'
const storageKey = `global-health:${platform}:session`
const idleTimeoutMs = Number(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES ?? 30) * 60_000

export interface SessionUser {
  user_id: string
  username: string
  display_name: string
  role: 'system_admin' | 'data_analyst' | 'port_operator' | 'auditor' | 'read_only'
}

interface StoredSession {
  access_token: string
  refresh_token: string
  expires_at: number
  last_activity: number
  user: SessionUser
}

export function getSession(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(storageKey)
    return raw ? JSON.parse(raw) as StoredSession : null
  } catch {
    return null
  }
}

export function clearSession() {
  sessionStorage.removeItem(storageKey)
}

export async function login(username: string, password: string, otp?: string): Promise<SessionUser> {
  const response = await fetch(`${API}/auth/login`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, otp: otp || undefined }), signal: AbortSignal.timeout(8000),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? '登录失败')
  }
  const body = await response.json() as { access_token: string; refresh_token: string; expires_in: number; user: SessionUser }
  sessionStorage.setItem(storageKey, JSON.stringify({
    access_token: body.access_token, refresh_token: body.refresh_token,
    expires_at: Date.now() + body.expires_in * 1000, user: body.user,
    last_activity: Date.now(),
  } satisfies StoredSession))
  return body.user
}

async function refresh(): Promise<string | null> {
  const session = getSession()
  if (!session?.refresh_token) return null
  const response = await fetch(`${API}/auth/refresh`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: session.refresh_token }), signal: AbortSignal.timeout(8000),
  })
  if (!response.ok) { clearSession(); return null }
  const body = await response.json() as { access_token: string; refresh_token: string; expires_in: number }
  sessionStorage.setItem(storageKey, JSON.stringify({ ...session, access_token: body.access_token, refresh_token: body.refresh_token, expires_at: Date.now() + body.expires_in * 1000 }))
  return body.access_token
}

export async function authenticatedFetch(path: string, init?: RequestInit, allowRefresh = true): Promise<Response> {
  let session = getSession()
  if (!session) throw new Error('AUTH_REQUIRED')
  if (Date.now() - (session.last_activity ?? 0) > idleTimeoutMs) {
    clearSession()
    throw new Error('AUTH_REQUIRED')
  }
  if (session.expires_at <= Date.now() + 15_000) {
    const token = await refresh()
    if (!token) throw new Error('AUTH_REQUIRED')
    session = getSession()
  }
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  headers.set('Authorization', `Bearer ${session?.access_token}`)
  const response = await fetch(`${API}${path}`, {
    signal: AbortSignal.timeout(10_000), ...init,
    headers,
  })
  const current = getSession()
  if (current) sessionStorage.setItem(storageKey, JSON.stringify({ ...current, last_activity: Date.now() }))
  if (response.status === 401 && allowRefresh) {
    const token = await refresh()
    if (token) return authenticatedFetch(path, init, false)
    throw new Error('AUTH_REQUIRED')
  }
  return response
}
