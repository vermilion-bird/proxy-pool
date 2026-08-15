import { useState, useEffect, useCallback, useMemo } from 'react'
import { listNodes, deleteNode, unbanNode, registerNode, enrichNode, enrichAllNodes, NodeInfo } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { useToast } from '../components/Toast'

type SortField = 'node_id' | 'ip' | 'region' | 'pool' | 'isp' | 'status' | 'latency' | 'protocol'
type SortDir = 'asc' | 'desc'

export default function Nodes() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [regionFilter, setRegionFilter] = useState('')
  const [poolFilter, setPoolFilter] = useState('')
  const [ispFilter, setIspFilter] = useState('')
  const [includeAll, setIncludeAll] = useState(true)
  const [search, setSearch] = useState('')
  const [sortField, setSortField] = useState<SortField>('node_id')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  const [showRegister, setShowRegister] = useState(false)
  const [selectedNode, setSelectedNode] = useState<NodeInfo | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const { toast } = useToast()

  const fetchNodes = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listNodes({
        region: regionFilter || undefined,
        pool: poolFilter || undefined,
        isp: ispFilter || undefined,
        include_all: includeAll,
      })
      setNodes(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [regionFilter, poolFilter, ispFilter, includeAll])

  useEffect(() => { fetchNodes() }, [fetchNodes])

  // Auto-refresh every 15s
  useEffect(() => {
    const i = setInterval(fetchNodes, 15000)
    return () => clearInterval(i)
  }, [fetchNodes])

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('asc')
    }
  }

  // Filtered + sorted nodes
  const displayNodes = useMemo(() => {
    let result = [...nodes]
    // Search filter
    if (search) {
      const q = search.toLowerCase()
      result = result.filter(n =>
        n.node_id.toLowerCase().includes(q) ||
        n.ip.includes(q) ||
        n.region.toLowerCase().includes(q) ||
        (n.pool || 'default').toLowerCase().includes(q) ||
        (n.isp || '').toLowerCase().includes(q)
      )
    }
    // Sort
    result.sort((a, b) => {
      let va: string = (a[sortField] || '').toString()
      let vb: string = (b[sortField] || '').toString()
      // Numeric sort for latency
      if (sortField === 'latency') {
        return sortDir === 'asc' ? parseFloat(va) - parseFloat(vb) : parseFloat(vb) - parseFloat(va)
      }
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va)
    })
    return result
  }, [nodes, search, sortField, sortDir])

  const stats = useMemo(() => {
    const healthy = nodes.filter(n => n.status === 'healthy').length
    const degraded = nodes.filter(n => n.status === 'degraded').length
    const dead = nodes.filter(n => n.status === 'dead').length
    const disabled = nodes.filter(n => n.status === 'disabled').length
    const regions = [...new Set(nodes.map(n => n.region))]
    const pools = [...new Set(nodes.map(n => n.pool || 'default'))]
    return { healthy, degraded, dead, disabled, total: nodes.length, regions, pools }
  }, [nodes])

  const handleDelete = async (nodeId: string) => {
    if (!confirm('确认删除节点 ' + nodeId + '?')) return
    try {
      await deleteNode(nodeId)
      toast('success', '节点 ' + nodeId + ' 已删除')
      fetchNodes()
    } catch (e) {
      toast('error', '删除失败: ' + (e instanceof Error ? e.message : 'Unknown'))
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm('确认删除 ' + selectedIds.size + ' 个节点?')) return
    let ok = 0
    for (const id of selectedIds) {
      try { await deleteNode(id); ok++ } catch { /* skip */ }
    }
    toast('success', '已删除 ' + ok + '/' + selectedIds.size + ' 个节点')
    setSelectedIds(new Set())
    fetchNodes()
  }

  const handleUnban = async (nodeId: string) => {
    try {
      await unbanNode(nodeId)
      toast('success', '节点 ' + nodeId + ' 已解封')
      fetchNodes()
    } catch (e) {
      toast('error', '解封失败: ' + (e instanceof Error ? e.message : 'Unknown'))
    }
  }

  const [enriching, setEnriching] = useState(false)
  const handleEnrichAll = async () => {
    setEnriching(true)
    try {
      const r = await enrichAllNodes()
      toast('success', r.total + ' 个节点地理信息已刷新')
      fetchNodes()
    } catch (e) {
      toast('error', '批量查询失败: ' + (e instanceof Error ? e.message : 'Unknown'))
    } finally {
      setEnriching(false)
    }
  }

  const handleEnrichOne = async (nodeId: string) => {
    try {
      await enrichNode(nodeId)
      toast('success', nodeId + ' 地理信息已刷新')
      fetchNodes()
    } catch (e) {
      toast('error', '查询失败: ' + (e instanceof Error ? e.message : 'Unknown'))
    }
  }

  const handleRegister = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const form = e.currentTarget
    const data = Object.fromEntries(new FormData(form))
    try {
      await registerNode({
        node_id: data.node_id,
        ip: data.ip,
        port: Number(data.port) || 3128,
        region: data.region || 'US',
        pool: data.pool || 'default',
        isp: data.isp || '',
        protocol: data.protocol || 'http',
        username: data.username || '3proxy',
        password: data.password,
      })
      toast('success', '节点注册成功')
      setShowRegister(false)
      form.reset()
      fetchNodes()
    } catch (e) {
      toast('error', '注册失败: ' + (e instanceof Error ? e.message : 'Unknown'))
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selectedIds.size === displayNodes.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(displayNodes.map(n => n.node_id)))
    }
  }

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <span style={{color:'var(--gray-300)', marginLeft:2}}>⇅</span>
    return <span style={{color:'var(--primary)', marginLeft:2}}>{sortDir === 'asc' ? '↑' : '↓'}</span>
  }

  const successRate = (n: NodeInfo) => {
    const total = (Number(n.success_count) || 0) + (Number(n.fail_count) || 0)
    if (total === 0) return '-'
    return ((Number(n.success_count) / total) * 100).toFixed(1) + '%'
  }

  const latencyDisplay = (n: NodeInfo) => {
    const v = parseFloat(n.latency)
    if (isNaN(v) || v <= 0) return '-'
    return v < 1000 ? v.toFixed(1) + 'ms' : (v / 1000).toFixed(2) + 's'
  }

  const FIELD_LABELS: Record<string, string> = {
    node_id: 'Node ID', ip: 'IP', port: '端口', region: '区域', pool: 'Pool',
    isp: 'ISP', protocol: '协议', status: '状态', latency: '延迟',
    success_count: '成功', fail_count: '失败', consecutive_failures: '连续失败',
    consecutive_successes: '连续成功', current_connections: '连接数',
    password: '密码', username: '用户名', banned_reason: '封禁原因',
  }

  return (
    <div>
      {/* Stats bar */}
      <div className="stats-grid" style={{marginBottom: 16}}>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem'}}>总计</span>
          <span className="stat-card-value" style={{fontSize:'1.3rem'}}>{stats.total}</span>
        </div>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem', color:'var(--success)'}}>健康</span>
          <span className="stat-card-value" style={{fontSize:'1.3rem', color:'var(--success)'}}>{stats.healthy}</span>
        </div>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem', color:'var(--warning)'}}>降级</span>
          <span className="stat-card-value" style={{fontSize:'1.3rem', color:'var(--warning)'}}>{stats.degraded}</span>
        </div>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem', color:'var(--danger)'}}>故障</span>
          <span className="stat-card-value" style={{fontSize:'1.3rem', color:'var(--danger)'}}>{stats.dead}</span>
        </div>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem'}}>区域</span>
          <span className="stat-card-value" style={{fontSize:'1.1rem'}}>{stats.regions.join(', ') || '-'}</span>
        </div>
        <div className="stat-card" style={{padding: '12px 16px'}}>
          <span className="stat-card-label" style={{fontSize:'0.7rem'}}>Pool</span>
          <span className="stat-card-value" style={{fontSize:'1.1rem'}}>{stats.pools.join(', ') || '-'}</span>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          type="text" className="form-input" placeholder="🔍 搜索..."
          value={search} onChange={e => setSearch(e.target.value)}
          style={{ width: 200 }}
        />
        <select className="form-select" value={regionFilter} onChange={e => setRegionFilter(e.target.value)} style={{ width: 120 }}>
          <option value="">全部区域</option>
          {stats.regions.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="form-select" value={poolFilter} onChange={e => setPoolFilter(e.target.value)} style={{ width: 130 }}>
          <option value="">全部 Pool</option>
          {stats.pools.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <input
          type="text" className="form-input" placeholder="ISP 过滤"
          value={ispFilter} onChange={e => setIspFilter(e.target.value)}
          style={{ width: 110 }}
        />
        <label style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: '0.8rem', cursor: 'pointer', userSelect: 'none' }}>
          <input type="checkbox" checked={includeAll} onChange={e => setIncludeAll(e.target.checked)} />
          全部状态
        </label>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
          {displayNodes.length} / {nodes.length} 节点
        </span>
        <button className="btn btn-sm btn-outline" onClick={fetchNodes}>刷新</button>
        <button className={`btn btn-sm btn-outline ${enriching ? 'btn-loading' : ''}`} onClick={handleEnrichAll} disabled={enriching}>
          🌐 查询全部
        </button>
        <button className="btn btn-sm btn-primary" onClick={() => setShowRegister(true)}>+ 注册</button>
        {selectedIds.size > 0 && (
          <button className="btn btn-sm btn-danger" onClick={handleBatchDelete}>
            删除 ({selectedIds.size})
          </button>
        )}
      </div>

      {loading && nodes.length === 0 ? (
        <div className="loading-spinner"><div className="spinner" /></div>
      ) : error ? (
        <div className="empty-state"><p>{error}</p></div>
      ) : displayNodes.length === 0 ? (
        <div className="empty-state">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="var(--gray-300)" strokeWidth="1.5">
            <rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/>
          </svg>
          <p>无匹配节点 · 调整过滤条件或注册新节点</p>
        </div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{width: 36}}>
                    <input type="checkbox" checked={selectedIds.size === displayNodes.length && displayNodes.length > 0}
                      onChange={toggleAll} />
                  </th>
                  <th onClick={() => handleSort('node_id')} style={{cursor:'pointer'}}>节点 ID <SortIcon field="node_id" /></th>
                  <th onClick={() => handleSort('ip')} style={{cursor:'pointer'}}>IP <SortIcon field="ip" /></th>
                  <th>端口</th>
                  <th>国家</th>
                  <th>区域</th>
                  <th>城市</th>
                  <th onClick={() => handleSort('pool')} style={{cursor:'pointer'}}>Pool <SortIcon field="pool" /></th>
                  <th>ISP / 运营商</th>
                  <th onClick={() => handleSort('protocol')} style={{cursor:'pointer'}}>协议 <SortIcon field="protocol" /></th>
                  <th onClick={() => handleSort('status')} style={{cursor:'pointer'}}>状态 <SortIcon field="status" /></th>
                  <th>成功率</th>
                  <th onClick={() => handleSort('latency')} style={{cursor:'pointer'}}>延迟 <SortIcon field="latency" /></th>
                  <th>连续失败</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {displayNodes.map(n => (
                  <tr key={n.node_id} style={{cursor:'pointer'}}>
                    <td onClick={e => e.stopPropagation()}>
                      <input type="checkbox" checked={selectedIds.has(n.node_id)} onChange={() => toggleSelect(n.node_id)} />
                    </td>
                    <td className="node-id" onClick={() => setSelectedNode(n)}>{n.node_id}</td>
                    <td onClick={() => setSelectedNode(n)}>{n.ip}</td>
                    <td onClick={() => setSelectedNode(n)}>{n.port}</td>
                    <td onClick={() => setSelectedNode(n)}>
                      {n.geo_flag_emoji ? <span style={{marginRight:4}}>{n.geo_flag_emoji}</span> : null}
                      <span style={{fontWeight:500}}>{n.geo_country || n.geo_country_code || n.region || '-'}</span>
                    </td>
                    <td onClick={() => setSelectedNode(n)}>{n.geo_region || '-'}</td>
                    <td onClick={() => setSelectedNode(n)}>{n.geo_city || '-'}</td>
                    <td onClick={() => setSelectedNode(n)}>{n.pool || 'default'}</td>
                    <td onClick={() => setSelectedNode(n)}>
                      <span style={{fontSize:'0.78rem', color:'var(--gray-500)'}}>{n.geo_isp || n.isp || '-'}</span>
                    </td>
                    <td onClick={() => setSelectedNode(n)}><span style={{fontWeight:600, color:'var(--primary)'}}>{n.protocol}</span></td>
                    <td onClick={() => setSelectedNode(n)}><StatusBadge status={n.status} /></td>
                    <td onClick={() => setSelectedNode(n)}>{successRate(n)}</td>
                    <td onClick={() => setSelectedNode(n)}>{latencyDisplay(n)}</td>
                    <td onClick={() => setSelectedNode(n)}>
                      <span style={{color: Number(n.consecutive_failures||0) > 0 ? 'var(--danger)' : 'var(--gray-400)', fontWeight:600}}>
                        {n.consecutive_failures || '0'}
                      </span>
                    </td>
                    <td onClick={e => e.stopPropagation()}>
                      <div style={{display:'flex', gap:3, flexWrap:'wrap'}}>
                        {!n.geo_enriched && (
                          <button className="btn btn-sm btn-outline" style={{fontSize:'0.7rem', padding:'3px 6px'}}
                            onClick={() => handleEnrichOne(n.node_id)} title="查询地理信息">🌐</button>
                        )}
                        {n.status === 'disabled' && (
                          <button className="btn btn-sm btn-success" onClick={() => handleUnban(n.node_id)}>解封</button>
                        )}
                        <button className="btn btn-sm btn-outline" style={{color:'var(--danger)', borderColor:'var(--danger)'}}
                          onClick={() => handleDelete(n.node_id)}>删除</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Node detail modal */}
      {selectedNode && (
        <div className="modal-overlay" onClick={() => setSelectedNode(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{width: 560}}>
            <div className="modal-header">
              <h3>
                <StatusBadge status={selectedNode.status} />
                <span style={{marginLeft:8}}>{selectedNode.node_id}</span>
              </h3>
              <button className="modal-close" onClick={() => setSelectedNode(null)}>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div className="modal-body">
              {/* Geo info card */}
              <div style={{background:'var(--gray-50)', borderRadius:'var(--radius)', padding:'12px 16px', marginBottom:16, display:'flex', alignItems:'center', gap:12, flexWrap:'wrap'}}>
                {selectedNode.geo_flag_emoji && <span style={{fontSize:'2rem'}}>{selectedNode.geo_flag_emoji}</span>}
                <div>
                  <div style={{fontWeight:700, fontSize:'0.95rem'}}>
                    {[selectedNode.geo_city, selectedNode.geo_region].filter(Boolean).join(', ') || selectedNode.ip}
                  </div>
                  <div style={{fontSize:'0.8rem', color:'var(--gray-500)'}}>
                    {[selectedNode.geo_country, selectedNode.geo_continent].filter(Boolean).join(' · ')}
                  </div>
                  {selectedNode.geo_isp && <div style={{fontSize:'0.75rem', color:'var(--gray-400)', marginTop:2}}>
                    ISP: {selectedNode.geo_isp}{selectedNode.geo_asn ? ' (AS' + selectedNode.geo_asn + ')' : ''}
                  </div>}
                  {!selectedNode.geo_enriched && (
                    <button className="btn btn-sm btn-outline" style={{marginTop:4, fontSize:'0.7rem'}}
                      onClick={() => { handleEnrichOne(selectedNode.node_id); setSelectedNode(null); }}>🌐 查询地理信息</button>
                  )}
                </div>
              </div>
              <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:'6px 20px', fontSize:'0.82rem'}}>
                {Object.entries(selectedNode)
                  .filter(([,v]) => v !== undefined && v !== '')
                  .map(([k, v]) => (
                    <div key={k} style={{display:'flex', justifyContent:'space-between', padding:'5px 0', borderBottom:'1px solid var(--gray-100)'}}>
                      <span style={{color:'var(--gray-500)', fontWeight:500, fontSize:'0.75rem'}}>{FIELD_LABELS[k] || k}</span>
                      <span style={{fontWeight:500, maxWidth:180, overflow:'hidden', textOverflow:'ellipsis', textAlign:'right', fontFamily: k.includes('password') ? 'monospace' : 'inherit'}}>
                        {k === 'latency' ? latencyDisplay(selectedNode) : (v || '-')}
                      </span>
                    </div>
                  ))}
              </div>
              {/* Proxy URL */}
              <div className="proxy-result" style={{marginTop:16}}>
                {selectedNode.protocol}://{selectedNode.username}:{selectedNode.password}@{selectedNode.ip}:{selectedNode.port}
              </div>
              <p style={{marginTop:8, fontSize:'0.75rem', color:'var(--gray-500)'}}>
                curl -x {selectedNode.protocol}://{selectedNode.username}:{selectedNode.password}@{selectedNode.ip}:{selectedNode.port} https://api.ipify.org
              </p>
            </div>
            <div className="modal-footer" style={{justifyContent:'space-between'}}>
              <div style={{display:'flex', gap:6}}>
                {selectedNode.status === 'disabled' && (
                  <button className="btn btn-sm btn-success" onClick={() => { handleUnban(selectedNode.node_id); setSelectedNode(null); }}>解封</button>
                )}
                <button className="btn btn-sm btn-outline" style={{color:'var(--danger)'}}
                  onClick={() => { handleDelete(selectedNode.node_id); setSelectedNode(null); }}>删除节点</button>
              </div>
              <button className="btn btn-outline btn-sm" onClick={() => setSelectedNode(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* Register modal */}
      {showRegister && (
        <div className="modal-overlay" onClick={() => setShowRegister(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <form onSubmit={handleRegister}>
              <div className="modal-header">
                <h3>注册新节点</h3>
                <button type="button" className="modal-close" onClick={() => setShowRegister(false)}>
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
              <div className="modal-body">
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Node ID *</label>
                    <input className="form-input" name="node_id" required placeholder="proxy-1.2.3.4" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">IP *</label>
                    <input className="form-input" name="ip" required placeholder="1.2.3.4" />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">端口</label>
                    <input className="form-input" name="port" defaultValue="3128" type="number" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">区域</label>
                    <select className="form-select" name="region" defaultValue="US">
                      <option value="US">US</option><option value="JP">JP</option>
                      <option value="EU">EU</option><option value="AP">AP</option>
                      <option value="CN">CN</option>
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Pool</label>
                    <input className="form-input" name="pool" defaultValue="default" placeholder="default/ads/data" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">ISP</label>
                    <input className="form-input" name="isp" placeholder="OCI / AWS / Azure" />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">用户名</label>
                    <input className="form-input" name="username" defaultValue="3proxy" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">密码 *</label>
                    <input className="form-input" name="password" required type="password" />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">协议</label>
                  <select className="form-select" name="protocol" defaultValue="http">
                    <option value="http">HTTP</option>
                    <option value="socks5">SOCKS5</option>
                  </select>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline" onClick={() => setShowRegister(false)}>取消</button>
                <button type="submit" className="btn btn-primary">注册</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
