import { lazy, Suspense, useEffect, useState } from 'react'
import { AlertTriangle, Globe2, LoaderCircle, RefreshCw } from 'lucide-react'
import type { PageId } from './types'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import { usePlatform } from './usePlatform'

const Dashboard = lazy(() => import('./components/Dashboard'))
const SourcesPage = lazy(() => import('./components/SourcesPage'))
const InternetEventsPage = lazy(() => import('./components/InternetEventsPage'))
const RiskPage = lazy(() => import('./components/RiskPage'))
const TransferPage = lazy(() => import('./components/TransferPage'))
const AdminPage = lazy(() => import('./components/AdminPage'))
const MapDrawer = lazy(() => import('./components/MapDrawer'))

export default function InternetApp() {
  const platform = usePlatform('internet')
  const [page,setPage]=useState<PageId>('dashboard');const [mapOpen,setMapOpen]=useState(false);const [mapActivated,setMapActivated]=useState(false);const [sidebarOpen,setSidebarOpen]=useState(false)
  const openMap=()=>{setMapActivated(true);setMapOpen(true)}
  useEffect(()=>{const open=()=>openMap();window.addEventListener('open-global-map',open);return()=>window.removeEventListener('open-global-map',open)},[])
  if(!platform.user)return <LoginPage mode="internet" onLogin={platform.login}/>
  if(platform.error)return <div className="boot-screen error"><AlertTriangle size={36}/><h1>互联网平台加载失败</h1><p>{platform.error}</p><button className="primary-button" onClick={platform.reload}><RefreshCw size={16}/>重试</button><button className="text-button" onClick={platform.logout}>退出登录</button></div>
  if(!platform.data)return <div className="boot-screen"><div className="boot-mark"><Globe2 size={42}/><span/></div><h1>互联网监测平台</h1><p>正在加载全球公共卫生数据</p><LoaderCircle className="boot-spinner" size={22}/></div>
  const data=platform.data
  const content:Partial<Record<PageId,React.ReactNode>>={dashboard:<Dashboard data={data} onOpenMap={openMap} onNavigate={setPage} mode="internet"/>,sources:<SourcesPage onCollected={platform.reload}/>,events:<InternetEventsPage events={data.events} onCollected={platform.reload}/>,risk:<RiskPage countries={data.countries} alerts={data.alerts} trend={data.trend} rules={data.rules} onOpenMap={openMap} connected/>,transfer:<TransferPage tasks={data.transfers} connected/>,admin:<AdminPage connected/>}
  return <><Layout page={page} onPageChange={setPage} onOpenMap={openMap} connected mode="internet" sidebarOpen={sidebarOpen} onSidebarToggle={()=>setSidebarOpen(v=>!v)} user={platform.user} onLogout={platform.logout} sourceHealth={data.stats.source_health} alertCount={data.alerts.length} lastUpdated={data.stats.last_updated}><Suspense fallback={<div className="page-loader"><LoaderCircle size={28}/><span>正在加载业务模块</span></div>}>{content[page]??content.dashboard}</Suspense></Layout>{mapActivated&&<Suspense fallback={null}><MapDrawer open={mapOpen} onClose={()=>setMapOpen(false)} countries={data.countries} events={data.events} links={data.links} mode="internet"/></Suspense>}</>
}
