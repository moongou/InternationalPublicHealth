import { useMemo, useState } from 'react'
import { ArrowDownToLine, Bot, ChevronRight, CircleAlert, ExternalLink, Filter, MapPin, Search, X } from 'lucide-react'
import type { DiseaseEvent, RiskLevel } from '../types'
import { formatNumber, formatTime, levelMeta } from '../utils'
import { postJson } from '../api'

export default function EventsPage({ events, actions, showSourceLink = false }: { events: DiseaseEvent[]; actions?: React.ReactNode; showSourceLink?: boolean }) {
  const [query, setQuery] = useState('')
  const [level, setLevel] = useState<'all' | RiskLevel>('all')
  const [selected, setSelected] = useState<DiseaseEvent | null>(null)
  const [toast, setToast] = useState('')
  const [page, setPage] = useState(1)
  const [aiBusy,setAiBusy]=useState(false)
  const [aiAnalysis,setAiAnalysis]=useState('')
  const filtered = useMemo(() => events.filter((event) => {
    const matchQuery = !query || `${event.title}${event.country}${event.disease}${event.source}`.toLowerCase().includes(query.toLowerCase())
    return matchQuery && (level === 'all' || event.level === level)
  }), [events, query, level])
  const pageSize=20
  const pageCount=Math.max(1,Math.ceil(filtered.length/pageSize))
  const paged=filtered.slice((Math.min(page,pageCount)-1)*pageSize,Math.min(page,pageCount)*pageSize)
  const cutoff=Date.now()-86_400_000
  const recent=events.filter(event=>new Date(event.published_at).getTime()>=cutoff).length
  const diseases=new Set(events.map(event=>event.disease)).size
  const sources=new Set(events.map(event=>event.source)).size
  const lowConfidence=events.filter(event=>event.confidence<.8).length

  const exportList = () => {
    const csv = ['事件编号,标题,国家,疾病,病例,死亡,风险等级,来源', ...filtered.map((e) => [e.id, e.title, e.country, e.disease, e.cases, e.deaths, levelMeta[e.level].label, e.source].map((v) => `"${v}"`).join(','))].join('\n')
    const url = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' }))
    const a = document.createElement('a'); a.href = url; a.download = '全球疫情事件.csv'; a.click(); URL.revokeObjectURL(url)
    setToast('事件清单已导出'); setTimeout(() => setToast(''), 2200)
  }
  const analyze=async()=>{if(!selected)return;setAiBusy(true);try{const result=await postJson<{analysis:string;provider:string;model:string}>('/ai/analyze-event',{title:selected.title,country:selected.country,disease:selected.disease,cases:selected.cases,deaths:selected.deaths,level:selected.level,source:selected.source,published_at:selected.published_at,confidence:selected.confidence});setAiAnalysis(`${result.analysis}\n\n— ${result.provider} / ${result.model}`)}catch(error){setToast(error instanceof Error?error.message:'大模型研判失败');setTimeout(()=>setToast(''),3000)}finally{setAiBusy(false)}}
  return (
    <div className="business-page page-enter">
      <section className="page-heading compact-heading">
        <div><span className="eyebrow">GLOBAL EVENT INTELLIGENCE</span><h1>全球疫情事件中心</h1><p>多源事件聚合、可信度校验与全过程追踪。</p></div>
        <div className="heading-actions">{actions}<button className="primary-button" onClick={exportList}><ArrowDownToLine size={16}/>导出清单</button></div>
      </section>

      <section className="summary-strip">
        <div><span>24小时新增</span><strong>{recent}</strong><small>按发布时间统计</small></div>
        <div><span>待复核事件</span><strong>{lowConfidence}</strong><small>置信度低于 80%</small></div>
        <div><span>覆盖疾病</span><strong>{diseases}</strong><small>当前载入事件</small></div>
        <div><span>事件数据源</span><strong className="text-teal">{sources}</strong><small>当前载入事件</small></div>
      </section>

      <section className="panel table-panel">
        <div className="table-toolbar">
          <label className="table-search"><Search size={16}/><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索事件、国家、疾病或来源" />{query && <button onClick={() => setQuery('')}><X size={14}/></button>}</label>
          <div className="filter-tabs"><button className={level === 'all' ? 'active' : ''} onClick={() => setLevel('all')}>全部 <span>{events.length}</span></button>{(['red','orange','yellow','blue'] as RiskLevel[]).map((item) => <button className={level === item ? `active active--${item}` : ''} key={item} onClick={() => setLevel(item)}><i style={{ background: levelMeta[item].color }}/>{levelMeta[item].label}</button>)}</div>
          <span className="source-tag">支持事件、国家、疾病、来源和风险筛选</span>
        </div>
        <div className="data-table-wrap">
          <table className="data-table event-data-table">
            <thead><tr><th>风险</th><th>事件摘要</th><th>国家 / 地区</th><th>疾病</th><th>病例 / 死亡</th><th>数据来源</th><th>发布时间</th><th>可信度</th><th/></tr></thead>
            <tbody>{paged.map((event) => <tr key={event.id} onClick={() => {setSelected(event);setAiAnalysis('')}}>
              <td><span className={`level-badge level-badge--${event.level}`}><i/>{levelMeta[event.level].label}</span></td>
              <td><div className="event-title-cell"><b>{event.title}</b><small>{event.id} · {event.event_type}</small></div></td>
              <td><span className="country-cell"><span>{event.country_code.slice(0, 2)}</span>{event.country}</span></td>
              <td>{event.disease}</td><td><b>{formatNumber(event.cases)}</b><small className="slash-count"> / {formatNumber(event.deaths)}</small></td>
              <td>{showSourceLink && event.source_url ? <a className="source-link" href={event.source_url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}><span className="source-tag">{event.source}</span><ExternalLink size={12}/></a> : <span className="source-tag">{event.source}</span>}</td><td>{formatTime(event.published_at)}</td>
              <td><span className={`confidence ${event.confidence >= .9 ? 'high' : ''}`}><i style={{ width: `${event.confidence * 100}%` }}/><b>{(event.confidence * 100).toFixed(0)}%</b></span></td><td><ChevronRight size={16}/></td>
            </tr>)}</tbody>
          </table>
          {!filtered.length && <div className="empty-state"><Filter size={28}/><b>没有符合条件的事件</b><span>请调整搜索词或筛选条件</span></div>}
        </div>
        <div className="table-footer"><span>筛选后 {filtered.length} 条，共载入 {events.length} 条事件</span><div className="pagination"><button disabled={page<=1} onClick={()=>setPage(value=>Math.max(1,value-1))}>上一页</button><span className="active">{Math.min(page,pageCount)} / {pageCount}</span><button disabled={page>=pageCount} onClick={()=>setPage(value=>Math.min(pageCount,value+1))}>下一页</button></div></div>
      </section>

      <aside className={`detail-drawer ${selected ? 'is-open' : ''}`}>
        {selected && <>
          <header><div><span className={`level-badge level-badge--${selected.level}`}><i/>{levelMeta[selected.level].label}风险</span><small>{selected.id}</small></div><button className="icon-button" onClick={() => setSelected(null)}><X size={19}/></button></header>
          <div className="detail-drawer__body">
            <h2>{selected.title}</h2><p className="detail-lead">该事件由 {selected.source} 于 {formatTime(selected.published_at)} 发布，经多源交叉验证后纳入监测。</p>
            <div className="detail-metrics"><div><span>累计病例</span><strong>{formatNumber(selected.cases)}</strong></div><div><span>报告死亡</span><strong>{formatNumber(selected.deaths)}</strong></div><div><span>可信度</span><strong>{(selected.confidence * 100).toFixed(0)}%</strong></div></div>
            <section className="detail-section"><h3>事件信息</h3><dl><div><dt>国家 / 地区</dt><dd><MapPin size={13}/>{selected.country}</dd></div><div><dt>涉及疾病</dt><dd>{selected.disease}</dd></div><div><dt>事件类型</dt><dd>{selected.event_type}</dd></div><div><dt>原始来源</dt><dd>{showSourceLink && selected.source_url ? <a className="source-link" href={selected.source_url} target="_blank" rel="noopener noreferrer">{selected.source}<ExternalLink size={12}/></a> : selected.source}</dd></div></dl></section>
            <section className="detail-section"><h3>{aiAnalysis?'大语言模型研判':'事实摘要'}</h3><div className="analysis-note"><CircleAlert size={18}/><p style={{whiteSpace:'pre-wrap'}}>{aiAnalysis||`当前来源记录 ${formatNumber(selected.cases)} 例、死亡 ${formatNumber(selected.deaths)} 例，可信度 ${(selected.confidence*100).toFixed(0)}%，系统风险分级为${levelMeta[selected.level].label}色。未调用模型前仅展示来源事实，不推断未提供的信息。`}</p></div></section>
            <section className="detail-section"><h3>处置建议</h3><ul className="check-list"><li>核验近14日相关地区旅居史</li><li>关注发热、皮疹等特异性症状</li><li>异常情况按口岸联防联控流程处置</li></ul></section>
          </div>
          <footer><button className="secondary-button" onClick={() => setSelected(null)}>关闭</button><button className="primary-button" disabled={aiBusy} onClick={analyze}><Bot size={15}/>{aiBusy?'模型研判中…':aiAnalysis?'重新调用模型':'调用大模型研判'}</button></footer>
        </>}
      </aside>
      {selected && <button className="drawer-backdrop" onClick={() => setSelected(null)} aria-label="关闭详情" />}
      {toast && <div className="toast success">{toast}</div>}
    </div>
  )
}
