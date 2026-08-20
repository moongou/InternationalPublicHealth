import { useMemo } from 'react'
import {
  Activity, ArrowRight, BellRing, CircleAlert, Clock3, Database, Globe2, MapPin,
  Plane, RefreshCw, ShieldAlert, TrendingDown, TrendingUp, UsersRound,
} from 'lucide-react'
import { Area, AreaChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { AppData } from '../api'
import type { PageId, RiskLevel } from '../types'
import { compactNumber, formatNumber, formatTime, levelMeta } from '../utils'

interface DashboardProps {
  data: AppData
  onOpenMap: () => void
  onNavigate: (page: PageId) => void
  mode: 'internet'|'intranet'
}

const baseKpis = [
  { key: 'active_events', label: '全球活跃事件', icon: Activity, tone: 'cyan', note: '近 30 日' },
  { key: 'high_risk_countries', label: '高风险国家', icon: ShieldAlert, tone: 'red', note: '红 / 橙等级' },
  { key: 'active_alerts', label: '生效预警', icon: BellRing, tone: 'orange', note: '数据库生效状态' },
] as const

export default function Dashboard({ data, onOpenMap, onNavigate, mode }: DashboardProps) {
  const kpis=[...baseKpis,mode==='intranet'?{key:'passengers_screened_today' as const,label:'今日筛查旅客',icon:UsersRound,tone:'violet',note:'内网实时统计'}:{key:'monitored_countries' as const,label:'监测国家 / 地区',icon:Globe2,tone:'violet',note:'风险评分覆盖'}]
  const highRisk = useMemo(() => data.countries.slice().sort((a, b) => b.risk_score - a.risk_score).slice(0, 6), [data.countries])
  const pieData = (['red', 'orange', 'yellow', 'blue'] as RiskLevel[]).map((level) => ({ name: levelMeta[level].label, value: data.stats.level_distribution[level] ?? 0, color: levelMeta[level].color }))
  const latestTrend=data.trend.at(-1)
  const firstTrend=data.trend[0]
  const globalIndex=latestTrend?.global??(data.countries.length?data.countries.reduce((sum,country)=>sum+country.risk_score,0)/data.countries.length:0)
  const globalChange=firstTrend?.global?((globalIndex-firstTrend.global)/firstTrend.global*100):0
  const sourceCount=Object.values(data.stats.source_health).reduce((sum,value)=>sum+value,0)
  const hasPartial = useMemo(() => data.trend.some((p) => p.partial), [data.trend])
  const trendSeries = useMemo(() => {
    const firstPartial = data.trend.findIndex((p) => p.partial)
    const anchor = firstPartial > 0 ? firstPartial - 1 : -1
    return data.trend.map((p, i) => ({
      ...p,
      globalActual: p.partial ? null : p.global,
      globalForecast: p.partial ? (p.forecast ?? p.global) : (i === anchor ? p.global : null),
    }))
  }, [data.trend])

  return (
    <div className="dashboard page-enter">
      <section className="page-heading">
        <div>
          <span className="eyebrow"><i className="pulse-dot" /> GLOBAL SITUATION · 实时监测</span>
          <h1>全球公共卫生态势</h1>
          <p>汇聚 {sourceCount} 个已配置数据源，识别跨境传播风险，为口岸精准检疫提供决策支持。</p>
        </div>
        <div className="heading-actions">
          <span className="updated"><RefreshCw size={14} /> 数据更新于 {new Date(data.stats.last_updated).toLocaleString('zh-CN')}</span>
          <button className="primary-button" onClick={onOpenMap}><Globe2 size={17} />进入全球态势地图<ArrowRight size={16} /></button>
        </div>
      </section>

      <section className="kpi-grid">
        {kpis.map(({ key, label, icon: Icon, tone, note }) => {
          const value = data.stats[key]
          return (
            <article className={`kpi-card kpi-card--${tone}`} key={key}>
              <div className="kpi-card__top"><span className="kpi-icon"><Icon size={20} /></span>{key==='active_events'&&<span className="delta up"><TrendingUp size={13}/>{data.stats.new_events_24h} / 24h</span>}</div>
              <strong>{key === 'passengers_screened_today' ? compactNumber(value) : formatNumber(value)}</strong>
              <div className="kpi-card__bottom"><span>{label}</span><small>{note}</small></div>
              <i className="kpi-card__glow" />
            </article>
          )
        })}
      </section>

      <section className="dashboard-grid dashboard-grid--top">
        <article className="panel trend-panel">
          <header className="panel__header">
            <div><span className="panel__eyebrow">RISK TREND</span><h2>全球风险指数趋势</h2></div>
            <span className="source-tag">已入库历史</span>
          </header>
          <div className="trend-summary"><strong>{globalIndex.toFixed(1)}</strong><span>{globalChange>=0?<TrendingUp size={14}/>:<TrendingDown size={14}/>} 历史区间 {globalChange>=0?'+':''}{globalChange.toFixed(1)}%</span><small>综合风险指数</small></div>
          <div className="chart-wrap">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendSeries} margin={{ top: 8, right: 12, left: -22, bottom: 0 }}>
                <defs><linearGradient id="riskFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#33d6c7" stopOpacity={0.34}/><stop offset="95%" stopColor="#33d6c7" stopOpacity={0}/></linearGradient></defs>
                <CartesianGrid stroke="rgba(151,172,199,.09)" vertical={false} />
                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#718399', fontSize: 11 }} />
                <YAxis domain={['auto', 'auto']} axisLine={false} tickLine={false} tick={{ fill: '#718399', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#101e2e', border: '1px solid #294056', borderRadius: 10, color: '#dbe9f6' }} labelStyle={{ color: '#8da2b8' }} />
                <Area type="monotone" dataKey="globalActual" name="全球指数" stroke="#33d6c7" strokeWidth={2.4} fill="url(#riskFill)" activeDot={{ r: 5, fill: '#33d6c7', stroke: '#07111f', strokeWidth: 3 }} connectNulls={false} />
                {hasPartial && <Area type="monotone" dataKey="globalForecast" name="预测趋势" stroke="#33d6c7" strokeWidth={2} strokeDasharray="6 4" fill="transparent" dot={{ r: 3, fill: '#33d6c7', stroke: '#07111f', strokeWidth: 2 }} connectNulls={false} />}
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="chart-legend"><span><i style={{ background: '#33d6c7' }} />全球 {latestTrend?.global?.toFixed(1)??'—'}</span>{hasPartial&&<span><i style={{ background: '#33d6c7', opacity:.5 }} />预测趋势 {latestTrend?.forecast?.toFixed(1)??'—'}</span>}</div>
          {hasPartial&&<div className="trend-partial-note"><TrendingUp size={13}/>最近一天为部分国家/地区采集（覆盖率 {Math.round((latestTrend?.coverage??0)*100)}%），虚线为预测趋势，不代表全量风险值。</div>}
        </article>

        <article className="panel risk-rank-panel">
          <header className="panel__header"><div><span className="panel__eyebrow">TOP RISK</span><h2>国家风险排行</h2></div><button className="text-button" onClick={() => onNavigate('risk')}>全部 <ArrowRight size={14}/></button></header>
          <div className="risk-ranking">
            {highRisk.map((country, index) => (
              <button key={country.code} className="risk-rank-row" onClick={onOpenMap}>
                <span className={`rank rank--${index + 1}`}>{String(index + 1).padStart(2, '0')}</span>
                <span className="country-flag">{country.code.slice(0, 2)}</span>
                <span className="country-info"><b>{country.name}</b><small>{country.region} · {formatNumber(country.active_cases)} 活跃病例</small></span>
                <span className="risk-score"><b style={{ color: levelMeta[country.level].color }}>{country.risk_score}</b><small className={`level-pill level-pill--${country.level}`}>{levelMeta[country.level].label}</small></span>
                <span className={`trend-arrow ${country.trend_7d >= 0 ? 'bad' : 'good'}`}>{country.trend_7d >= 0 ? <TrendingUp size={14}/> : <TrendingDown size={14}/>} {Math.abs(country.trend_7d)}%</span>
              </button>
            ))}
          </div>
        </article>
      </section>

      <section className="dashboard-grid dashboard-grid--bottom">
        <article className="panel alert-panel">
          <header className="panel__header"><div><span className="panel__eyebrow">ACTIVE ALERTS</span><h2>当前生效预警</h2></div><span className="header-count">{data.alerts.length} 条</span></header>
          <div className="alert-list">
            {data.alerts.map((alert) => (
              <button className="alert-item" key={alert.id} onClick={() => onNavigate('risk')}>
                <span className={`alert-level-icon alert-level-icon--${alert.level}`}><CircleAlert size={19} /></span>
                <span className="alert-item__content"><b>{alert.title}</b><small><MapPin size={12}/>{alert.country}<i/> {alert.disease}<i/><Clock3 size={12}/>{formatTime(alert.issued_at)}</small></span>
                <span className="alert-item__score"><strong>{alert.score}</strong><small>风险分</small></span>
                <ArrowRight size={15} className="row-arrow" />
              </button>
            ))}
          </div>
          <button className="panel-footer-button" onClick={() => onNavigate('risk')}>查看全部预警 <ArrowRight size={14}/></button>
        </article>

        <article className="panel event-panel">
          <header className="panel__header"><div><span className="panel__eyebrow">LATEST EVENTS</span><h2>最新疫情事件</h2></div><span className="live-label"><i/>实时</span></header>
          <div className="event-timeline">
            {data.events.slice(0, 5).map((event) => (
              <button className="event-row" key={event.id} onClick={() => onNavigate('events')}>
                <span className={`timeline-dot timeline-dot--${event.level}`} />
                <span className="event-time">{new Date(event.published_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}</span>
                <span className="event-row__content"><b>{event.title}</b><small>{event.source} · 置信度 {(event.confidence * 100).toFixed(0)}%</small></span>
                <span className={`level-pill level-pill--${event.level}`}>{levelMeta[event.level].label}</span>
              </button>
            ))}
          </div>
          <button className="panel-footer-button" onClick={() => onNavigate('events')}>进入事件中心 <ArrowRight size={14}/></button>
        </article>

        <article className="panel distribution-panel">
          <header className="panel__header"><div><span className="panel__eyebrow">DISTRIBUTION</span><h2>风险等级分布</h2></div><Database size={17} className="muted-icon" /></header>
          <div className="donut-wrap">
            <ResponsiveContainer width="100%" height={170}>
              <PieChart><Pie data={pieData} dataKey="value" innerRadius={55} outerRadius={74} paddingAngle={4} stroke="none">{pieData.map((item) => <Cell key={item.name} fill={item.color}/>)}</Pie><Tooltip contentStyle={{ background: '#101e2e', border: '1px solid #294056', borderRadius: 9 }}/></PieChart>
            </ResponsiveContainer>
            <div className="donut-center"><strong>{data.stats.monitored_countries}</strong><span>国家/地区</span></div>
          </div>
          <div className="distribution-list">{pieData.map((item) => <div key={item.name}><span><i style={{ background: item.color }}/>{item.name}风险</span><strong>{item.value}<small> 个</small></strong></div>)}</div>
          <div className="port-mini"><Plane size={17}/><span><b>口岸筛查数据</b><small>今日已匹配 {formatNumber(data.stats.passengers_screened_today)} 人</small></span><ArrowRight size={15}/></div>
        </article>
      </section>
    </div>
  )
}
