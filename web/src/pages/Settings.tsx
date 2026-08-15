import { useState, useEffect } from 'react'
import { version } from '../api/client'
import { useToast } from '../components/Toast'

export default function Settings() {
  const [apiKey, setApiKey] = useState(localStorage.getItem('api_key') || '')
  const [ver, setVer] = useState('')
  const { toast } = useToast()

  useEffect(() => {
    version().then(v => setVer(v.version)).catch(() => {})
  }, [])

  const handleSave = () => {
    if (apiKey) {
      localStorage.setItem('api_key', apiKey)
    } else {
      localStorage.removeItem('api_key')
    }
    toast('success', 'API Key 已保存（存储在浏览器本地）')
  }

  return (
    <div>
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header"><h3>API 认证</h3></div>
        <div className="card-body">
          <div className="form-group">
            <label className="form-label">API Key</label>
            <input
              className="form-input" type="password" value={apiKey}
              onChange={e => setApiKey(e.target.value)}
              placeholder="sk-xxxxxxxx"
              style={{ maxWidth: 480 }}
            />
            <p style={{ marginTop: 6, fontSize: '0.75rem', color: 'var(--gray-500)' }}>
              用于认证管理 API 请求。若服务端未配置 PP_API_KEYS 则可留空。
              Key 仅存储在浏览器 localStorage，不会发送到其他地方。
            </p>
          </div>
          <button className="btn btn-primary" onClick={handleSave}>保存</button>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-header"><h3>系统信息</h3></div>
        <div className="card-body">
          <div style={{ display: 'grid', gap: 8, maxWidth: 400 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--gray-100)' }}>
              <span style={{ color: 'var(--gray-500)' }}>版本</span>
              <span style={{ fontWeight: 600 }}>{ver || '...'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--gray-100)' }}>
              <span style={{ color: 'var(--gray-500)' }}>API 地址</span>
              <span style={{ fontWeight: 600 }}>{window.location.origin}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--gray-100)' }}>
              <span style={{ color: 'var(--gray-500)' }}>Prometheus</span>
              <a href={window.location.origin.replace(':8082', ':9090')} target="_blank" rel="noopener">:9090 →</a>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid var(--gray-100)' }}>
              <span style={{ color: 'var(--gray-500)' }}>Grafana</span>
              <a href={window.location.origin.replace(':8082', ':3000')} target="_blank" rel="noopener">:3000 →</a>
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header"><h3>快速链接</h3></div>
        <div className="card-body">
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <a href="/metrics" target="_blank" className="btn btn-outline btn-sm">Prometheus 指标</a>
            <a href="/docs" target="_blank" className="btn btn-outline btn-sm">API 文档 (Swagger)</a>
            <a href="/health" target="_blank" className="btn btn-outline btn-sm">健康检查</a>
          </div>
        </div>
      </div>
    </div>
  )
}
