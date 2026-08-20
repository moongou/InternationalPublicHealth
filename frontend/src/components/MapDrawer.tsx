import { useEffect, useMemo, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { MapboxOverlay } from '@deck.gl/mapbox'
import { ArcLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers'
import { HeatmapLayer } from '@deck.gl/aggregation-layers'
import { feature } from 'topojson-client'
import worldAtlas from 'world-atlas/countries-110m.json'
import {
  ArrowDownToLine, ChevronLeft, ChevronRight, CircleDot, Flame, Globe2,
  Layers3, Network, Pause, Plane, Play, Search, ShipWheel, UsersRound, X, ZoomIn,
} from 'lucide-react'
import type { Country, DiseaseEvent, Port, RiskLevel, TransferLink } from '../types'
import { requestJson } from '../api'
import { formatNumber, levelMeta } from '../utils'

interface MapDrawerProps {
  open: boolean
  onClose: () => void
  countries: Country[]
  events: DiseaseEvent[]
  links: TransferLink[]
  mode: 'internet' | 'intranet'
}

type LayerId = 'risk' | 'bubbles' | 'heat' | 'links' | 'flows' | 'ports'

interface RiskHistoryPoint {
  country_code: string
  score: number
  level: RiskLevel
  factors: Country['factors']
  calculated_at: string
}

const isoNumeric: Record<string, string> = {
  '180':'COD','076':'BRA','356':'IND','840':'USA','360':'IDN','764':'THA','704':'VNM','608':'PHL','702':'SGP','036':'AUS','250':'FRA','826':'GBR','818':'EGY','484':'MEX','156':'CHN',
}

const layerOptions: Array<{id:LayerId;label:string;desc:string;icon:typeof Layers3}> = [
  {id:'risk',label:'疫情风险分级',desc:'国家风险 Choropleth',icon:Layers3},
  {id:'bubbles',label:'病例事件气泡',desc:'按病例规模显示',icon:CircleDot},
  {id:'heat',label:'疫情热力分布',desc:'事件空间密度',icon:Flame},
  {id:'links',label:'中转风险链路',desc:'第三国中转来华',icon:Network},
  {id:'flows',label:'人员往来强度',desc:'历史对华流量指标',icon:UsersRound},
  {id:'ports',label:'中国口岸分布',desc:'内网布控口岸',icon:Plane},
]

const portTypeLabel: Record<string, string> = { sea: '海港', land: '陆路', air: '空港', rail: '铁路' }

const deckColor = (level: RiskLevel): [number,number,number,number] => level === 'red' ? [255,68,94,220] : level === 'orange' ? [255,159,67,210] : level === 'yellow' ? [245,206,72,200] : [78,161,255,190]

// 将源点经度 wrap 到与目标点最短路径（±180 内），避免远程弧线跨反经线绕远、曲率过大溢出视口
const wrapLng = (source: [number, number], target: [number, number]): [number, number] => {
  let lng = source[0]
  while (lng - target[0] > 180) lng -= 360
  while (lng - target[0] < -180) lng += 360
  return [lng, source[1]]
}

// 反经线（antimeridian）切割：对跨 ±180° 的多边形 ring 做经度 wrap，
// 消除「贯穿左右、无法消除」的水平丝线（俄罗斯/斐济/南极等跨反经线多边形连线所致）
const wrapRing = (ring: number[][]): number[][] => {
  const result = ring.map((p) => [p[0], p[1]] as [number, number])
  let offset = 0
  for (let i = 1; i < ring.length; i++) {
    const delta = ring[i][0] - ring[i - 1][0]
    if (delta > 180) offset -= 360
    else if (delta < -180) offset += 360
    result[i][0] = ring[i][0] + offset
  }
  return result
}

const splitAntimeridian = (geometry: any): any => {
  if (!geometry) return geometry
  if (geometry.type === 'Polygon') return { ...geometry, coordinates: geometry.coordinates.map((ring: number[][]) => wrapRing(ring)) }
  if (geometry.type === 'MultiPolygon') return { ...geometry, coordinates: geometry.coordinates.map((poly: number[][][]) => poly.map((ring: number[][]) => wrapRing(ring))) }
  return geometry
}

export default function MapDrawer({ open, onClose, countries, events, links, mode }: MapDrawerProps) {
  const containerRef=useRef<HTMLDivElement>(null)
  const mapRef=useRef<maplibregl.Map|null>(null)
  const overlayRef=useRef<MapboxOverlay|null>(null)
  const popupRef=useRef<maplibregl.Popup|null>(null)
  const [ready,setReady]=useState(false)
  const [activeLayers,setActiveLayers]=useState<Set<LayerId>>(new Set(['risk','bubbles','links',...(mode==='intranet'?['ports' as LayerId]:[])]))
  const [selected,setSelected]=useState<Country|null>(countries[0]??null)
  const [detailOpen,setDetailOpen]=useState(true)
  const [panelOpen,setPanelOpen]=useState(true)
  const [playing,setPlaying]=useState(false)
  const [timeline,setTimeline]=useState(13)
  const [query,setQuery]=useState('')
  const [disease,setDisease]=useState('全部疾病')
  const [riskHistory,setRiskHistory]=useState<RiskHistoryPoint[]>([])
  const [ports,setPorts]=useState<Port[]>([])
  const [zoom,setZoom]=useState(1.35)

  const timelineDates=useMemo(()=>Array.from({length:14},(_,index)=>{
    const date=new Date();date.setHours(23,59,59,999);date.setDate(date.getDate()-(13-index));return date
  }),[])
  const timelineCutoff=timelineDates[timeline]?.getTime()??Date.now()
  const effectiveCountries=useMemo(()=>countries.map(country=>{
    const point=[...riskHistory].reverse().find(item=>item.country_code===country.code&&new Date(item.calculated_at).getTime()<=timelineCutoff)
    return point?{...country,risk_score:point.score,level:point.level,factors:point.factors,updated_at:point.calculated_at}:country
  }),[countries,riskHistory,timelineCutoff])
  const filteredEvents=useMemo(()=>events.filter(item=>(disease==='全部疾病'||item.disease===disease)&&new Date(item.published_at).getTime()<=timelineCutoff),[events,disease,timelineCutoff])

  const worldData=useMemo(()=>{
    const atlas = worldAtlas as unknown as {objects:{countries:never}}
    const collection=feature(worldAtlas as never,atlas.objects.countries) as unknown as {type:'FeatureCollection';features:Array<{id?:string|number;properties:Record<string,unknown>|null;geometry:unknown}>}
    return {...collection,features:collection.features.map((item)=>{const numeric=String(item.id??'').padStart(3,'0');const code=isoNumeric[numeric];const country=effectiveCountries.find(c=>c.code===code);return {...item,geometry:splitAntimeridian(item.geometry),properties:{...(item.properties??{}),code:country?.code??'',name_zh:country?.name??'',risk_score:country?.risk_score??0,level:country?.level??'none',active_cases:country?.active_cases??0,trend_7d:country?.trend_7d??0}}})}
  },[effectiveCountries])

  useEffect(()=>{if(open&&!riskHistory.length)requestJson<RiskHistoryPoint[]>('/map/risk-history?days=30').then(setRiskHistory).catch(()=>undefined)},[open,riskHistory.length])
  useEffect(()=>{if(open&&mode==='intranet'&&!ports.length)requestJson<{items:Port[]}>('/ports?page_size=2000').then(result=>setPorts(result.items.filter(item=>item.enabled))).catch(()=>undefined)},[open,mode,ports.length])

  useEffect(()=>{
    if(!open||mapRef.current||!containerRef.current)return
    const map=new maplibregl.Map({container:containerRef.current,style:{version:8,sources:{},layers:[{id:'background',type:'background',paint:{'background-color':'#07121f'}}]},center:[55,21],zoom:1.35,minZoom:.8,maxZoom:8,attributionControl:false,canvasContextAttributes:{preserveDrawingBuffer:true}})
    mapRef.current=map
    map.addControl(new maplibregl.NavigationControl({showCompass:false}),'bottom-right')
    map.addControl(new maplibregl.AttributionControl({compact:true,customAttribution:'本地 Natural Earth 边界数据'}),'bottom-right')
    map.on('load',()=>{
      map.addSource('world-risk',{type:'geojson',data:worldData as never})
      map.addLayer({id:'world-fill',type:'fill',source:'world-risk',paint:{'fill-color':['case',['>=',['get','risk_score'],80],'#fa3f5e',['>=',['get','risk_score'],60],'#e8893f',['>=',['get','risk_score'],40],'#c8a944',['>', ['get','risk_score'],0],'#317bb9','#15283a'],'fill-opacity':['case',['>', ['get','risk_score'],0],.72,.48]}})
      map.addLayer({id:'world-outline',type:'line',source:'world-risk',paint:{'line-color':['case',['>', ['get','risk_score'],0],'rgba(180,220,240,.62)','rgba(77,110,137,.5)'],'line-width':['case',['boolean',['feature-state','hover'],false],1.6,.55]}})
      const overlay=new MapboxOverlay({interleaved:true,layers:[]})
      overlayRef.current=overlay
      map.addControl(overlay as unknown as maplibregl.IControl)
      setZoom(map.getZoom())
      map.on('zoom',()=>setZoom(map.getZoom()))
      setReady(true)
    })
    map.on('click','world-fill',(event)=>{
      const code=event.features?.[0]?.properties?.code as string|undefined
      const match=countries.find(country=>country.code===code)
      if(match){setSelected(match);setDetailOpen(true)}
    })
    map.on('mousemove','world-fill',(event)=>{
      map.getCanvas().style.cursor='pointer'
      const props=event.features?.[0]?.properties
      if(!props?.name_zh)return
      popupRef.current?.remove()
      popupRef.current=new maplibregl.Popup({closeButton:false,closeOnClick:false,offset:12,className:'risk-map-popup'}).setLngLat(event.lngLat).setHTML(`<div><b>${props.name_zh}</b><span>风险分 <strong>${props.risk_score}</strong></span><small>活跃病例 ${Number(props.active_cases).toLocaleString('zh-CN')}</small></div>`).addTo(map)
    })
    map.on('mouseleave','world-fill',()=>{map.getCanvas().style.cursor='';popupRef.current?.remove()})
    return()=>{popupRef.current?.remove();map.remove();mapRef.current=null;overlayRef.current=null}
  },[open])

  useEffect(()=>{if(ready){const source=mapRef.current?.getSource('world-risk') as maplibregl.GeoJSONSource|undefined;source?.setData(worldData as never)}},[ready,worldData])

  useEffect(()=>{
    if(!ready||!overlayRef.current)return
    const layers=[]
    if(activeLayers.has('heat'))layers.push(new HeatmapLayer<DiseaseEvent>({id:'event-heat',data:filteredEvents,getPosition:d=>d.coordinates,getWeight:d=>Math.log10(d.cases+10),radiusPixels:58,intensity:1.4,threshold:.08,colorRange:[[20,55,95],[35,130,153],[55,199,165],[245,201,76],[255,128,61],[255,54,88]]}))
    if(activeLayers.has('links'))layers.push(new ArcLayer<TransferLink>({id:'transfer-arcs',data:links,getSourcePosition:d=>wrapLng(d.source as [number,number],d.target as [number,number]),getTargetPosition:d=>d.target,getSourceColor:d=>d.risk>=80?[255,64,92,220]:d.risk>=60?[255,159,67,210]:d.risk>=40?[245,206,72,200]:[78,161,255,190],getTargetColor:d=>d.risk>=80?[255,64,92,160]:[49,216,197,200],getWidth:d=>Math.max(0.8,0.8+d.volume/22+(d.risk>=70?1.3:d.risk>=40?0.6:0)),greatCircle:false,pickable:true}))
    if(activeLayers.has('flows'))layers.push(new ArcLayer<Country>({id:'passenger-flow-arcs',data:effectiveCountries.filter(c=>c.code!=='CHN'),getSourcePosition:d=>wrapLng(d.center as [number,number],[104.2,35.86]),getTargetPosition:()=>[104.2,35.86],getSourceColor:d=>{const t=d.factors.travel??0;return t>=80?[255,64,92,200]:t>=60?[255,159,67,190]:t>=40?[245,206,72,180]:[87,133,255,140]},getTargetColor:[53,211,192,180],getWidth:d=>Math.max(.6,(d.factors.travel??20)/22),greatCircle:false}))
    if(activeLayers.has('bubbles'))layers.push(new ScatterplotLayer<DiseaseEvent>({id:'event-bubbles',data:filteredEvents,getPosition:d=>d.coordinates,getRadius:d=>Math.max(60000,Math.sqrt(d.cases+1)*21000),radiusMinPixels:5,radiusMaxPixels:32,getFillColor:d=>deckColor(d.level),getLineColor:[255,255,255,150],lineWidthMinPixels:1,stroked:true,pickable:true}))
    if(activeLayers.has('ports'))layers.push(new ScatterplotLayer<Port>({id:'china-ports',data:ports,getPosition:d=>[d.longitude,d.latitude],getRadius:()=>90000,radiusUnits:'meters',radiusMinPixels:5,radiusMaxPixels:13,getFillColor:d=>deckColor(d.risk_level),getLineColor:[220,245,255,240],lineWidthMinPixels:1.2,stroked:true,pickable:true}))
    if(activeLayers.has('ports')&&zoom>=4)layers.push(new TextLayer<Port>({id:'china-port-labels',data:ports,getPosition:d=>[d.longitude,d.latitude],getText:d=>d.name,getSize:13,getColor:[222,240,252,235],getPixelOffset:[0,-16],getAlignmentBaseline:'top',fontFamily:'PingFang SC, Microsoft YaHei, sans-serif'}))
    overlayRef.current.setProps({layers,getTooltip:({object}:{object?:DiseaseEvent|TransferLink|Port})=>{if(!object)return null;if('title'in object)return {html:`<b>${object.title}</b><br/><span>${object.country} · ${formatNumber(object.cases)} 例</span>`,style:{backgroundColor:'#0d1c2b',color:'#dfeefa',fontSize:'12px',border:'1px solid #29435a',borderRadius:'8px'}};if('origin'in object)return {html:`<b>${object.origin} → 中国</b><br/><span>中转：${object.via} · 风险 ${object.risk}</span>`};if('port_type'in object)return {html:`<b>${object.name}</b><br/><span>${portTypeLabel[object.port_type]??object.port_type} · ${levelMeta[object.risk_level].label}风险</span>`};return null}})
  },[ready,activeLayers,filteredEvents,links,effectiveCountries,ports,zoom])

  useEffect(()=>{if(!ready||!mapRef.current)return;mapRef.current.setLayoutProperty('world-fill','visibility',activeLayers.has('risk')?'visible':'none');mapRef.current.setLayoutProperty('world-outline','visibility',activeLayers.has('risk')?'visible':'none')},[activeLayers,ready])
  useEffect(()=>{setSelected(current=>current?(effectiveCountries.find(country=>country.code===current.code)??current):(effectiveCountries[0]??null))},[effectiveCountries])
  useEffect(()=>{if(!playing)return;const timer=window.setInterval(()=>setTimeline(v=>v>=13?0:v+1),850);return()=>clearInterval(timer)},[playing])
  useEffect(()=>{if(open&&mapRef.current)window.setTimeout(()=>mapRef.current?.resize(),330)},[open])

  const toggle=(id:LayerId)=>setActiveLayers(current=>{const next=new Set(current);next.has(id)?next.delete(id):next.add(id);return next})
  const locate=()=>{const match=effectiveCountries.find(c=>c.name.includes(query)||c.code.toLowerCase()===query.toLowerCase());if(match){setSelected(match);setDetailOpen(true);mapRef.current?.flyTo({center:match.center,zoom:3.8,duration:1000})}}
  const exportMap=()=>{const url=mapRef.current?.getCanvas().toDataURL('image/png');if(!url)return;const a=document.createElement('a');a.href=url;a.download=`全球公共卫生态势_${Date.now()}.png`;a.click()}
  const diseases=['全部疾病',...Array.from(new Set(events.map(event=>event.disease)))]
  const selectedDate=timelineDates[timeline]??new Date()
  const dateText=(date:Date)=>`${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
  const affectedCountries=new Set(filteredEvents.map(event=>event.country_code)).size
  const newEvents=filteredEvents.filter(event=>new Date(event.published_at).getTime()>timelineCutoff-86_400_000).length
  const timelineStart=timelineDates[0].getTime()
  const timelineSpan=Math.max(1,timelineDates[13].getTime()-timelineStart)
  const eventMarkers=events.map(event=>({id:event.id,left:(new Date(event.published_at).getTime()-timelineStart)/timelineSpan*100,level:event.level})).filter(item=>item.left>=0&&item.left<=100).slice(0,40)

  return <section className={`map-drawer ${open?'is-open':''}`} aria-hidden={!open}>
    <header className="map-header"><div className="map-title"><button className="collapse-map" onClick={onClose}><ChevronLeft size={19}/>收叠</button><span className="map-logo"><Globe2 size={21}/></span><div><b>全球公共卫生态势地图</b><small>GLOBAL PUBLIC HEALTH SITUATION MAP</small></div><span className="map-live"><i/>LIVE</span></div><div className="map-toolbar"><label><Search size={15}/><input value={query} onChange={e=>setQuery(e.target.value)} onKeyDown={e=>e.key==='Enter'&&locate()} placeholder="定位国家 / 地区"/></label><select value={disease} onChange={e=>setDisease(e.target.value)}>{diseases.map(item=><option key={item}>{item}</option>)}</select><button onClick={()=>setPanelOpen(v=>!v)} className={panelOpen?'active':''}><Layers3 size={16}/>图层</button><button onClick={exportMap}><ArrowDownToLine size={16}/>导出</button><button className="map-close" onClick={onClose}><X size={18}/></button></div></header>
    <div className="map-stage">
      <div ref={containerRef} className="map-container"/>
      {!ready&&<div className="map-loading"><Globe2 size={32}/><span>正在载入本地地图数据…</span></div>}
      <aside className={`layer-panel ${panelOpen?'is-open':''}`}><header><span><Layers3 size={17}/>观察角度</span><button onClick={()=>setPanelOpen(false)}><X size={15}/></button></header><div className="disease-theme"><span className="disease-theme__label">疫病主题</span><div className="disease-theme__tabs">{diseases.map(d=><button key={d} className={`disease-tab ${disease===d?'is-active':''}`} onClick={()=>setDisease(d)}>{d}</button>)}</div></div>{layerOptions.filter(item=>mode==='intranet'||item.id!=='ports').map(({id,label,desc,icon:Icon})=><button key={id} className={activeLayers.has(id)?'active':''} onClick={()=>toggle(id)}><span className="layer-icon"><Icon size={17}/></span><span><b>{label}</b><small>{desc}</small></span><i><em/></i></button>)}<div className="map-legend"><span>国家风险分级</span>{(['red','orange','yellow','blue'] as RiskLevel[]).map(level=><div key={level}><i style={{background:levelMeta[level].color}}/><span>{levelMeta[level].label}色</span><b>{level==='red'?'≥80':level==='orange'?'60—79':level==='yellow'?'40—59':'<40'}</b></div>)}</div></aside>
      <div className="map-summary"><div><span>截至所选日事件</span><strong>{filteredEvents.length}</strong></div><i/><div><span>红色风险国家</span><strong className="red">{effectiveCountries.filter(country=>country.level==='red').length}</strong></div><i/><div><span>影响国家</span><strong>{affectedCountries}</strong></div><i/><div><span>所选日新增</span><strong className="orange">+{newEvents}</strong></div></div>
      <button className="map-zoom-world" onClick={()=>mapRef.current?.flyTo({center:[55,21],zoom:1.35})}><ZoomIn size={16}/>全球视图</button>
      <aside className={`country-detail ${detailOpen&&selected?'is-open':''}`}>
        {selected&&<><header><div><span className="country-code-large">{selected.code.slice(0,2)}</span><div><small>{selected.region}</small><h2>{selected.name}</h2></div></div><button onClick={()=>setDetailOpen(false)}><ChevronRight size={18}/></button></header><div className="country-risk-head"><div className={`country-score country-score--${selected.level}`}><strong>{selected.risk_score}</strong><span>综合风险分</span></div><div><span className={`level-badge level-badge--${selected.level}`}><i/>{levelMeta[selected.level].label}色风险</span><small>较7日前 <b className={selected.trend_7d>=0?'bad':'good'}>{selected.trend_7d>=0?'+':''}{selected.trend_7d}%</b></small></div></div><div className="country-metrics"><div><span>活跃病例</span><b>{formatNumber(selected.active_cases)}</b></div><div><span>累计死亡</span><b>{formatNumber(selected.deaths)}</b></div><div><span>对华往来</span><b>{selected.factors.travel}</b></div></div><section><h3>六因子风险画像</h3><div className="factor-bars">{Object.entries(selected.factors).map(([key,value])=><div key={key}><span>{({severity:'疾病严重性',transmission:'传播速度',scale:'病例规模',travel:'对华往来',transit:'中转风险',capacity:'防控能力'} as Record<string,string>)[key]}</span><i><em style={{width:`${value}%`,background:value>=80?'#ff526b':value>=60?'#f2a94c':'#37cdbf'}}/></i><b>{value}</b></div>)}</div></section><section><h3>截至所选日的最近事件</h3><div className="country-events">{filteredEvents.filter(e=>e.country_code===selected.code).slice(0,3).map(event=><div key={event.id}><i className={event.level}/><span><b>{event.title}</b><small>{event.source} · {new Date(event.published_at).toLocaleDateString('zh-CN')}</small></span></div>)}{!filteredEvents.some(e=>e.country_code===selected.code)&&<p>所选时间前无重点事件</p>}</div></section><button className="country-analysis-button" onClick={()=>setDetailOpen(false)}>收起国家研判 <ChevronRight size={15}/></button></>}
      </aside>
      {selected&&!detailOpen&&<button className="reopen-detail" onClick={()=>setDetailOpen(true)}><ChevronLeft size={16}/>{selected.name}</button>}
      <div className="timeline-control"><button className="timeline-play" onClick={()=>setPlaying(v=>!v)}>{playing?<Pause size={16}/>:<Play size={16}/>}</button><div className="timeline-date"><b>{selectedDate.getFullYear()}</b><span>{String(selectedDate.getMonth()+1).padStart(2,'0')} / {String(selectedDate.getDate()).padStart(2,'0')}</span></div><div className="timeline-track"><div className="timeline-labels"><span>{dateText(timelineDates[0])}</span><span>{dateText(timelineDates[3])}</span><span>{dateText(timelineDates[6])}</span><span>{dateText(timelineDates[9])}</span><span>今天</span></div><input type="range" min="0" max="13" value={timeline} onChange={e=>setTimeline(Number(e.target.value))}/><div className="timeline-events">{eventMarkers.map(item=><i key={item.id} style={{left:`${item.left}%`,background:item.level==='red'?'#ff586f':'#f5b74a'}}/>)}</div></div><span className="timeline-speed">1×</span></div>
      <div className="map-coordinates"><ShipWheel size={13}/> EPSG:4326 · 离线地图资源</div>
    </div>
  </section>
}
