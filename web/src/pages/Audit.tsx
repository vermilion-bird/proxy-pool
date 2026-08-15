import { useState, useEffect, useCallback } from 'react'
import { listAuditEvents, listAuditAcquires, listAuditReports, AuditEvent, AuditAcquire, AuditReport } from '../api/client'

type Tab = 'events' | 'acquires' | 'reports'

export default function Audit() {
  const [tab, setTab] = useState<Tab>('events')
  const [nodeId, setNodeId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [events, setEvents] = useState<AuditEvent[]>([])
  const [acquires, setAcquires] = useState<AuditAcquire[]>([])
  const [reports, setReports] = useState<AuditReport[]>([])

  const fetch = useCallback(async () => {
    setLoading(true)
    setError(null)
    const nid = nodeId || undefined
    try {
      if (tab === 'events') {
        const r = await listAuditEvents(nid)
        setEvents(r.events)
      } else if (tab === 'acquires') {
        const r = await listAuditAcquires(nid)
        setAcquires(r.acquires)
      } else {
        const r = await listAuditReports(nid)
        setReports(r.reports)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed'
      if (msg.includes('401')) {
        setError('需要 API Key (请在设置页配置)')
      } else if (msg.includes('404') || msg.includes('500')) {
        setError('审计功能需要启用 PostgreSQL (PG_ENABLED=1)')
        setEvents([])
        setAcquires([])
        setReports([])
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }, [tab, nodeId])

  useEffect(() => { fetch() }, [fetch])

  const formatTime = (t: string) => {
    try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
  }

  return (
    <div>
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <div className="tab-bar" style={{ flex: 1 }}>
          <button className={`tab-btn ${tab === 'events' ? 'active' : ''}`} onClick={() => setTab('events')}>
            生命周期事件
          </button>
          <button className={`tab-btn ${tab === 'acquires' ? 'active' : ''}`} onClick={() => setTab('acquires')}>
            分配记录
          </button>
          <button className={`tab-btn ${tab === 'reports' ? 'active' : ''}`} onClick={() => setTab('reports')}>
            上报记录
          </button>
        </div>
        <div>
          <input
            type="text" className="form-input" placeholder="节点 ID 过滤"
            value={nodeId} onChange={e => setNodeId(e.target.value)}
            style={{ width: 200 }}
          />
        </div>
        <button className="btn btn-sm btn-outline" onClick={fetch}>查询</button>
      </div>

      {loading ? (
        <div className="loading-spinner"><div className="spinner" /></div>
      ) : error ? (
        <div className="empty-state"><p>{error}</p></div>
      ) : (
        <div className="card" style={{ overflow: 'hidden' }}>
          <div className="table-wrap">
            {tab === 'events' && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>节点</th>
                    <th>事件类型</th>
                    <th>旧状态</th>
                    <th>新状态</th>
                    <th>详情</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr><td colSpan={7} style={{textAlign:'center',padding:24,color:'var(--gray-400)'}}>暂无记录</td></tr>
                  ) : events.map(e => (
                    <tr key={e.id}>
                      <td>{e.id}</td>
                      <td className="node-id">{e.node_id}</td>
                      <td>{e.event_type}</td>
                      <td>{e.old_status || '-'}</td>
                      <td>{e.new_status || '-'}</td>
                      <td>{e.detail || '-'}</td>
                      <td>{formatTime(e.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === 'acquires' && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>节点</th>
                    <th>区域</th>
                    <th>Pool</th>
                    <th>ISP</th>
                    <th>Account</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {acquires.length === 0 ? (
                    <tr><td colSpan={7} style={{textAlign:'center',padding:24,color:'var(--gray-400)'}}>暂无记录</td></tr>
                  ) : acquires.map(a => (
                    <tr key={a.id}>
                      <td>{a.id}</td>
                      <td className="node-id">{a.node_id}</td>
                      <td>{a.region || '-'}</td>
                      <td>{a.pool || '-'}</td>
                      <td>{a.isp || '-'}</td>
                      <td>{a.account_id || '-'}</td>
                      <td>{formatTime(a.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {tab === 'reports' && (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>节点</th>
                    <th>结果</th>
                    <th>延迟(ms)</th>
                    <th>时间</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.length === 0 ? (
                    <tr><td colSpan={5} style={{textAlign:'center',padding:24,color:'var(--gray-400)'}}>暂无记录</td></tr>
                  ) : reports.map(r => (
                    <tr key={r.id}>
                      <td>{r.id}</td>
                      <td className="node-id">{r.node_id}</td>
                      <td><span style={{color: r.success ? 'var(--success)' : 'var(--danger)', fontWeight:600}}>{r.success ? '成功' : '失败'}</span></td>
                      <td>{r.latency_ms}</td>
                      <td>{formatTime(r.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
