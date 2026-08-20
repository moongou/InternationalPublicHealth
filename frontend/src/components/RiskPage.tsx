import { useMemo, useState } from 'react'
import { Activity, ArrowRight, BellRing, Calculator, CheckCircle2, Globe2, Save, Settings2, SlidersHorizontal, Sparkles, TrendingUp } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Alert, Country, RiskLevel, RuleDefinition, TrendPoint } from '../types'
import { requestJson } from '../api'
import { calculateWeightedRisk } from '../risk'
import { levelMeta } from '../utils'

const initialWeights = { severity: 25, transmission: 25, scale: 15, travel: 15, transit: 10, capacity: 10 }
const labels: Record<keyof typeof initialWeights, string> = { severity: '疾病严重性', transmission: '传播速度', scale: '病例规模', travel: '对华往来强度', transit: '中转风险', capacity: '当地防控能力' }

const ruleWeights = (rule?: RuleDefinition) => {
  const configured=(rule?.action_json.weights??{}) as Record<string,unknown>
  const values=Object.fromEntries(Object.keys(initialWeights).map(key=>[key,Math.round(Number(configured[key]??initialWeights[key as keyof typeof initialWeights]/100)*100)])) as typeof initialWeights
  return Object.values(values).every(Number.isFinite)&&Object.values(values).reduce((sum,value)=>sum+value,0)===100?values:initialWeights
}

