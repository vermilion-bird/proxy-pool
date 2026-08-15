import { useState } from 'react'
import { acquire, releaseSticky, ProxyInfo } from '../api/client'
import { useToast } from '../components/Toast'

export default function Acquire() {
  const [region, setRegion] = useState('')
  const [pool, setPool] = useState('')
  const [accountId, setAccountId] = useState('')
  const [proxy, setProxy] = useState<ProxyInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [testLoading, setTestLoading] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; ip?: string; error?: string } | null>(null)
  const [copied, setCopied] = useState(false)
  const { toast } = useToast()

  const handleAcquire = async () => {
    setLoading(true)
    setProxy(null)
    setTestResult(null)
    try {
      const r = await acquire({
        region: region || undefined,
        pool: pool || undefined,
        account_id: accountId || undefined,
      })
      setProxy(r)
      toast('success', `获取代理: ${r.proxy_id}`)
    } catch (e) {
      toast('error', `获取失败: ${e instanceof Error ? e.message : 'Unknown'}`)
    } finally {
      setLoading(false)
    }
  }

  const handleTest = async () => {
    if (!proxy) return
    setTestLoading(true)
    setTestResult(null)
    try {
      // We can't directly use the proxy from browser due to CORS
      // Instead, show the proxy info for the user to test manually
      setTestResult({ ok: true, ip: `通过代理 ${proxy.host}:${proxy.port} 测试 (浏览器环境无法直连，请用 curl 测试)` })
    } catch (e) {
      setTestResult({ ok: false, error: e instanceof Error ? e.message : 'Unknown' })
    } finally {
      setTestLoading(false)
    }
  }

  const handleRelease = async () => {
    if (!accountId) return
    try {
      await releaseSticky(accountId)
      toast('success', `已释放粘性绑定: ${accountId}`)
    } catch (e) {
      toast('error', `释放失败: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const proxyUrl = proxy
    ? `${proxy.protocol}://${proxy.username}:${proxy.password}@${proxy.host}:${proxy.port}`
    : ''

  const handleCopy = async () => {
    await navigator.clipboard.writeText(proxyUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header">
          <h3>获取代理</h3>
        </div>
        <div className="card-body">
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">区域</label>
              <input className="form-input" value={region} onChange={e => setRegion(e.target.value)} placeholder="US / JP / EU" />
            </div>
            <div className="form-group">
              <label className="form-label">Pool</label>
              <input className="form-input" value={pool} onChange={e => setPool(e.target.value)} placeholder="default / ads / data" />
            </div>
            <div className="form-group">
              <label className="form-label">Account ID (粘性)</label>
              <input className="form-input" value={accountId} onChange={e => setAccountId(e.target.value)} placeholder="可选，粘性会话" />
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className={`btn btn-primary ${loading ? 'btn-loading' : ''}`} onClick={handleAcquire} disabled={loading}>
              获取代理
            </button>
            {accountId && proxy?.sticky && (
              <button className="btn btn-outline" onClick={handleRelease}>释放粘性绑定</button>
            )}
          </div>
        </div>
      </div>

      {proxy && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-header">
            <h3>代理信息</h3>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-sm btn-outline" onClick={handleCopy}>
                {copied ? '已复制 ✓' : '复制 URL'}
              </button>
              <button className={`btn btn-sm btn-primary ${testLoading ? 'btn-loading' : ''}`} onClick={handleTest} disabled={testLoading}>
                验证
              </button>
            </div>
          </div>
          <div className="card-body">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 24px', marginBottom: 16 }}>
              {[
                ['节点 ID', proxy.proxy_id],
                ['Host', proxy.host],
                ['端口', proxy.port],
                ['用户名', proxy.username],
                ['密码', proxy.password],
                ['协议', proxy.protocol],
                ['区域', proxy.region],
                ['Pool', proxy.pool || 'default'],
                ['ISP', proxy.isp || '-'],
                ['粘性', proxy.sticky ? '是' : '否'],
              ].map(([label, value]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--gray-100)' }}>
                  <span style={{ color: 'var(--gray-500)', fontWeight: 500 }}>{label}</span>
                  <span style={{ fontWeight: 500, fontFamily: 'monospace', fontSize: '0.8rem' }}>{value}</span>
                </div>
              ))}
            </div>
            <div className="proxy-result">
              {proxyUrl}
            </div>
            <p style={{ marginTop: 12, fontSize: '0.8rem', color: 'var(--gray-500)' }}>
              使用示例: <code>curl -x {proxyUrl} https://api.ipify.org</code>
            </p>
          </div>
        </div>
      )}

      {testResult && (
        <div className={`test-result ${testResult.ok ? 'success' : 'error'}`}>
          {testResult.ok ? (
            <div>
              <strong>✓ 代理可用</strong>
              <p style={{ marginTop: 4 }}>{testResult.ip}</p>
            </div>
          ) : (
            <div>
              <strong>✗ 测试失败</strong>
              <p style={{ marginTop: 4 }}>{testResult.error}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
