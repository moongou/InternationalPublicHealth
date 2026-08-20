export type RiskLevel = 'red' | 'orange' | 'yellow' | 'blue'
export type PortType = 'sea' | 'land' | 'air' | 'rail'

export interface Port {
  port_id: string
  name: string
  port_type: PortType
  longitude: number
  latitude: number
  risk_level: RiskLevel
  enabled: boolean
  updated_at: string
}

export interface Country {
  code: string
  name: string
  region: string
  center: [number, number]
  risk_score: number
  level: RiskLevel
  active_cases: number
  deaths: number
  trend_7d: number
  factors: Record<string, number>
  updated_at: string
}

export interface DiseaseEvent {
  id: string
  title: string
  country_code: string
  country: string
  disease: string
  event_type: string
  cases: number
  deaths: number
  level: RiskLevel
  source: string
  source_url?: string
  published_at: string
  confidence: number
  coordinates: [number, number]
}

export interface Alert {
  id: string
  title: string
  level: RiskLevel
  country: string
  disease: string
  score: number
  status: string
  issued_at: string
  advice: string
}

export interface TrendPoint {
  date: string
  global: number
  asia: number
  africa: number
  americas: number
}

export interface TransferLink {
  id: string
  origin: string
  destination: string
  source: [number, number]
  target: [number, number]
  risk: number
  volume: number
  via: string
}

export interface Stats {
  monitored_countries: number
  active_events: number
  new_events_24h: number
  active_alerts: number
  high_risk_countries: number
  passengers_screened_today: number
  last_updated: string
  level_distribution: Record<RiskLevel, number>
  source_health: { healthy: number; degraded: number; offline: number }
}

export interface RuleDefinition {
  rule_id: string
  rule_key?: string
  name: string
  type: string
  description: string
  condition_json: Record<string, unknown>
  action_json: Record<string, unknown>
  version: number
  status: 'published' | 'draft' | 'disabled' | 'retired'
  priority: number
  updated_at: string
}

export interface TransferTask {
  task_id: string
  package_id: string
  channel: 'file' | 'message_queue' | 'api_polling'
  data_type: 'full' | 'incremental'
  status: 'completed' | 'transferring' | 'pending' | 'failed'
  records: number
  size: number
  progress: number
  created_at: string
  completed_at: string | null
}

export interface PassengerRecord {
  passenger_id: string
  name: string
  document_number: string
  nationality: string
  entry_port: string
  entry_time: string
  flight_no?: string
  health_declaration: boolean
  travel_history: Array<{ country: string; entry_date: string; exit_date: string }>
  transit_countries: string[]
  risk_analysis: {
    score: number
    level: RiskLevel
    reasons: string[]
    advice: string[]
    matched_at: string
    rule_version: string
  }
}

export type PageId = 'dashboard' | 'sources' | 'events' | 'risk' | 'passengers' | 'transfer' | 'rules' | 'admin' | 'ports'