export default function RiskPage({ countries, alerts, trend, rules, onOpenMap, connected }: { countries: Country[]; alerts: Alert[]; trend: TrendPoint[]; rules: RuleDefinition[]; onOpenMap: () => void; connected: boolean }) {
  const [tab, setTab] = useState<'overview' | 'model'>('overview')
  const initialRiskRule=rules.find(rule=>rule.type==='risk_score')
  const [riskRuleId,setRiskRuleId]=useState<string|null>(initialRiskRule?.rule_id??null)
  const [weights, setWeights] = useState(()=>ruleWeights(initialRiskRule))
  const [countryLevel,setCountryLevel]=useState<'all'|'red'|'orange'>('all')
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const weightTotal = Object.values(weights).reduce((a, b) => a + b, 0)
  const highRisk = useMemo(() => countries.filter((country) => ['red','orange'].includes(country.level)&&(countryLevel==='all'||country.level===countryLevel)).sort((a,b) => b.risk_score - a.risk_score), [countries,countryLevel])
  const testCountry = countries[0]
  const previewWeights = Object.fromEntries(Object.entries(weights).map(([key, value]) => [key, value / 100]))
  const preview = testCountry && weightTotal === 100 ? calculateWeightedRisk(testCountry.factors, previewWeights).score : 0
  const latestTrend=trend.at(-1)
  const firstTrend=trend[0]
  const globalIndex=latestTrend?.global??(countries.length?countries.reduce((sum,country)=>sum+country.risk_score,0)/countries.length:0)
  const globalChange=firstTrend?.global?((globalIndex-firstTrend.global)/firstTrend.global*100):0
  const drivers=highRisk.slice(0,3).map(country=>country.name).join('、')||'暂无高风险国家'

  const save = async () => {
    setSaveState('saving')
    try {
      if (connected) {
        const action_json = { weights: Object.fromEntries(Object.entries(weights).map(([key, value]) => [key, value / 100])) }
        const saved=await requestJson<RuleDefinition>(riskRuleId?`/rules/${riskRuleId}`:'/rules', {
          method:riskRuleId?'PUT':'POST',
          body:JSON.stringify(riskRuleId?{action_json}:{name:'全球国家风险加权评分',type:'risk_score',description:'按六因子计算国家综合风险',condition_json:{all:true},action_json,priority:10}),
        })
        setRiskRuleId(saved.rule_id)
      }
      setSaveState('saved')
    } catch {
      setSaveState('error')
    }
    setTimeout(() => setSaveState('idle'), 2400)
  }
  return (
    <div className="business-page page-enter">
      <section className="page-heading compact-heading">
        <div><span className="eyebrow">RISK INTELLIGENCE ENGINE</span><h1>风险研判中心</h1><p>六因子动态评分、趋势突变检测与分级预警管理。</p></div>
        <div className="heading-actions"><div className="page-tabs"><button className={tab === 'overview' ? 'active' : ''} onClick={() => setTab('overview')}>研判总览</button><button className={tab === 'model' ? 'active' : ''} onClick={() => setTab('model')}>模型配置</button></div><button className="primary-button" onClick={onOpenMap}><Globe2 size={16}/>地图研判</button></div>
      </section>

      {tab === 'overview' ? <>
        <section className="risk-overview-grid">
          <article className="panel risk-index-hero">
            <div className="risk-gauge" style={{ '--score': globalIndex } as React.CSSProperties}><div><strong>{globalIndex.toFixed(1)}</strong><span>全球风险指数</span><small>{globalIndex>=60?'中高风险':globalIndex>=40?'中风险':'低风险'}</small></div></div>
            <div className="risk-hero-copy"><span className="panel__eyebrow">GLOBAL RISK INDEX</span><h2>历史区间风险指数{globalChange>=0?'上升':'下降'} {Math.abs(globalChange).toFixed(1)}%</h2><p>当前主要高风险国家：{drivers}。</p><div><span><TrendingUp size={14}/>区间变化 <b>{globalChange>=0?'+':''}{globalChange.toFixed(1)}%</b></span><span>评分对象 <b>{countries.length} 国</b></span></div></div>
          </article>
          <article className="panel risk-level-cards"><header className="panel__header"><div><span className="panel__eyebrow">ALERT LEVELS</span><h2>风险等级分布</h2></div></header><div className="level-card-grid">{(['red','orange','yellow','blue'] as RiskLevel[]).map((level) => { const count = countries.filter((c) => c.level === level).length; return <div key={level} className={`level-stat level-stat--${level}`}><span><i/>{levelMeta[level].label}色风险</span><strong>{count}<small> 个</small></strong><em>{level === 'red' ? '重点布控' : level === 'orange' ? '加强筛查' : level === 'yellow' ? '常规监测' : '常态检疫'}</em></div> })}</div></article>
        </section>

        <section className="risk-detail-grid">
          <article className="panel risk-country-table">
            <header className="panel__header"><div><span className="panel__eyebrow">HIGH RISK COUNTRIES</span><h2>高风险国家研判</h2></div><label className="toolbar-button"><SlidersHorizontal size={14}/><select value={countryLevel} onChange={event=>setCountryLevel(event.target.value as typeof countryLevel)}><option value="all">红色与橙色</option><option value="red">仅红色</option><option value="orange">仅橙色</option></select></label></header>
            <div className="factor-header"><span>国家</span><span>严重性</span><span>传播</span><span>规模</span><span>往来</span><span>中转</span><span>综合分</span></div>
            {highRisk.map((country) => <div className="factor-row" key={country.code}>
              <span className="factor-country"><span>{country.code.slice(0,2)}</span><b>{country.name}</b><small>{country.region}</small></span>
              {(['severity','transmission','scale','travel','transit'] as const).map((key) => <span className="mini-factor" key={key}><i style={{ width: `${country.factors[key]}%`, background: country.factors[key] >= 80 ? '#ff5b72' : country.factors[key] >= 60 ? '#ffad4d' : '#34cbbb' }}/><b>{country.factors[key]}</b></span>)}
              <span className="factor-score"><b style={{ color: levelMeta[country.level].color }}>{country.risk_score}</b><small className={`level-pill level-pill--${country.level}`}>{levelMeta[country.level].label}</small></span>
            </div>)}
          </article>
          <article className="panel multi-trend-panel">
            <header className="panel__header"><div><span className="panel__eyebrow">REGIONAL TREND</span><h2>区域风险走势</h2></div><Activity size={18} className="muted-icon"/></header>
            <div className="multi-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={trend} margin={{ left: -25, right: 8, top: 10 }}><CartesianGrid stroke="rgba(151,172,199,.08)" vertical={false}/><XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill:'#718399',fontSize:10 }}/><YAxis domain={['auto','auto']} axisLine={false} tickLine={false} tick={{ fill:'#718399',fontSize:10 }}/><Tooltip contentStyle={{ background:'#101e2e',border:'1px solid #294056',borderRadius:9 }}/><Area dataKey="africa" name="非洲" type="monotone" stroke="#ff647a" fill="transparent" strokeWidth={2}/><Area dataKey="asia" name="亚洲" type="monotone" stroke="#f5b84d" fill="transparent" strokeWidth={2}/><Area dataKey="americas" name="美洲" type="monotone" stroke="#6d8cff" fill="transparent" strokeWidth={2}/><Area dataKey="europe" name="欧洲" type="monotone" stroke="#b07cff" fill="transparent" strokeWidth={2}/><Area dataKey="oceania" name="大洋洲" type="monotone" stroke="#34cbbb" fill="transparent" strokeWidth={2}/></AreaChart></ResponsiveContainer></div>
            <div className="regional-legend"><span><i style={{background:'#ff647a'}}/>非洲 <b>{latestTrend?.africa?.toFixed(1)??'—'}</b></span><span><i style={{background:'#f5b84d'}}/>亚洲 <b>{latestTrend?.asia?.toFixed(1)??'—'}</b></span><span><i style={{background:'#6d8cff'}}/>美洲 <b>{latestTrend?.americas?.toFixed(1)??'—'}</b></span><span><i style={{background:'#b07cff'}}/>欧洲 <b>{latestTrend?.europe?.toFixed(1)??'—'}</b></span><span><i style={{background:'#34cbbb'}}/>大洋洲 <b>{latestTrend?.oceania?.toFixed(1)??'—'}</b></span></div>
          </article>
        </section>
        <article className="panel alerts-workbench"><header className="panel__header"><div><span className="panel__eyebrow">ALERT WORKBENCH</span><h2>预警研判工作台</h2></div><span className="header-count">{alerts.length} 条待处置</span></header><div className="alert-workbench-grid">{alerts.map((alert) => <div className={`workbench-alert workbench-alert--${alert.level}`} key={alert.id}><div className="workbench-alert__head"><span><BellRing size={16}/>{levelMeta[alert.level].label}色预警</span><small>{alert.id}</small></div><h3>{alert.title}</h3><p>{alert.advice}</p><div><span>{alert.country} · {alert.disease}</span><strong>{alert.score} 分</strong></div><button onClick={onOpenMap}>进入地图研判 <ArrowRight size={14}/></button></div>)}</div></article>
      </> : <section className="model-layout">
        <article className="panel weight-editor">
          <header className="panel__header"><div><span className="panel__eyebrow">FACTOR WEIGHTS</span><h2>风险因子权重配置</h2></div><span className={`weight-total ${weightTotal === 100 ? 'valid' : ''}`}>合计 {weightTotal}%</span></header>
          <p className="panel-description">调整因子权重后可实时预览评分结果。正式发布后将在下一计算周期热更新。</p>
          <div className="weight-list">{Object.entries(weights).map(([key, value]) => <label key={key}><div><span>{labels[key as keyof typeof weights]}</span><b>{value}%</b></div><input type="range" min="0" max="50" value={value} onChange={(e) => setWeights((current) => ({ ...current, [key]: Number(e.target.value) }))}/><small>{key === 'severity' ? '病死率、住院率、后遗症' : key === 'transmission' ? '病例增长率、Rt 值' : key === 'scale' ? '病例绝对数、影响地区' : key === 'travel' ? '历史出入境人数、航班频次' : key === 'transit' ? '第三国中转来华比例' : 'GHS Index、医疗承载能力'}</small></label>)}</div>
          <footer><button className="secondary-button" onClick={() => setWeights(initialWeights)}>恢复默认</button><button className="primary-button" disabled={weightTotal !== 100 || saveState === 'saving' || !connected} onClick={save}><Save size={16}/>{saveState === 'saving' ? '正在保存…' : saveState === 'saved' ? '已保存草稿' : saveState === 'error' ? '保存失败，请重试' : '保存为新版本'}</button></footer>
        </article>
        <div className="model-side">
          <article className="panel score-preview"><header className="panel__header"><div><span className="panel__eyebrow">LIVE PREVIEW</span><h2>评分实时预览</h2></div><Sparkles size={18} className="text-teal"/></header><div className="preview-country"><span>CO</span><div><b>{testCountry?.name}</b><small>使用当前监测数据</small></div></div><div className="preview-score"><span style={{ '--value': `${preview}%` } as React.CSSProperties}/><div><strong>{preview.toFixed(1)}</strong><small>预估风险分</small></div></div><div className="score-change"><Calculator size={16}/><span>当前生产评分</span><b>{testCountry?.risk_score}</b><ArrowRight size={14}/><strong>{preview.toFixed(1)}</strong></div></article>
          <article className="panel threshold-card"><header className="panel__header"><div><span className="panel__eyebrow">THRESHOLDS</span><h2>预警分级阈值</h2></div><Settings2 size={18} className="muted-icon"/></header><div className="threshold-bar"><span className="blue" style={{width:'40%'}}>0—39</span><span className="yellow" style={{width:'20%'}}>40—59</span><span className="orange" style={{width:'20%'}}>60—79</span><span className="red" style={{width:'20%'}}>80—100</span></div><ul><li><i className="red"/><span>红色预警</span><b>≥ 80</b></li><li><i className="orange"/><span>橙色预警</span><b>60—79</b></li><li><i className="yellow"/><span>黄色预警</span><b>40—59</b></li><li><i className="blue"/><span>蓝色预警</span><b>&lt; 40</b></li></ul></article>
          <article className="model-ready"><CheckCircle2 size={21}/><div><b>模型运行正常</b><span>当前载入 {countries.length} 个国家 · 执行耗时见系统统计</span></div></article>
        </div>
      </section>}
      {saveState === 'saved' && <div className="toast success"><CheckCircle2 size={16}/>模型配置已保存为新的草稿版本</div>}
    </div>
  )
}
