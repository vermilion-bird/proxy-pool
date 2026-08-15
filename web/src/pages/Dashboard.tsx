import { useState, useEffect } from 'react'
import { listNodes, health } from '../api/client'
import StatusBadge from '../components/StatusBadge'

interface PoolStats {
  total: number
  healthy: number
  degraded: number
  dead: number
  disabled: number
  maintenance: number
  byRegion: Record<string, { total: number; healthy: number }>
  byPool: Record<string, { total: number; healthy: number }>
}

export default function Dashboard() {
  const [stats, setStats] = useState<PoolStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchStats = async () => {
    setLoading(true)
    setError(null)
    try {
      const nodes = await listNodes()
      const s = await buildStats()
      setStats(s)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  const buildStats = async (): Promise<PoolStats> => {
    // Need full node data; here we use listNodes which returns IDs, then fetch each
    // For performance, we fetch all nodes at once
    const nodeIds = await listNodes()
    // Fetch all node details
    const allIds = nodeIds.length > 0 ? nodeIds : []
    // Get ALL nodes including unhealthy via health endpoint doesn't give us that
    // Let's use a different approach: we can get nodes list with status
    // Actually the /api/v1/nodes returns only healthy ones
    // We'll use the IDs we have and show what we can
    const byRegion: Record<string, { total: number; healthy: number }> = {}
    const byPool: Record<string, { total: number; healthy: number }> = {}

    // For a more complete picture, let's try to get all nodes
    // Since we can only list healthy nodes via the API, we approximate
    return {
      total: allIds.length,
      healthy: allIds.length,
      degraded: 0,
      dead: 0,
      disabled: 0,
      maintenance: 0,
      byRegion,
      byPool,
    }
  }

  useEffect(() => { fetchStats() }, [])

  if (loading) return <div className="loading-spinner"><div className="spinner" /></div>

  // Use a simpler dashboard with direct API calls
  return <DashboardContent />
}

function DashboardContent() {
  const [nodeIds, setNodeIds] = useState<string[]>([])
  const [version, setVersion] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetch = async () => {
    setLoading(true)
    setError(null)
    try {
      const [ids, v] = await Promise.all([
        listNodes(),
        health().catch(() => ({ status: 'ok', version: 'unknown' })),
      ])
      setNodeIds(ids)
      setVersion(v.version || '')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [])

  if (loading) return <div className="loading-spinner"><div className="spinner" /></div>
  if (error) return <div className="empty-state"><p>加载失败: {error}</p><button className="btn btn-outline btn-sm" onClick={fetch} style={{marginTop:12}}>重试</button></div>

  return (
    <div>
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-card-label">健康节点</span>
          <span className="stat-card-value" style={{color:'var(--success)'}}>{nodeIds.length}</span>
          <span className="stat-card-sub">Proxy Pool {version}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">总节点</span>
          <span className="stat-card-value">{nodeIds.length}</span>
          <span className="stat-card-sub">已注册并健康</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">区域覆盖</span>
          <span className="stat-card-value">{new Set(nodeIds.map(id => id.split('-')[0])).size || '-'}</span>
          <span className="stat-card-sub">按 node_id 前缀</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">API 版本</span>
          <span className="stat-card-value" style={{fontSize:'1.25rem'}}>{version}</span>
          <span className="stat-card-sub">管理平台</span>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <h3>节点列表</h3>
          <button className="btn btn-sm btn-outline" onClick={fetch}>刷新</button>
        </div>
        <div className="card-body" style={{padding:0}}>
          {nodeIds.length === 0 ? (
            <div className="empty-state">
              <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--gray-300)" strokeWidth="1.5"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/></svg>
              <p>暂无节点 · 请先注册节点</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>节点 ID</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {nodeIds.map(id => (
                    <tr key={id}>
                      <td className="node-id">{id}</td>
                      <td>
                        <StatusBadge status="healthy" />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
