import { authenticatedFetch } from './auth'
import type { Alert, Country, DiseaseEvent, RuleDefinition, Stats, TransferLink, TransferTask, TrendPoint } from './types'

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
