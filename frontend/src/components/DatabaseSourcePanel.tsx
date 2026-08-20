import { FormEvent, useState } from 'react'
import { CheckCircle2, Database, Gauge, RefreshCw, Table2, X, Zap } from 'lucide-react'
import { postJson } from '../api'
import type { PassengerRecord } from '../types'

export type DbType = 'mysql' | 'postgresql' | 'mssql' | 'oracle' | 'clickhouse' | 'maxcompute'

interface DbConfig {
  host: string; port: string; database: string; user: string; password: string
  endpoint: string; project: string; access_id: string; access_key: string; tunnel_endpoint: string
}

interface TestResult { status: string; latency_ms: number; message: string; db_type: string }
interface SyncResult {
  total_rows: number; matched: number; skipped_fields: number; duplicate: number; imported: number
  column_mapping: Record<string, string>; items: PassengerRecord[]
}

// 丰富数据库提供商预设，对齐 DeepAnalyze 的数据库连接能力
const DB_PRESETS: { id: string; label: string; hint: string; db_type: DbType }[] = [
  { id: 'mysql', label: 'MySQL', hint: '通用 MySQL 5.7 / 8.0', db_type: 'mysql' },
  { id: 'rds_mysql', label: '阿里云 RDS MySQL', hint: '云数据库 RDS MySQL 版', db_type: 'mysql' },
  { id: 'polardb_mysql', label: '阿里云 PolarDB MySQL', hint: '云原生数据库 PolarDB', db_type: 'mysql' },
  { id: 'analyticdb_mysql', label: '阿里云 AnalyticDB (ADS) MySQL', hint: '云原生数仓 ADS MySQL 兼容版', db_type: 'mysql' },
  { id: 'analyticdb_pg', label: '阿里云 AnalyticDB (ADS) PostgreSQL', hint: '云原生数仓 ADS PG 兼容版', db_type: 'postgresql' },
  { id: 'postgresql', label: 'PostgreSQL', hint: '通用 PostgreSQL', db_type: 'postgresql' },
  { id: 'rds_pg', label: '阿里云 RDS PostgreSQL', hint: '云数据库 RDS PG 版', db_type: 'postgresql' },
  { id: 'maxcompute', label: '阿里云 MaxCompute / ODPS', hint: '通过 pyodps 连接，Endpoint + Project + AK', db_type: 'maxcompute' },
  { id: 'mssql', label: 'SQL Server', hint: 'Microsoft SQL Server', db_type: 'mssql' },
  { id: 'oracle', label: 'Oracle', hint: 'Oracle Database', db_type: 'oracle' },
  { id: 'clickhouse', label: 'ClickHouse', hint: '列式分析数据库', db_type: 'clickhouse' },
]

const DB_LABELS: Record<DbType, string> = {
  mysql: 'MySQL', postgresql: 'PostgreSQL', mssql: 'SQL Server', oracle: 'Oracle', clickhouse: 'ClickHouse', maxcompute: 'MaxCompute / ODPS',
}

const emptyConfig: DbConfig = {
  host: '', port: '', database: '', user: '', password: '',
  endpoint: '', project: '', access_id: '', access_key: '', tunnel_endpoint: '',
}

const defaultPort = (type: DbType) => ({ mysql: '3306', postgresql: '5432', mssql: '1433', oracle: '1521', clickhouse: '8123', maxcompute: '' })[type]

