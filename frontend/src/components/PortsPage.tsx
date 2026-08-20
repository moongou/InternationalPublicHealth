import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { Anchor, CheckCircle2, FileDown, FileUp, Filter, MapPin, Pencil, Plus, Search, Trash2, X } from 'lucide-react'
import type { Port, PortType, RiskLevel } from '../types'
import { levelMeta } from '../utils'
import { createPort, deletePort, exportPorts, importPorts, listPorts, updatePort } from '../api'

const portTypeMeta: Record<PortType, { label: string; hint: string }> = {
  sea: { label: '海港', hint: 'SEA' },
  land: { label: '陆路', hint: 'LAND' },
  air: { label: '空港', hint: 'AIR' },
  rail: { label: '铁路', hint: 'RAIL' },
}

interface PortForm {
  name: string
  port_type: PortType
  longitude: string
  latitude: string
  risk_level: RiskLevel
  enabled: boolean
}

const emptyForm: PortForm = { name: '', port_type: 'air', longitude: '', latitude: '', risk_level: 'blue', enabled: true }

export default function PortsPage({ connected }: { connected: boolean }) {
  const [ports, setPorts] = useState<Port[]>([])
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState<'all' | PortType>('all')
  const [riskFilter, setRiskFilter] = useState<'all' | RiskLevel>('all')
  const [modal, setModal] = useState(false)
  const [editing, setEditing] = useState<Port | null>(null)
  const [form, setForm] = useState<PortForm>(emptyForm)
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = () => listPorts()
    .then(result => setPorts(result.items))
    .catch(error => setToast(error instanceof Error ? error.message : '口岸库加载失败'))

  useEffect(() => { if (connected) { load() } }, [connected])

  const filtered = useMemo(() => ports.filter(port =>
    (typeFilter === 'all' || port.port_type === typeFilter) &&
    (riskFilter === 'all' || port.risk_level === riskFilter) &&
    (!query || port.name.toLowerCase().includes(query.toLowerCase()))
  ), [ports, query, typeFilter, riskFilter])

  const stats = useMemo(() => ({
    total: ports.length,
    air: ports.filter(p => p.port_type === 'air').length,
    sea: ports.filter(p => p.port_type === 'sea').length,
    land: ports.filter(p => p.port_type === 'land').length,
    rail: ports.filter(p => p.port_type === 'rail').length,
    highRisk: ports.filter(p => p.risk_level === 'red' || p.risk_level === 'orange').length,
  }), [ports])

  const openCreate = () => { setEditing(null); setForm(emptyForm); setModal(true) }
  const openEdit = (port: Port) => {
    setEditing(port)
    setForm({ name: port.name, port_type: port.port_type, longitude: String(port.longitude), latitude: String(port.latitude), risk_level: port.risk_level, enabled: port.enabled })
    setModal(true)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const longitude = Number(form.longitude)
    const latitude = Number(form.latitude)
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) { setToast('经度需在 -180 ~ 180 之间'); return }
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) { setToast('纬度需在 -90 ~ 90 之间'); return }
    setBusy(true)
    try {
      if (editing) {
        const updated = await updatePort(editing.port_id, { name: form.name, port_type: form.port_type, longitude, latitude, risk_level: form.risk_level, enabled: form.enabled })
        setPorts(current => current.map(p => p.port_id === updated.port_id ? updated : p))
        setToast('口岸信息已更新')
      } else {
        const created = await createPort({ name: form.name, port_type: form.port_type, longitude, latitude, risk_level: form.risk_level, enabled: form.enabled })
        setPorts(current => [...current, created])
        setToast(`已新增口岸「${created.name}」`)
      }
      setModal(false)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '保存失败')
    } finally {
      setBusy(false); setTimeout(() => setToast(''), 3000)
    }
  }

  const remove = async (port: Port) => {
    if (!window.confirm(`确认删除口岸「${port.name}」？`)) return
    setBusy(true)
    try {
      await deletePort(port.port_id)
      setPorts(current => current.filter(p => p.port_id !== port.port_id))
      setToast(`已删除口岸「${port.name}」`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '删除失败')
    } finally {
      setBusy(false); setTimeout(() => setToast(''), 3000)
    }
  }

  const importFile = async (file: File) => {
    setBusy(true)
    try {
      const result = await importPorts(file)
      await load()
      setToast(`导入完成：新增 ${result.imported} 条${result.skipped ? `，跳过 ${result.skipped} 条` : ''}${result.errors.length ? `，异常 ${result.errors.length} 条` : ''}`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : 'CSV 导入失败')
    } finally {
      setBusy(false); if (fileRef.current) fileRef.current.value = ''; setTimeout(() => setToast(''), 4000)
    }
  }

  const exportFile = async () => {
    setBusy(true)
    try {
      const result = await exportPorts()
      const blob = new Blob(['\uFEFF' + result.csv], { type: 'text/csv;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setToast(`已导出 ${result.total} 个口岸`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '导出失败')
    } finally {
      setBusy(false); setTimeout(() => setToast(''), 3000)
    }
  }

  return <div className="business-page page-enter ports-page">
    <section className="page-heading compact-heading">
      <div><span className="eyebrow">PORT REGISTRY · INTRANET</span><h1>中国口岸库</h1><p>海、陆、空、铁全量口岸的统一台账，支撑入境风险分级布控与全国多层级口岸地图。</p></div>
      <div className="heading-actions">
        <button className="secondary-button" disabled={busy} onClick={() => fileRef.current?.click()}><FileUp size={16}/>CSV 导入</button>
        <input ref={fileRef} hidden type="file" accept=".csv" onChange={event => event.target.files?.[0] && importFile(event.target.files[0])} />
        <button className="secondary-button" disabled={busy} onClick={exportFile}><FileDown size={16}/>CSV 导出</button>
        <button className="primary-button" disabled={busy} onClick={openCreate}><Plus size={16}/>新增口岸</button>
      </div>
    </section>

    <section className="ports-kpis">
      <article><span className="round-icon cyan"><Anchor size={20}/></span><div><small>口岸总数</small><strong>{stats.total}</strong><em>海陆空铁全覆盖</em></div></article>
      <article><span className="round-icon blue"><MapPin size={20}/></span><div><small>空港</small><strong>{stats.air}</strong><em>国际航空口岸</em></div></article>
      <article><span className="round-icon orange"><MapPin size={20}/></span><div><small>海港</small><strong>{stats.sea}</strong><em>国际海运口岸</em></div></article>
      <article><span className="round-icon yellow"><MapPin size={20}/></span><div><small>陆路</small><strong>{stats.land}</strong><em>边境陆路口岸</em></div></article>
      <article><span className="round-icon red"><MapPin size={20}/></span><div><small>铁路</small><strong>{stats.rail}</strong><em>铁路口岸</em></div></article>
      <article><span className="round-icon red"><CheckCircle2 size={20}/></span><div><small>高/较高风险</small><strong>{stats.highRisk}</strong><em>红 / 橙色口岸</em></div></article>
    </section>

    <section className="panel ports-table-panel">
      <header className="panel__header"><div><span className="panel__eyebrow">PORT DIRECTORY</span><h2>口岸台账</h2></div><span className="live-label"><i/>全量口岸库</span></header>
      <div className="table-toolbar">
        <label className="table-search"><Search size={16}/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="搜索口岸名称"/></label>
        <label className="toolbar-button"><Filter size={15}/><select value={typeFilter} onChange={e => setTypeFilter(e.target.value as 'all' | PortType)}><option value="all">全部类型</option>{(Object.keys(portTypeMeta) as PortType[]).map(t => <option key={t} value={t}>{portTypeMeta[t].label}</option>)}</select></label>
        <label className="toolbar-button"><Filter size={15}/><select value={riskFilter} onChange={e => setRiskFilter(e.target.value as 'all' | RiskLevel)}><option value="all">全部风险</option>{(['red','orange','yellow','blue'] as RiskLevel[]).map(level => <option key={level} value={level}>{levelMeta[level].label}色</option>)}</select></label>
      </div>
      <div className="ports-table">
        <div className="ports-table__head"><span>口岸名称</span><span>类型</span><span>经纬度</span><span>风险等级</span><span>状态</span><span/></div>
        {filtered.map(port => <div key={port.port_id} className="ports-row">
          <span className="port-name"><span className="avatar small">{port.name.slice(0, 1)}</span><span><b>{port.name}</b><small>{port.port_id}</small></span></span>
          <span><span className={`port-type-badge port-type-badge--${port.port_type}`}>{portTypeMeta[port.port_type].label}</span></span>
          <span className="port-coord"><b>{port.longitude.toFixed(4)}°E</b><small>{port.latitude.toFixed(4)}°N</small></span>
          <span><span className={`level-pill level-pill--${port.risk_level}`}>{levelMeta[port.risk_level].label}</span></span>
          <span><span className={`status-dot ${port.enabled ? 'is-on' : 'is-off'}`}><i/>{port.enabled ? '启用' : '停用'}</span></span>
          <span className="port-actions">
            <button className="icon-button" title="编辑" onClick={() => openEdit(port)}><Pencil size={15}/></button>
            <button className="icon-button danger" title="删除" onClick={() => remove(port)}><Trash2 size={15}/></button>
          </span>
        </div>)}
        {!filtered.length && <div className="empty-state"><Anchor size={30}/><b>{connected ? '暂无匹配口岸' : '口岸服务未连接'}</b></div>}
      </div>
      <div className="table-footer"><span>当前显示 {filtered.length} 个 / 共 {stats.total} 个口岸</span></div>
    </section>

    {modal && <div className="modal-layer"><button className="modal-backdrop" onClick={() => setModal(false)}/>
      <form className="modal-card port-form" onSubmit={submit}>
        <header><div><span className="panel__eyebrow">{editing ? 'EDIT PORT' : 'NEW PORT'}</span><h2>{editing ? '编辑口岸' : '新增口岸'}</h2></div><button type="button" className="icon-button" onClick={() => setModal(false)}><X size={19}/></button></header>
        <div className="form-grid">
          <label><span>口岸名称</span><input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="例如：满洲里铁路口岸"/></label>
          <label><span>口岸类型</span><select value={form.port_type} onChange={e => setForm({ ...form, port_type: e.target.value as PortType })}>{(Object.keys(portTypeMeta) as PortType[]).map(t => <option key={t} value={t}>{portTypeMeta[t].label}</option>)}</select></label>
          <label><span>经度（-180 ~ 180）</span><input required inputMode="decimal" value={form.longitude} onChange={e => setForm({ ...form, longitude: e.target.value })} placeholder="例如：117.72"/></label>
          <label><span>纬度（-90 ~ 90）</span><input required inputMode="decimal" value={form.latitude} onChange={e => setForm({ ...form, latitude: e.target.value })} placeholder="例如：39.00"/></label>
          <label><span>入境风险等级</span><select value={form.risk_level} onChange={e => setForm({ ...form, risk_level: e.target.value as RiskLevel })}>{(['red','orange','yellow','blue'] as RiskLevel[]).map(level => <option key={level} value={level}>{levelMeta[level].label}色风险</option>)}</select></label>
          <label className="checkbox-label"><input type="checkbox" checked={form.enabled} onChange={e => setForm({ ...form, enabled: e.target.checked })}/><span><b>启用该口岸</b><small>停用后将不在地图与布控中展示</small></span></label>
        </div>
        <footer><button type="button" className="secondary-button" onClick={() => setModal(false)}>取消</button><button className="primary-button"><Anchor size={16}/>{editing ? '保存修改' : '确认新增'}</button></footer>
      </form>
    </div>}
    {toast && <div className="toast success"><CheckCircle2 size={16}/>{toast}</div>}
  </div>
}
