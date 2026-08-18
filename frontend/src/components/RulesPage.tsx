import { useEffect, useMemo, useState } from 'react'
import { Beaker, BookOpenCheck, Check, CheckCircle2, ChevronRight, CircleDot, Clock3, Code2, Copy, GitBranch, Plus, Rocket, Save, Search, SlidersHorizontal, Sparkles, ToggleRight, X } from 'lucide-react'
import type { RuleDefinition } from '../types'
import { postJson, requestJson } from '../api'

interface RuleTestResponse { rule_id: string; version: number; success: boolean; execution_ms: number; output: { score?: number; level?: string; matched?: boolean; action?: Record<string, unknown> } }
interface RuleExecution { execution_id: string; matched: boolean; output: Record<string, unknown>; execution_ms: number; executed_at: string }

const typeMeta: Record<string,{label:string;color:string}> = {
  risk_score:{label:'风险评分',color:'#36d0c1'}, alert_level:{label:'预警分级',color:'#ff6378'}, port_advice:{label:'布控建议',color:'#7a91ff'}, passenger_match:{label:'旅客匹配',color:'#ffad4d'}, trend_change:{label:'趋势突变',color:'#c47aff'},
}

export default function RulesPage({ rules: initial, connected }: { rules: RuleDefinition[]; connected: boolean }) {
  const [rules,setRules]=useState(initial)
  const [selectedId,setSelectedId]=useState(initial[0]?.rule_id)
  const [query,setQuery]=useState('')
  const [ruleFilter,setRuleFilter]=useState<'all'|'risk_score'|'alert_level'|'port_advice'>('all')
  const [testOpen,setTestOpen]=useState(false)
  const [testResult,setTestResult]=useState<RuleTestResponse | null>(null)
  const [testContext,setTestContext]=useState(JSON.stringify({factors:{severity:90,transmission:80,scale:70,travel:60,transit:50,capacity:20}},null,2))
  const [toast,setToast]=useState('')
  const [busy,setBusy]=useState(false)
  const [editOpen,setEditOpen]=useState(false)
  const [historyOpen,setHistoryOpen]=useState(false)
  const [history,setHistory]=useState<RuleDefinition[]>([])
  const [conditionText,setConditionText]=useState('{}')
  const [actionText,setActionText]=useState('{}')
  const [executions,setExecutions]=useState<RuleExecution[]>([])
  const selected=rules.find(rule=>rule.rule_id===selectedId) ?? rules[0]
  const filtered=useMemo(()=>rules.filter(rule=>(ruleFilter==='all'||rule.type===ruleFilter)&&(!query||`${rule.name}${rule.rule_id}${rule.description}`.toLowerCase().includes(query.toLowerCase()))),[rules,query,ruleFilter])
  const executionStats=useMemo(()=>{
    const durations=executions.map(item=>item.execution_ms).sort((a,b)=>a-b)
    const matched=executions.filter(item=>item.matched).length
    return {
      matched,
      unmatched:executions.length-matched,
      matchRate:executions.length?`${(matched/executions.length*100).toFixed(1)}%`:'—',
      average:durations.length?`${Math.round(durations.reduce((sum,value)=>sum+value,0)/durations.length)} ms`:'—',
      p95:durations.length?`${durations[Math.min(durations.length-1,Math.ceil(durations.length*0.95)-1)]} ms`:'—',
    }
  },[executions])
  useEffect(()=>{
    let active=true
    if(!connected||!selected?.rule_id){setExecutions([]);return()=>{active=false}}
    requestJson<RuleExecution[]>(`/rules/${selected.rule_id}/executions?limit=500`)
      .then(items=>{if(active)setExecutions(items)})
      .catch(()=>{if(active)setExecutions([])})
    return()=>{active=false}
  },[connected,selected?.rule_id])
  const notify=(message:string)=>{setToast(message);setTimeout(()=>setToast(''),2600)}
  const publish=async()=>{if(!selected)return;setBusy(true);try{if(!connected)throw new Error('规则服务未连接');const published=await postJson<RuleDefinition>(`/rules/${selected.rule_id}/publish`);setRules(c=>c.map(r=>r.rule_id===selected.rule_id?published:r));notify(`规则 ${selected.rule_id} 已发布并热更新`)}catch(error){notify(error instanceof Error?error.message:'规则发布失败')}finally{setBusy(false)}}
  const duplicate=async()=>{if(!selected)return;setBusy(true);try{if(!connected)throw new Error('规则服务未连接');const copy=await postJson<RuleDefinition>('/rules',{name:`${selected.name}（副本）`,type:selected.type,description:selected.description,condition_json:selected.condition_json,action_json:selected.action_json,priority:selected.priority});setRules(c=>[...c,copy]);setSelectedId(copy.rule_id);notify('规则草稿已创建')}catch(error){notify(error instanceof Error?error.message:'规则创建失败')}finally{setBusy(false)}}
  const runTest=async()=>{if(!selected)return;setBusy(true);try{if(!connected)throw new Error('规则服务未连接');const context=JSON.parse(testContext) as {factors?:Record<string,number>};const result=await postJson<RuleTestResponse>(`/rules/${selected.rule_id}/test`,{context});setTestResult(result);setExecutions(await requestJson<RuleExecution[]>(`/rules/${selected.rule_id}/executions?limit=500`))}catch(error){setTestResult(null);notify(error instanceof Error?error.message:'测试上下文不是有效 JSON')}finally{setBusy(false)}}
  const openEdit=()=>{if(!selected)return;setConditionText(JSON.stringify(selected.condition_json,null,2));setActionText(JSON.stringify(selected.action_json,null,2));setEditOpen(true)}
  const saveDraft=async()=>{if(!selected)return;setBusy(true);try{const condition_json=JSON.parse(conditionText);const action_json=JSON.parse(actionText);const updated=await requestJson<RuleDefinition>(`/rules/${selected.rule_id}`,{method:'PUT',body:JSON.stringify({condition_json,action_json})});setRules(current=>[updated,...current.filter(item=>item.rule_id!==updated.rule_id)]);setSelectedId(updated.rule_id);setEditOpen(false);notify(`新草稿 v${updated.version} 已保存`)}catch(error){notify(error instanceof Error?error.message:'规则 JSON 格式或保存失败')}finally{setBusy(false)}}
  const openHistory=async()=>{if(!selected)return;setBusy(true);try{const items=await requestJson<RuleDefinition[]>('/rules?history=true');setHistory(items.filter(item=>(item.rule_key??item.rule_id.split('-')[0])===(selected.rule_key??selected.rule_id.split('-')[0])));setHistoryOpen(true)}catch(error){notify(error instanceof Error?error.message:'版本历史加载失败')}finally{setBusy(false)}}
  return <div className="business-page page-enter rules-page">
    <section className="page-heading compact-heading"><div><span className="eyebrow">VISUAL RULE ENGINE</span><h1>规则引擎</h1><p>配置、测试、版本化发布风险研判与口岸布控规则。</p></div><div className="heading-actions"><button className="secondary-button" disabled={busy||!selected} onClick={openHistory}><GitBranch size={16}/>版本历史</button><button className="primary-button" disabled={busy||!selected} onClick={duplicate}><Plus size={16}/>复制为新规则</button></div></section>
    <section className="rule-stats"><div><span className="round-icon cyan"><BookOpenCheck size={19}/></span><span><small>规则总数</small><strong>{rules.length}</strong></span></div><div><span className="round-icon blue"><Rocket size={19}/></span><span><small>已发布</small><strong>{rules.filter(r=>r.status==='published').length}</strong></span></div><div><span className="round-icon orange"><Clock3 size={19}/></span><span><small>待发布草稿</small><strong>{rules.filter(r=>r.status==='draft').length}</strong></span></div><div><span className="round-icon violet"><Sparkles size={19}/></span><span><small>所选规则执行记录</small><strong>{executions.length}</strong></span></div><div><span className="engine-status"><i/></span><span><small>执行器状态</small><strong className={connected?'text-teal':'text-orange'}>{connected?'运行正常':'服务未连接'}</strong></span></div></section>
    <section className="rules-workspace">
      <aside className="panel rule-list-panel"><div className="rule-list-search"><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索规则"/></div><div className="rule-filters">{([['all','全部'],['risk_score','评分'],['alert_level','预警'],['port_advice','布控']] as const).map(([value,label])=><button key={value} className={ruleFilter===value?'active':''} onClick={()=>setRuleFilter(value)}>{label}</button>)}</div><div className="rule-list">{filtered.map(rule=>{const meta=typeMeta[rule.type]??{label:rule.type,color:'#718399'};return <button key={rule.rule_id} className={selected?.rule_id===rule.rule_id?'active':''} onClick={()=>setSelectedId(rule.rule_id)}><span className="rule-type-icon" style={{color:meta.color,background:`${meta.color}18`}}><CircleDot size={18}/></span><span><b>{rule.name}</b><small><em style={{color:meta.color}}>{meta.label}</em> · v{rule.version}</small></span><i className={`publish-dot ${rule.status}`}/><ChevronRight size={15}/></button>})}</div><footer><span><i className="publish-dot published"/>已发布</span><span><i className="publish-dot draft"/>草稿</span></footer></aside>
      {selected&&<article className="panel rule-editor">
        <header className="rule-editor__header"><div><span className="panel__eyebrow">RULE DEFINITION · {selected.rule_id}</span><h2>{selected.name}</h2><p>{selected.description}</p></div><div><span className={`status-chip status-chip--${selected.status}`}>{selected.status==='published'?<><Check size={13}/>已发布</>:<><Clock3 size={13}/>草稿</>}</span><button className="icon-button" onClick={duplicate}><Copy size={16}/></button></div></header>
        <div className="rule-meta"><div><span>规则类型</span><b style={{color:typeMeta[selected.type]?.color}}>{typeMeta[selected.type]?.label}</b></div><div><span>当前版本</span><b>v{selected.version}</b></div><div><span>执行优先级</span><b>P{selected.priority}</b></div><div><span>最近更新</span><b>{selected.updated_at?new Date(selected.updated_at).toLocaleString('zh-CN'):'暂无记录'}</b></div></div>
        <div className="rule-builder">
          <div className="builder-flow"><span className="builder-start"><i/>当满足以下条件</span><em/><span className="builder-and">AND</span><em/><span className="builder-end"><Rocket size={14}/>执行规则动作</span></div>
          <section className="condition-group"><header><div><GitBranch size={16}/><b>条件组合</b><span>当前生效定义预览</span></div><button onClick={openEdit}><Code2 size={14}/>编辑条件</button></header><div className="action-preview"><Code2 size={17}/><pre>{JSON.stringify(selected.condition_json,null,2)}</pre></div></section>
          <section className="action-group"><header><div><Rocket size={16}/><b>执行动作</b><span>命中后输出</span></div><button onClick={openEdit}><Code2 size={14}/>编辑动作</button></header><div className="action-preview"><Code2 size={17}/><pre>{JSON.stringify(selected.action_json,null,2)}</pre></div></section>
          {selected.type==='risk_score'&&<section className="visual-weights"><header><SlidersHorizontal size={16}/><b>因子权重</b><span>合计 100%</span></header><div>{Object.entries((selected.action_json.weights??{}) as Record<string,number>).map(([key,value])=><label key={key}><span>{({severity:'严重性',transmission:'传播速度',scale:'病例规模',travel:'人员往来',transit:'中转风险',capacity:'防控能力'} as Record<string,string>)[key]??key}</span><i><em style={{width:`${value*400}%`}}/></i><b>{value*100}%</b></label>)}</div></section>}
        </div>
        <footer className="rule-editor__footer"><div><ToggleRight size={23}/><span><b>热更新</b><small>发布后新请求立即使用新版本</small></span></div><button className="secondary-button" disabled={busy} onClick={()=>{setTestResult(null);setTestOpen(true)}}><Beaker size={16}/>在线测试</button><button className="secondary-button" disabled={busy} onClick={openEdit}><Save size={16}/>编辑并保存草稿</button><button className="primary-button" disabled={busy||selected.status==='published'} onClick={publish}><Rocket size={16}/>{busy?'正在处理…':selected.status==='published'?'当前已发布':'发布规则'}</button></footer>
      </article>}
      <aside className="rule-activity"><article className="panel execution-card"><header className="panel__header"><div><span className="panel__eyebrow">EXECUTION</span><h2>所选规则执行概况</h2></div></header><div className="execution-score"><strong>{executionStats.matchRate}</strong><span>规则命中率</span></div><dl><div><dt>最近记录数</dt><dd>{executions.length}</dd></div><div><dt>平均耗时</dt><dd>{executionStats.average}</dd></div><div><dt>P95 耗时</dt><dd>{executionStats.p95}</dd></div><div><dt>未命中次数</dt><dd>{executionStats.unmatched}</dd></div></dl></article><article className="panel recent-execution"><header><b>最近执行</b><span className="live-label"><i/>实时</span></header>{executions.length===0?<div><span><b>暂无执行记录</b><small>执行在线测试后会显示真实结果</small></span></div>:executions.slice(0,4).map(item=><div key={item.execution_id}><span className="execution-ok"><Check size={12}/></span><span><b>{item.matched?'规则已命中':'规则未命中'}</b><small>{new Date(item.executed_at).toLocaleString('zh-CN')} · {item.execution_ms} ms</small></span></div>)}</article></aside>
    </section>
    {testOpen&&<div className="modal-layer"><button className="modal-backdrop" onClick={()=>setTestOpen(false)}/><div className="modal-card test-modal"><header><div><span className="panel__eyebrow">RULE SANDBOX</span><h2>在线测试 · {selected?.rule_id}</h2></div><button className="icon-button" onClick={()=>setTestOpen(false)}><X size={19}/></button></header><div className="test-modal__body"><label>测试上下文（JSON）</label><textarea value={testContext} onChange={event=>setTestContext(event.target.value)}/>{testResult&&<div className="test-result"><header><CheckCircle2 size={18}/><b>规则执行成功</b><span>{testResult.execution_ms} ms</span></header><dl><div><dt>命中结果</dt><dd>{testResult.output.matched===false?'否':'是'}</dd></div><div><dt>输出风险分</dt><dd>{testResult.output.score??'—'}</dd></div><div><dt>输出等级</dt><dd>{testResult.output.level?({red:'红色',orange:'橙色',yellow:'黄色',blue:'蓝色'} as Record<string,string>)[testResult.output.level]:'—'}</dd></div><div><dt>规则版本</dt><dd>v{testResult.version}</dd></div></dl></div>}</div><footer><button className="secondary-button" disabled={busy} onClick={()=>setTestOpen(false)}>关闭</button><button className="primary-button" disabled={busy} onClick={runTest}><Beaker size={16}/>{busy?'执行中…':testResult?'重新执行':'执行测试'}</button></footer></div></div>}
    {editOpen&&<div className="modal-layer"><button className="modal-backdrop" onClick={()=>setEditOpen(false)}/><div className="modal-card test-modal"><header><div><span className="panel__eyebrow">RULE EDITOR</span><h2>创建新版本 · {selected?.rule_id}</h2></div><button className="icon-button" onClick={()=>setEditOpen(false)}><X size={19}/></button></header><div className="test-modal__body"><label>条件组合 JSON（支持 all / any / not）</label><textarea value={conditionText} onChange={event=>setConditionText(event.target.value)}/><label>执行动作 JSON</label><textarea value={actionText} onChange={event=>setActionText(event.target.value)}/></div><footer><button className="secondary-button" onClick={()=>setEditOpen(false)}>取消</button><button className="primary-button" disabled={busy} onClick={saveDraft}><Save size={16}/>保存为新版本</button></footer></div></div>}
    {historyOpen&&<div className="modal-layer"><button className="modal-backdrop" onClick={()=>setHistoryOpen(false)}/><div className="modal-card test-modal"><header><div><span className="panel__eyebrow">VERSION HISTORY</span><h2>{selected?.name}</h2></div><button className="icon-button" onClick={()=>setHistoryOpen(false)}><X size={19}/></button></header><div className="test-modal__body"><div className="backup-list">{history.map(item=><button className="backup-row" key={item.rule_id} onClick={()=>{setSelectedId(item.rule_id);setHistoryOpen(false)}}><span><GitBranch size={16}/><b>v{item.version}</b><small>{item.rule_id}</small></span><span className={`status-chip status-chip--${item.status}`}>{item.status}</span><span>{new Date(item.updated_at).toLocaleString('zh-CN')}</span></button>)}</div></div><footer><button className="secondary-button" onClick={()=>setHistoryOpen(false)}>关闭</button></footer></div></div>}
    {toast&&<div className="toast success"><CheckCircle2 size={16}/>{toast}</div>}
  </div>
}
