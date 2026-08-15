import { useState, useEffect, useCallback } from 'react'
import { listNodes, getNode, deleteNode, unbanNode, registerNode, NodeInfo } from '../api/client'
import StatusBadge from '../components/StatusBadge'
import { useToast } from '../components/Toast'

export default function Nodes() {
  const [nodes, setNodes] = useState<NodeInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [regionFilter, setRegionFilter] = useState('')
  const [poolFilter, setPoolFilter] = useState('')
  const [showRegister, setShowRegister] = useState(false)
  const [selectedNode, setSelectedNode] = useState<NodeInfo | null>(null)
  const { toast } = useToast()

  const fetchNodes = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const ids = await listNodes({ region: regionFilter || undefined, pool: poolFilter || undefined })
      // Fetch full details for each node
      const details = await Promise.all(ids.map(id => getNode(id).catch(() => null)))
      setNodes(details.filter(Boolean) as NodeInfo[])
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [regionFilter, poolFilter])

  useEffect(() => { fetchNodes() }, [fetchNodes])

  const handleDelete = async (nodeId: string) => {
    if (!confirm(`确认删除节点 ${nodeId}?`)) return
    try {
      await deleteNode(nodeId)
      toast('success', `节点 ${nodeId} 已删除`)
      fetchNodes()
    } catch (e) {
      toast('error', `删除失败: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const handleUnban = async (nodeId: string) => {
    try {
      await unbanNode(nodeId)
      toast('success', `节点 ${nodeId} 已解封`)
      fetchNodes()
    } catch (e) {
      toast('error', `解封失败: ${e instanceof Error ? e.message : 'Unknown'}`)
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
      toast('error', `注册失败: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  return (
    <div>
      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div>
          <input
            type="text" className="form-input" placeholder="区域过滤 (e.g. US)"
            value={regionFilter} onChange={e => setRegionFilter(e.target.value)}
            style={{ width: 160 }}
          />
        </div>
        <div>
          <input
            type="text" className="form-input" placeholder="Pool 过滤 (e.g. ads)"
            value={poolFilter} onChange={e => setPoolFilter(e.target.value)}
            style={{ width: 160 }}
          />
        </div>
        <button className="btn btn-sm btn-outline" onClick={fetchNodes}>查询</button>
        <div style={{ flex: 1 }} />
        <button className="btn btn-sm btn-primary" onClick={() => setShowRegister(true)}>+ 注册节点</button>
      </div>

      {loading ? (
        <div className="loading-spinner"><div className="spinner" /></div>
      ) : error ? (
        <div className="empty-state"><p>{error}</p></div>
      ) : nodes.length === 0 ? (
        <div className="empty-state"><p>无匹配节点</p></div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>节点 ID</th>
                  <th>IP</th>
                  <th>端口</th>
                  <th>区域</th>
                  <th>Pool</th>
                  <th>状态</th>
                  <th>成功率</th>
                  <th>延迟(ms)</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map(n => {
                  const total = (Number(n.success_count) || 0) + (Number(n.fail_count) || 0)
                  const rate = total > 0 ? ((Number(n.success_count) / total) * 100).toFixed(1) : '-'
                  return (
                    <tr key={n.node_id} onClick={() => setSelectedNode(n)} style={{cursor:'pointer'}}>
                      <td className="node-id">{n.node_id}</td>
                      <td>{n.ip}</td>
                      <td>{n.port}</td>
                      <td>{n.region}</td>
                      <td>{n.pool || 'default'}</td>
                      <td><StatusBadge status={n.status} /></td>
                      <td>{rate === '-' ? '-' : rate + '%'}</td>
                      <td>{n.latency || '-'}</td>
                      <td onClick={e => e.stopPropagation()}>
                        <div style={{display:'flex', gap:6}}>
                          {n.status === 'disabled' && (
                            <button className="btn btn-sm btn-success" onClick={() => handleUnban(n.node_id)}>解封</button>
                          )}
                          <button className="btn btn-sm btn-danger" onClick={() => handleDelete(n.node_id)}>删除</button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Node detail modal */}
      {selectedNode && (
        <div className="modal-overlay" onClick={() => setSelectedNode(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>节点详情: {selectedNode.node_id}</h3>
              <button className="modal-close" onClick={() => setSelectedNode(null)}>
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div className="modal-body">
              <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:'8px 24px', fontSize:'0.85rem'}}>
                {Object.entries(selectedNode).map(([k, v]) => (
                  <div key={k} style={{display:'flex', justifyContent:'space-between', padding:'4px 0', borderBottom:'1px solid var(--gray-100)'}}>
                    <span style={{color:'var(--gray-500)', fontWeight:500}}>{k}</span>
                    <span style={{fontWeight:500, maxWidth:200, overflow:'hidden', textOverflow:'ellipsis'}}>{v || '-'}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-outline" onClick={() => setSelectedNode(null)}>关闭</button>
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
                    <input className="form-input" name="region" defaultValue="US" />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Pool</label>
                    <input className="form-input" name="pool" defaultValue="default" />
                  </div>
                  <div className="form-group">
                    <label className="form-label">ISP</label>
                    <input className="form-input" name="isp" placeholder="OCI / AWS" />
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
