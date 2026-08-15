import { useState, useEffect, useCallback } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { health } from '../api/client'

const NAV_ITEMS = [
  { to: '/dashboard', icon: 'grid', label: '总览' },
  { to: '/nodes', icon: 'server', label: '节点管理' },
  { to: '/acquire', icon: 'layers', label: '代理分配' },
  { to: '/audit', icon: 'file-text', label: '审计日志' },
  { to: '/settings', icon: 'settings', label: '设置' },
]

function NavIcon({ name }: { name: string }) {
  switch (name) {
    case 'grid':
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
      )
    case 'server':
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/>
          <circle cx="8" cy="6" r="1" fill="currentColor" stroke="none"/>
          <circle cx="8" cy="18" r="1" fill="currentColor" stroke="none"/>
        </svg>
      )
    case 'layers':
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
        </svg>
      )
    case 'file-text':
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
      )
    case 'settings':
      return (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="3"/>
          <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
        </svg>
      )
    default: return null
  }
}

const PAGE_TITLES: Record<string, string> = {
  '/': '总览',
  '/dashboard': '总览',
  '/nodes': '节点管理',
  '/acquire': '代理分配',
  '/audit': '审计日志',
  '/settings': '设置',
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false)
  const [apiOnline, setApiOnline] = useState<boolean | null>(null)
  const [version, setVersion] = useState('')
  const location = useLocation()
  const pageTitle = PAGE_TITLES[location.pathname] || 'Proxy Pool'

  const checkHealth = useCallback(async () => {
    try {
      const h = await health()
      setApiOnline(true)
      setVersion(h.version || '')
    } catch {
      setApiOnline(false)
    }
  }, [])

  // Check health on mount and every 30s
  useEffect(() => {
    checkHealth()
    const i = setInterval(checkHealth, 30000)
    return () => clearInterval(i)
  }, [checkHealth])

  // Clock
  const [time, setTime] = useState('')
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }))
    tick()
    const i = setInterval(tick, 1000)
    return () => clearInterval(i)
  }, [])

  return (
    <div className="app-layout">
      <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-brand">
          <div className="brand-icon">
            <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3"/>
              <path d="M12 2v4m0 12v4M2 12h4m12 0h4"/>
              <circle cx="5" cy="5" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="19" cy="5" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="5" cy="19" r="1.5" fill="currentColor" stroke="none"/>
              <circle cx="19" cy="19" r="1.5" fill="currentColor" stroke="none"/>
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-name">Proxy Pool</span>
            <span className="brand-version">{version || '...'}</span>
          </div>
        </div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map(item => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              end={item.to === '/'}
            >
              <NavIcon name={item.icon} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="api-status">
            <span className={`status-dot ${apiOnline === true ? 'online' : apiOnline === false ? 'offline' : ''}`} />
            <span className="status-text">
              {apiOnline === true ? 'API 在线' : apiOnline === false ? 'API 离线' : '连接中...'}
            </span>
          </div>
        </div>
      </aside>

      <main className={`main-content ${collapsed ? 'expanded' : ''}`}>
        <header className="topbar">
          <div className="topbar-left">
            <button className="menu-toggle" onClick={() => setCollapsed(c => !c)} title="切换侧栏">
              <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/>
              </svg>
            </button>
            <h1 className="page-title">{pageTitle}</h1>
          </div>
          <div className="topbar-right">
            <button className="btn btn-sm btn-outline" onClick={checkHealth}>刷新</button>
            <span className="clock">{time}</span>
          </div>
        </header>
        <div className="page-container">
          {children}
        </div>
      </main>
    </div>
  )
}
