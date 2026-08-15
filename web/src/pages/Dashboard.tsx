import { useState, useEffect } from 'react'
import { listNodes, health, NodeInfo } from '../api/client'
import StatusBadge from '../components/StatusBadge'

export default function Dashboard() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [version, setVersion] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetch = async () => {
    setLoading(true)
    setError(null)
    try {
      const [data, v] = await Promise.all([
        listNodes({ include_all: true }),
        health().catch(() => ({ status: 'ok', version: 'unknown' })),
      ])
      setNodes(data)
      setVersion(v.version || '')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetch() }, [])

  // Auto-refresh every 20s
  useEffect(() => {
    const i = setInterval(fetch, 20000)
    return () => clearInterval(i)
  }, [])

  if (loading && nodes.length === 0) return <div className="loading-spinner"><div className="spinner" /></div>
  if (error) return <div className="empty-state"><p>加载失败: {error}</p><button className="btn btn-outline btn-sm" onClick={fetch} style={{marginTop:12}}>重试</button></div>

  const healthy = nodes.filter(n => n.status === 'healthy')
  const degraded = nodes.filter(n => n.status === 'degraded')
  const dead = nodes.filter(n => n.status === 'dead')
  const disabled = nodes.filter(n => n.status === 'disabled')
  const regions = [...new Set(nodes.map(n => n.region))]
  const pools = [...new Set(nodes.map(n => n.pool || 'default'))]

  return (
    <div>
      <div className="stats-grid">
        <div className="stat-card">
          <span className="stat-card-label">总节点</span>
          <span className="stat-card-value">{nodes.length}</span>
          <span className="stat-card-sub">{regions.length} 个区域</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label" style={{color:'var(--success)'}}>健康</span>
          <span className="stat-card-value" style={{color:'var(--success)'}}>{healthy.length}</span>
          <span className="stat-card-sub">{healthy.length > 0 ? Math.round(healthy.length/nodes.length*100) : 0}%</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label" style={{color:'var(--warning)'}}>降级</span>
          <span className="stat-card-value" style={{color:'var(--warning)'}}>{degraded.length}</span>
          <span className="stat-card-sub">需关注</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label" style={{color:'var(--danger)'}}>故障/禁用</span>
          <span className="stat-card-value" style={{color:'var(--danger)'}}>{dead.length + disabled.length}</span>
          <span className="stat-card-sub">dead: {dead.length} · disabled: {disabled.length}</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">版本</span>
          <span className="stat-card-value" style={{fontSize:'1.25rem'}}>{version}</span>
          <span className="stat-card-sub">管理平台 API</span>
        </div>
        <div className="stat-card">
          <span className="stat-card-label">Pool 覆盖</span>
          <span className="stat-card-value" style={{fontSize:'1.1rem'}}>{pools.length}</span>
          <span className="stat-card-sub">{pools.join(', ') || '-'}</span>
        </div>
      </div>

      {/* Region distribution */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header"><h3>区域分布</h3></div>
        <div className="card-body">
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {regions.map(r => {
              const rNodes = nodes.filter(n => n.region === r)
              const rHealthy = rNodes.filter(n => n.status === 'healthy').length
              return (
                <div key={r} style={{
                  background: 'var(--gray-50)', borderRadius: 'var(--radius)',
                  padding: '12px 20px', minWidth: 120, textAlign: 'center',
                  border: '1px solid var(--gray-200)'
                }}>
                  <div style={{fontSize:'1.3rem', fontWeight:700}}>{r}</div>
                  <div style={{fontSize:'0.8rem', color:'var(--success)'}}>{rHealthy}/{rNodes.length} 健康</div>
                </div>
              )
            })}
            {regions.length === 0 && <span style={{color:'var(--gray-400)'}}>暂无数据</span>}
          </div>
        </div>
      </div>

      {/* Recent nodes table */}
      <div className="card">
        <div className="card-header">
          <h3>节点概览</h3>
          <button className="btn btn-sm btn-outline" onClick={fetch}>刷新</button>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {nodes.length === 0 ? (
            <div className="empty-state">
              <p>暂无节点 · 请前往「节点管理」注册</p>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>节点 ID</th>
                    <th>IP</th>
                    <th>区域</th>
                    <th>Pool</th>
                    <th>状态</th>
                    <th>成功率</th>
                    <th>延迟</th>
                  </tr>
                </thead>
                <tbody>
                  {nodes.slice(0, 20).map(n => {
                    const total = (Number(n.success_count) || 0) + (Number(n.fail_count) || 0)
                    const rate = total > 0 ? ((Number(n.success_count) / total) * 100).toFixed(1) + '%' : '-'
                    const lat = parseFloat(n.latency)
                    return (
                      <tr key={n.node_id}>
                        <td className="node-id">{n.node_id}</td>
                        <td>{n.ip}</td>
                        <td>{n.region}</td>
                        <td>{n.pool || 'default'}</td>
                        <td><StatusBadge status={n.status} /></td>
                        <td>{rate}</td>
                        <td>{isNaN(lat) || lat <= 0 ? '-' : lat.toFixed(1) + 'ms'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
