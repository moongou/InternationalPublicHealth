import { authenticatedFetch } from './auth'
import type { Alert, Country, DiseaseEvent, Port, RuleDefinition, Stats, TransferLink, TransferTask, TrendPoint } from './types'

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(path, init)
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `请求失败（HTTP ${response.status}）`)
  }
  if (response.status === 204) return undefined as T
  return await response.json() as T
}

export interface AppData {
  stats: Stats
  countries: Country[]
  events: DiseaseEvent[]
  alerts: Alert[]
  trend: TrendPoint[]
  links: TransferLink[]
  rules: RuleDefinition[]
  transfers: TransferTask[]
  connected: boolean
}

export async function loadAppData(mode: 'internet' | 'intranet'): Promise<AppData> {
  const [stats, countries, eventPage, alerts, riskData, links, rules, transfers] = await Promise.all([
    requestJson<Stats>('/stats'),
    requestJson<Country[]>('/countries'),
    requestJson<{ items: DiseaseEvent[] }>('/events?page_size=100'),
    requestJson<Alert[]>('/alerts'),
    requestJson<{ history: TrendPoint[] }>('/risk-scores'),
    requestJson<TransferLink[]>('/map/transfer-links'),
    requestJson<RuleDefinition[]>('/rules'),
    mode === 'internet' ? requestJson<TransferTask[]>('/transfer/tasks') : Promise.resolve([]),
  ])
  return { stats, countries, events: eventPage.items, alerts, trend: riskData.history, links, rules, transfers, connected: true }
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  return requestJson(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })
}

export async function uploadFile<T>(path: string, file: File): Promise<T> {
  const form = new FormData(); form.append('file', file)
  const response = await authenticatedFetch(path, { method: 'POST', body: form, headers: {} })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `上传失败（HTTP ${response.status}）`)
  }
  return response.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// 口岸库（海、陆、空、铁全量口岸）
// ---------------------------------------------------------------------------
export async function listPorts(filters: { port_type?: string; risk_level?: string } = {}): Promise<{ items: Port[]; total: number }> {
  const params = new URLSearchParams()
  if (filters.port_type) params.set('port_type', filters.port_type)
  if (filters.risk_level) params.set('risk_level', filters.risk_level)
  const query = params.toString()
  return requestJson<{ items: Port[]; total: number }>(`/ports?page_size=2000${query ? `&${query}` : ''}`)
}

export async function createPort(body: { name: string; port_type: Port['port_type']; longitude: number; latitude: number; risk_level: Port['risk_level']; enabled: boolean }): Promise<Port> {
  return postJson<Port>('/ports', body)
}

export async function updatePort(portId: string, body: Partial<{ name: string; port_type: Port['port_type']; longitude: number; latitude: number; risk_level: Port['risk_level']; enabled: boolean }>): Promise<Port> {
  return requestJson<Port>(`/ports/${portId}`, { method: 'PATCH', body: JSON.stringify(body) })
}

export async function deletePort(portId: string): Promise<void> {
  await requestJson<void>(`/ports/${portId}`, { method: 'DELETE' })
}

export async function importPorts(file: File): Promise<{ imported: number; skipped: number; errors: string[]; total: number }> {
  return uploadFile<{ imported: number; skipped: number; errors: string[]; total: number }>('/ports/import', file)
}

export async function exportPorts(): Promise<{ filename: string; csv: string; total: number }> {
  return requestJson<{ filename: string; csv: string; total: number }>('/ports/export')
}
