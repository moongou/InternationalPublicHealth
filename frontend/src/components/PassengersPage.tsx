import { FormEvent, useEffect, useMemo, useRef, useState } from 'react'
import { AlertTriangle, ArrowRight, BadgeCheck, CheckCircle2, ChevronRight, FileUp, Filter, Plane, Plus, Search, ShieldCheck, Siren, UserRoundCheck, UsersRound, X } from 'lucide-react'
import type { Country, PassengerRecord, RiskLevel } from '../types'
import { levelMeta } from '../utils'
import { postJson, requestJson, uploadFile } from '../api'

interface PassengerRow {
  id: string; name: string; document: string; nationality: string; origin: string; transit: string; port: string; flight: string; time: string; score: number; level: RiskLevel; declaration: boolean; reasons: string[]; ruleVersion: string; matchedAt: string
}

const toRow = (record: PassengerRecord): PassengerRow => ({
  id:record.passenger_id,name:record.name,document:record.document_number,nationality:record.nationality,
  origin:record.travel_history[0]?.country??'—',transit:record.transit_countries.join('、')||'—',port:record.entry_port,
  flight:record.flight_no||'—',time:new Date(record.entry_time).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false}),
  score:record.risk_analysis.score,level:record.risk_analysis.level,declaration:record.health_declaration,reasons:record.risk_analysis.reasons,
  ruleVersion:record.risk_analysis.rule_version,matchedAt:record.risk_analysis.matched_at,
})