export default function DatabaseSourcePanel({ onImported }: { onImported: (records: PassengerRecord[]) => void }) {
  const [dbType, setDbType] = useState<DbType>('maxcompute')
  const [presetId, setPresetId] = useState('maxcompute')
  const [config, setConfig] = useState<DbConfig>(emptyConfig)
  const [busy, setBusy] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [tables, setTables] = useState<string[]>([])
  const [selectedTable, setSelectedTable] = useState('')
  const [syncResult, setSyncResult] = useState<SyncResult | null>(null)
  const [toast, setToast] = useState('')
  const notify = (message: string) => { setToast(message); setTimeout(() => setToast(''), 4000) }

  const isMaxCompute = dbType === 'maxcompute'

  const applyPreset = (id: string) => {
    setPresetId(id)
    const preset = DB_PRESETS.find((item) => item.id === id)
    if (!preset) { setConfig(emptyConfig); return }
    setDbType(preset.db_type)
    setConfig((current) => ({ ...current, port: defaultPort(preset.db_type), database: '', host: '', user: '', password: '', endpoint: '', project: '', access_id: '', access_key: '', tunnel_endpoint: '' }))
  }

  const payload = () => ({ db_type: dbType, config })

  const test = async () => {
    setBusy('test'); setTestResult(null)
    try {
      const result = await postJson<TestResult>('/database-sources/test', payload())
      setTestResult(result); notify(`连接成功（${result.latency_ms} ms）`)
    } catch (error) { notify(error instanceof Error ? error.message : '连接测试失败') }
    finally { setBusy('') }
  }

  const listTables = async () => {
    setBusy('tables'); setTables([]); setSelectedTable('')
    try {
      const result = await postJson<{ tables: string[]; total: number }>('/database-sources/tables', payload())
      setTables(result.tables); notify(`发现 ${result.total} 张数据表`)
    } catch (error) { notify(error instanceof Error ? error.message : '列出数据表失败') }
    finally { setBusy('') }
  }

  const sync = async (event: FormEvent) => {
    event.preventDefault()
    if (!selectedTable) { notify('请先选择要同步的数据表'); return }
    setBusy('sync'); setSyncResult(null)
    try {
      const result = await postJson<SyncResult>('/database-sources/sync', { db_type: dbType, config, table: selectedTable, limit: 5000 })
      setSyncResult(result); onImported(result.items)
      notify(`同步完成：导入 ${result.imported} 条，跳过重复 ${result.duplicate} 条`)
    } catch (error) { notify(error instanceof Error ? error.message : '同步旅客数据失败') }
    finally { setBusy('') }
  }

  const set = (key: keyof DbConfig, value: string) => setConfig((current) => ({ ...current, [key]: value }))

  return <section className="panel db-source-panel">
    <header className="panel__header"><div><span className="panel__eyebrow">DATABASE SOURCE · PASSENGER</span><h2>旅客数据库连接</h2><p>广泛连接旅客数据库，支持阿里云 MaxCompute / ODPS、AnalyticDB（ADS）、MySQL、PostgreSQL 等，受控同步旅客风险数据。</p></div></header>

    <div className="db-source-body">
      <label><span>数据库提供商</span><select value={presetId} onChange={(event) => applyPreset(event.target.value)}>{DB_PRESETS.map((item) => <option key={item.id} value={item.id}>{item.label} · {item.hint}</option>)}</select></label>

      {isMaxCompute ? <>
        <label><span>Endpoint 地址</span><input value={config.endpoint} onChange={(e) => set('endpoint', e.target.value)} placeholder="例如 https://service.cn-shanghai.maxcompute.aliyun.com/api"/></label>
        <label><span>Project 名称</span><input value={config.project} onChange={(e) => set('project', e.target.value)} placeholder="例如 my_project"/></label>
        <label><span>AccessKey ID</span><input value={config.access_id} onChange={(e) => set('access_id', e.target.value)} placeholder="阿里云 AccessKey ID"/></label>
        <label><span>AccessKey Secret</span><input type="password" autoComplete="new-password" value={config.access_key} onChange={(e) => set('access_key', e.target.value)} placeholder="阿里云 AccessKey Secret"/></label>
        <label><span>Tunnel Endpoint（可选）</span><input value={config.tunnel_endpoint} onChange={(e) => set('tunnel_endpoint', e.target.value)} placeholder="例如 https://dt.cn-shanghai.maxcompute.aliyun.com"/></label>
      </> : <>
        <div className="form-grid">
          <label><span>主机地址</span><input value={config.host} onChange={(e) => set('host', e.target.value)} placeholder="例如 rm-xxx.mysql.rds.aliyuncs.com"/></label>
          <label><span>端口</span><input value={config.port} onChange={(e) => set('port', e.target.value)} placeholder={defaultPort(dbType)}/></label>
        </div>
        <label><span>数据库名</span><input value={config.database} onChange={(e) => set('database', e.target.value)} placeholder="数据库 / Schema 名称"/></label>
        <div className="form-grid">
          <label><span>用户名</span><input value={config.user} onChange={(e) => set('user', e.target.value)} placeholder="数据库账号"/></label>
          <label><span>密码</span><input type="password" autoComplete="new-password" value={config.password} onChange={(e) => set('password', e.target.value)} placeholder="数据库密码"/></label>
        </div>
      </>}

      <div className="db-source-actions">
        <button className="secondary-button" disabled={!!busy} onClick={test}><Zap size={15}/>{busy === 'test' ? '测试中…' : '测试连接'}</button>
        <button className="secondary-button" disabled={!!busy} onClick={listTables}><Table2 size={15}/>{busy === 'tables' ? '读取中…' : '获取数据表'}</button>
      </div>

      {testResult && <div className="db-test-result"><span className={testResult.status === 'success' ? 'result-ok' : 'result-fail'}>{testResult.status === 'success' ? <CheckCircle2 size={14}/> : <X size={14}/>}</span><b>{DB_LABELS[testResult.db_type as DbType] ?? testResult.db_type}</b><em><Gauge size={12}/>{testResult.latency_ms} ms</em><small>{testResult.message}</small></div>}

      {tables.length > 0 && <form className="db-sync-form" onSubmit={sync}>
        <label><span>选择数据表（旅客记录表）</span><div className="db-table-pick"><select value={selectedTable} onChange={(e) => setSelectedTable(e.target.value)}><option value="">请选择数据表…</option>{tables.map((t) => <option key={t} value={t}>{t}</option>)}</select><button className="primary-button" disabled={busy === 'sync'}><RefreshCw size={15}/>{busy === 'sync' ? '同步中…' : '同步旅客数据'}</button></div></label>
      </form>}

      {syncResult && <div className="db-sync-result">
        <b><CheckCircle2 size={14}/>同步完成</b>
        <div className="db-sync-stats"><span>总行数 <strong>{syncResult.total_rows}</strong></span><span>匹配字段 <strong>{syncResult.matched}</strong></span><span>字段缺失跳过 <strong>{syncResult.skipped_fields}</strong></span><span>重复跳过 <strong>{syncResult.duplicate}</strong></span><span>新导入 <strong>{syncResult.imported}</strong></span></div>
        {Object.keys(syncResult.column_mapping).length > 0 && <details className="db-column-map"><summary>字段映射（{Object.keys(syncResult.column_mapping).length} 项）</summary><ul>{Object.entries(syncResult.column_mapping).map(([field, col]) => <li key={field}><code>{field}</code> ← <code>{col}</code></li>)}</ul></details>}
      </div>}
    </div>

    {toast && <div className="toast success"><Database size={16}/>{toast}</div>}
  </section>
}
