import type { ReactNode } from 'react'
import {
  Activity, Anchor, Bell, BookOpenCheck, ChevronDown, CircleUserRound, CloudDownload, DatabaseZap, FileClock,
  Globe2, LayoutDashboard, Menu, Radar, Settings2, ShieldCheck, UsersRound, X,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import type { PageId } from '../types'
import type { SessionUser } from '../auth'

interface LayoutProps {
  children: ReactNode
  page: PageId
  onPageChange: (page: PageId) => void
  onOpenMap: () => void
  connected: boolean
  mode: 'internet' | 'intranet'
  sidebarOpen: boolean
  onSidebarToggle: () => void
  user: SessionUser
  onLogout: () => void
  sourceHealth: { healthy:number; degraded:number; offline:number }
  alertCount: number
  lastUpdated: string
}

const nav: Array<{ id: PageId; label: string; hint: string; icon: LucideIcon; intranet?: boolean; internet?: boolean; roles?: SessionUser['role'][] }> = [
  { id: 'dashboard', label: '态势总览', hint: 'Dashboard', icon: LayoutDashboard },
  { id: 'sources', label: '数据采集', hint: 'Collection', icon: CloudDownload, internet: true, roles: ['system_admin','data_analyst'] },
  { id: 'events', label: '疫情事件', hint: 'Events', icon: Radar },
  { id: 'risk', label: '风险研判', hint: 'Risk analysis', icon: Activity },
  { id: 'passengers', label: '旅客预警', hint: 'Port control', icon: UsersRound, intranet: true },
  { id: 'ports', label: '口岸管理', hint: 'Port registry', icon: Anchor, intranet: true },
  { id: 'transfer', label: '数据摆渡', hint: 'Data transfer', icon: DatabaseZap },
  { id: 'rules', label: '规则引擎', hint: 'Rule engine', icon: BookOpenCheck, intranet: true, roles: ['system_admin','data_analyst'] },
  { id: 'admin', label: '系统管理', hint: 'Administration', icon: Settings2, roles: ['system_admin','auditor'] },
]

export default function Layout({ children, page, onPageChange, onOpenMap, connected, mode, sidebarOpen, onSidebarToggle, user, onLogout, sourceHealth, alertCount, lastUpdated }: LayoutProps) {
  const visibleNav = nav.filter((item) => (!item.intranet || mode === 'intranet') && (!item.internet || mode === 'internet') && (!item.roles || item.roles.includes(user.role)))
  const current = visibleNav.find((item) => item.id === page) ?? visibleNav[0]
  const sourceTotal=sourceHealth.healthy+sourceHealth.degraded+sourceHealth.offline
  const sourcePercent=sourceTotal?sourceHealth.healthy/sourceTotal*100:100
  return (
    <div className={`app-shell theme-${mode}`}>
      <aside className={`sidebar ${sidebarOpen ? 'sidebar--open' : ''}`}>
        <div className="brand">
          <div className="brand__mark"><Globe2 size={25} strokeWidth={1.8} /><span /></div>
          <div className="brand__text"><strong>国境卫士</strong><small>GLOBAL HEALTH SENTINEL</small></div>
          <button className="icon-button sidebar__close" onClick={onSidebarToggle} aria-label="关闭导航"><X size={19} /></button>
        </div>

        <div className="system-mode">
          <div className="system-mode__icon"><ShieldCheck size={18} /></div>
          <div><span>{mode === 'intranet' ? '内网研判预警中心' : '互联网采集监测中心'}</span><small><i className={connected ? 'online' : 'demo'} />{connected ? '业务服务在线' : '业务服务未连接'}</small></div>
        </div>

        <nav className="nav-list" aria-label="主导航">
          <span className="nav-section-label">业务中心</span>
          {visibleNav.map(({ id, label, hint, icon: Icon, intranet }) => (
            <button key={id} className={`nav-item ${page === id ? 'is-active' : ''}`} onClick={() => { onPageChange(id); if (window.innerWidth < 900) onSidebarToggle() }}>
              <Icon size={19} strokeWidth={1.8} />
              <span><b>{label}</b><small>{hint}</small></span>
              {intranet && <em>内网</em>}
            </button>
          ))}
        </nav>

        <div className="sidebar__status">
          <div className="sidebar__status-head"><span>{mode==='internet'?'数据源健康度':'内网离线运行'}</span><strong>{sourcePercent.toFixed(1)}%</strong></div>
          <div className="mini-progress"><span style={{ width: `${sourcePercent}%` }} /></div>
          <div className="sidebar__status-foot"><span>{mode==='internet'?`${sourceHealth.healthy} 正常`:'外网依赖 0'}</span><span>{mode==='internet'?`${sourceHealth.degraded+sourceHealth.offline} 异常`:'资源本地化'}</span></div>
        </div>
        <button className="sidebar__user" onClick={onLogout} title="退出登录">
          <span className="avatar">{user.display_name.slice(0, 1)}</span>
          <span><b>{user.display_name}</b><small>{user.role} · 点击退出</small></span>
          <ChevronDown size={16} />
        </button>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <div className="topbar__title">
            <button className="icon-button mobile-menu" onClick={onSidebarToggle} aria-label="打开导航"><Menu size={20} /></button>
            <div><span>{current.label}</span><small>{current.hint}</small></div>
          </div>
          <div className="topbar__right">
            <button className="map-launch" onClick={onOpenMap}><Globe2 size={17} /><span>全球展示</span><i>LIVE</i></button>
            <button className="icon-button notification" aria-label="查看生效预警" onClick={()=>onPageChange('risk')}><Bell size={19} />{alertCount>0&&<span>{alertCount}</span>}</button>
            <button className="icon-button desktop-user" aria-label="退出登录" title="退出登录" onClick={onLogout}><CircleUserRound size={20} /></button>
          </div>
        </header>
        <main className="content">{children}</main>
        <footer className="app-footer"><span><ShieldCheck size={13} /> 内部系统 · 数据分级保护</span><span><FileClock size={13} /> 最近同步：{new Date(lastUpdated).toLocaleString('zh-CN')}</span></footer>
      </div>
      {sidebarOpen && <button className="sidebar-backdrop" aria-label="关闭导航" onClick={onSidebarToggle} />}
    </div>
  )
}