export default function PassengersPage({ countries, connected }: { countries: Country[]; connected: boolean }) {
  const [rows, setRows] = useState<PassengerRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [query, setQuery] = useState('')
  const [riskFilter, setRiskFilter] = useState<'all'|RiskLevel>('all')
  const [selected, setSelected] = useState<PassengerRow | null>(null)
  const [modal, setModal] = useState(false)
  const [toast, setToast] = useState('')
  const [busy, setBusy] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState({ name:'', document:'', nationality:'中国', origin:'印度', transit:'', port:'北京首都国际机场', flight:'', declaration:true })
  const filtered = useMemo(() => rows.filter((row) => (riskFilter==='all'||row.level===riskFilter)&&(!query || `${row.name}${row.document}${row.origin}${row.flight}`.toLowerCase().includes(query.toLowerCase()))), [rows, query, riskFilter])
  useEffect(()=>{if(!connected)return;requestJson<{items:PassengerRecord[];total:number}>('/passengers?page=1&page_size=200').then(result=>{const loaded=result.items.map(toRow);setRows(loaded);setTotal(result.total);setPage(1);setSelected(loaded[0]??null)}).catch(error=>setToast(error instanceof Error?error.message:'旅客记录加载失败'))},[connected])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    try {
      const arrival = new Date()
      const tripEntry = new Date(arrival); tripEntry.setDate(tripEntry.getDate() - 10)
      const tripExit = new Date(arrival); tripExit.setDate(tripExit.getDate() - 1)
      const dateOnly = (value: Date) => value.toISOString().slice(0, 10)
      if(!connected)throw new Error('旅客风险服务未连接')
      const passengerId = `PAX-${dateOnly(arrival).replaceAll('-', '')}-${Date.now().toString().slice(-6)}`
      const response = await postJson<{items: PassengerRecord[]}>('/passengers', {
        passenger_id: passengerId, document_type: '护照', document_number: form.document, name: form.name,
        nationality: form.nationality, travel_history: [{ country: form.origin, entry_date: dateOnly(tripEntry), exit_date: dateOnly(tripExit) }],
        transit_countries: form.transit ? [form.transit] : [], entry_port: form.port, entry_time: arrival.toISOString(),
        flight_no: form.flight || null, health_declaration: form.declaration,
      })
      const row = toRow(response.items[0])
      setRows((current) => [row, ...current]);setTotal(value=>value+1);setSelected(row);setModal(false);setToast(`风险匹配完成：${levelMeta[row.level].label}色风险 ${row.score} 分`)
    } catch (error) {
      setToast(error instanceof Error ? error.message : '旅客风险匹配失败')
    } finally {
      setBusy(false); setTimeout(() => setToast(''), 3000)
    }
  }
  const importFile=async(file:File)=>{setBusy(true);try{const response=await uploadFile<{items:PassengerRecord[];total:number}>('/passengers/import',file);const imported=response.items.map(toRow);setRows(current=>[...imported,...current]);setTotal(value=>value+response.total);setSelected(imported[0]??selected);setToast(`成功导入并匹配 ${response.total} 名旅客`)}catch(error){setToast(error instanceof Error?error.message:'批量导入失败')}finally{setBusy(false);if(fileRef.current)fileRef.current.value='';setTimeout(()=>setToast(''),3000)}}
  const loadMore=async()=>{if(busy||rows.length>=total)return;setBusy(true);try{const next=page+1;const result=await requestJson<{items:PassengerRecord[];total:number}>(`/passengers?page=${next}&page_size=200`);setRows(current=>[...current,...result.items.map(toRow)]);setTotal(result.total);setPage(next)}catch(error){setToast(error instanceof Error?error.message:'更多旅客记录加载失败')}finally{setBusy(false)}}
  const createControl=async()=>{if(!selected)return;setBusy(true);try{const portType=selected.port.includes('机场')?'airport':selected.port.includes('港')?'seaport':'land';const result=await postJson<{measures:string[]}>('/port-advice',{port_name:selected.port,port_type:portType,alert_level:selected.level});setToast(`布控建议已生成：${result.measures.join('；')}`)}catch(error){setToast(error instanceof Error?error.message:'布控建议生成失败')}finally{setBusy(false);setTimeout(()=>setToast(''),4000)}}

  const redCount=rows.filter(row=>row.level==='red').length
  const hitCount=rows.filter(row=>row.level!=='blue').length
  const declarationRate=rows.length?rows.filter(row=>row.declaration).length/rows.length*100:100
  return <div className="business-page page-enter passenger-page">
    <section className="page-heading compact-heading"><div><span className="eyebrow">PORT HEALTH CONTROL · INTRANET</span><h1>旅客风险预警</h1><p>基于14天旅居史、健康申报及中转链路进行实时风险匹配。</p></div><div className="heading-actions"><button className="secondary-button" disabled={busy} onClick={()=>fileRef.current?.click()}><FileUp size={16}/>批量导入</button><input ref={fileRef} hidden type="file" accept=".csv,.jsonl,.ndjson" onChange={event=>event.target.files?.[0]&&importFile(event.target.files[0])}/><button className="primary-button" disabled={busy} onClick={() => setModal(true)}><Plus size={16}/>录入旅客</button></div></section>

    <section className="passenger-kpis">
      <article><span className="round-icon cyan"><UsersRound size={20}/></span><div><small>累计风险匹配</small><strong>{total}</strong><em>数据库真实记录</em></div></article>
      <article><span className="round-icon red"><Siren size={20}/></span><div><small>红色风险旅客</small><strong>{redCount}</strong><em>当前载入 {rows.length} 人</em></div></article>
      <article><span className="round-icon orange"><AlertTriangle size={20}/></span><div><small>风险规则命中</small><strong>{hitCount}</strong><em>黄 / 橙 / 红风险</em></div></article>
      <article><span className="round-icon blue"><BadgeCheck size={20}/></span><div><small>健康申报完成率</small><strong>{declarationRate.toFixed(1)}%</strong><em>当前载入旅客</em></div></article>
    </section>

    <section className="passenger-workspace">
      <article className="panel passenger-list-panel">
        <header className="panel__header"><div><span className="panel__eyebrow">LIVE SCREENING</span><h2>实时入境旅客</h2></div><span className="live-label"><i/>实时匹配</span></header>
        <div className="table-toolbar"><label className="table-search"><Search size={16}/><input value={query} onChange={(e)=>setQuery(e.target.value)} placeholder="搜索证件尾号、航班或来源地"/></label><label className="toolbar-button"><Filter size={15}/><select value={riskFilter} onChange={event=>setRiskFilter(event.target.value as 'all'|RiskLevel)}><option value="all">全部风险</option>{(['red','orange','yellow','blue'] as RiskLevel[]).map(level=><option key={level} value={level}>{levelMeta[level].label}色</option>)}</select></label></div>
        <div className="passenger-list">
          <div className="passenger-list__head"><span>旅客</span><span>行程</span><span>入境信息</span><span>风险结果</span><span/></div>
          {filtered.map((row) => <button key={row.id} className={`passenger-row ${selected?.id === row.id ? 'is-selected' : ''}`} onClick={()=>setSelected(row)}>
            <span className="pax-person"><span className="avatar small">{row.name.slice(0,1)}</span><span><b>{row.name}</b><small>{row.document} · {row.nationality}</small></span></span>
            <span className="pax-route"><b>{row.origin}</b><small>{row.transit === '—' ? '直达入境' : `经 ${row.transit} 中转`}</small></span>
            <span className="pax-entry"><b>{row.flight}</b><small>{row.port} · {row.time}</small></span>
            <span className="pax-risk"><strong style={{color:levelMeta[row.level].color}}>{row.score}</strong><span className={`level-pill level-pill--${row.level}`}>{levelMeta[row.level].label}</span></span><ChevronRight size={16}/>
          </button>)}
        </div><div className="table-footer"><span>当前显示 {rows.length} 人 / 共 {total} 人</span>{rows.length<total&&<button className="text-button" disabled={busy} onClick={loadMore}>加载更多记录 <ArrowRight size={14}/></button>}</div>
      </article>

      <aside className="panel passenger-analysis">
        {selected ? <><header className="analysis-head"><div><span className={`alert-level-icon alert-level-icon--${selected.level}`}><UserRoundCheck size={22}/></span><div><small>个人风险研判</small><h2>{selected.name}</h2></div></div><span className={`level-badge level-badge--${selected.level}`}><i/>{levelMeta[selected.level].label}色</span></header>
        <div className="person-score"><div className={`score-ring score-ring--${selected.level}`}><strong>{selected.score}</strong><span>风险分</span></div><div><b>{selected.level === 'red' ? '建议重点布控' : selected.level === 'orange' ? '建议加强筛查' : selected.level === 'yellow' ? '建议常规监测' : '执行常态检疫'}</b><span>匹配规则 {selected.ruleVersion}</span><small><CheckCircle2 size={13}/>匹配时间 {new Date(selected.matchedAt).toLocaleString('zh-CN')}</small></div></div>
        <section><h3>风险命中原因</h3><ul className="reason-list">{selected.reasons.map((reason,i)=><li key={reason}><span>{i+1}</span>{reason}</li>)}</ul></section>
        <section><h3>行程链路</h3><div className="route-line"><span><i/>{selected.origin}<small>来源地</small></span>{selected.transit !== '—' && <><em/><span><i/>{selected.transit}<small>中转</small></span></>}<em/><span><i className="china"/>中国<small>{selected.port.replace('国际机场','')}</small></span></div></section>
        <section><h3>布控处置建议</h3><ul className="advice-list">{(selected.level === 'red' ? ['引导至专用检疫通道','开展流行病学调查','按病种要求采样检测','通知属地联防联控'] : selected.level === 'orange' ? ['加强健康申报核验','实施体温复测','按比例开展核酸抽检'] : ['核验健康申报','常规体温监测']).map(item=><li key={item}><ShieldCheck size={14}/>{item}</li>)}</ul></section>
        <button className="primary-button full-width" disabled={busy} onClick={createControl}><Siren size={16}/>生成布控指令</button></> : <div className="empty-state"><UserRoundCheck size={30}/><b>选择旅客查看风险研判</b></div>}
      </aside>
    </section>

    {modal && <div className="modal-layer"><button className="modal-backdrop" onClick={()=>setModal(false)}/><form className="modal-card passenger-form" onSubmit={submit}><header><div><span className="panel__eyebrow">PASSENGER INPUT</span><h2>录入旅客信息</h2></div><button type="button" className="icon-button" onClick={()=>setModal(false)}><X size={19}/></button></header><div className="form-grid"><label><span>姓名</span><input required value={form.name} onChange={e=>setForm({...form,name:e.target.value})} placeholder="输入旅客姓名"/></label><label><span>证件号码</span><input required value={form.document} onChange={e=>setForm({...form,document:e.target.value})} placeholder="仅在内网加密存储"/></label><label><span>国籍</span><input value={form.nationality} onChange={e=>setForm({...form,nationality:e.target.value})}/></label><label><span>14天内主要旅居地</span><select value={form.origin} onChange={e=>setForm({...form,origin:e.target.value})}>{countries.map(c=><option key={c.code}>{c.name}</option>)}</select></label><label><span>中转国家（可选）</span><input value={form.transit} onChange={e=>setForm({...form,transit:e.target.value})} placeholder="例如：新加坡"/></label><label><span>入境口岸</span><select value={form.port} onChange={e=>setForm({...form,port:e.target.value})}><option>北京首都国际机场</option><option>上海浦东国际机场</option><option>广州白云国际机场</option><option>深圳湾口岸</option></select></label><label><span>航班号</span><input value={form.flight} onChange={e=>setForm({...form,flight:e.target.value})} placeholder="例如 CA970"/></label><label className="checkbox-label"><input type="checkbox" checked={form.declaration} onChange={e=>setForm({...form,declaration:e.target.checked})}/><span><b>已完成健康申报</b><small>取消勾选将增加个人风险分</small></span></label></div><footer><button type="button" className="secondary-button" onClick={()=>setModal(false)}>取消</button><button className="primary-button"><Plane size={16}/>提交并匹配风险</button></footer></form></div>}
    {toast && <div className="toast success"><CheckCircle2 size={16}/>{toast}</div>}
  </div>
}
