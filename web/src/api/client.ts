const API_BASE = '';

export interface NodeInfo {
  node_id: string;
  ip: string;
  port: string;
  region: string;
  protocol: string;
  username: string;
  password: string;
  status: string;
  success_count: string;
  fail_count: string;
  latency: string;
  current_connections: string;
  pool?: string;
  isp?: string;
  banned_reason?: string;
  consecutive_failures?: string;
  consecutive_successes?: string;
}

export interface ProxyInfo {
  proxy_id: string;
  host: string;
  port: string;
  username: string;
  password: string;
  protocol: string;
  region: string;
  pool: string;
  isp: string;
  sticky: boolean;
}

export interface AuditEvent {
  id: number;
  node_id: string;
  event_type: string;
  old_status: string | null;
  new_status: string | null;
  detail: string | null;
  created_at: string;
}

export interface AuditAcquire {
  id: number;
  node_id: string;
  region: string | null;
  pool: string | null;
  isp: string | null;
  account_id: string | null;
  created_at: string;
}

export interface AuditReport {
  id: number;
  node_id: string;
  success: boolean;
  latency_ms: number;
  created_at: string;
}

export interface VersionInfo {
  name: string;
  version: string;
}

function getHeaders(): Record<string, string> {
  const key = localStorage.getItem('api_key') || '';
  const h: Record<string, string> = {};
  if (key) h['X-API-Key'] = key;
  return h;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { ...getHeaders(), ...(options?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }
  return res.json();
}

// --- Nodes ---
export async function listNodes(params?: { region?: string; pool?: string; isp?: string }) {
  const qs = new URLSearchParams();
  if (params?.region) qs.set('region', params.region);
  if (params?.pool) qs.set('pool', params.pool);
  if (params?.isp) qs.set('isp', params.isp);
  const q = qs.toString();
  const data = await request<{ nodes: string[] }>(`/api/v1/nodes${q ? '?' + q : ''}`);
  return data.nodes;
}

export async function getNode(nodeId: string) {
  return request<NodeInfo>(`/api/v1/nodes/${encodeURIComponent(nodeId)}`);
}

export async function registerNode(body: Record<string, unknown>) {
  return request<{ node_id: string }>('/api/v1/nodes/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function deleteNode(nodeId: string) {
  return request<{ status: string }>(`/api/v1/nodes/${encodeURIComponent(nodeId)}`, {
    method: 'DELETE',
  });
}

export async function unbanNode(nodeId: string) {
  return request<{ node_id: string; status: string }>(
    `/api/v1/nodes/${encodeURIComponent(nodeId)}/unban`,
    { method: 'POST' }
  );
}

// --- Proxy ---
export async function acquire(params?: {
  region?: string; pool?: string; isp?: string; account_id?: string;
}) {
  const qs = new URLSearchParams();
  if (params?.region) qs.set('region', params.region);
  if (params?.pool) qs.set('pool', params.pool);
  if (params?.isp) qs.set('isp', params.isp);
  if (params?.account_id) qs.set('account_id', params.account_id);
  return request<ProxyInfo>(`/api/v1/proxies/acquire?${qs.toString()}`);
}

export async function report(body: { node_id: string; success: boolean; latency: number }) {
  return request<{ status: string }>('/api/v1/proxies/report', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export async function releaseSticky(accountId: string) {
  return request<{ status: string }>('/api/v1/proxies/release', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ account_id: accountId }),
  });
}

// --- Audit ---
export async function listAuditEvents(nodeId?: string, limit = 50) {
  const qs = new URLSearchParams();
  if (nodeId) qs.set('node_id', nodeId);
  qs.set('limit', String(limit));
  return request<{ events: AuditEvent[] }>(`/api/v1/audit/events?${qs.toString()}`);
}

export async function listAuditAcquires(nodeId?: string, limit = 50) {
  const qs = new URLSearchParams();
  if (nodeId) qs.set('node_id', nodeId);
  qs.set('limit', String(limit));
  return request<{ acquires: AuditAcquire[] }>(`/api/v1/audit/acquires?${qs.toString()}`);
}

export async function listAuditReports(nodeId?: string, limit = 50) {
  const qs = new URLSearchParams();
  if (nodeId) qs.set('node_id', nodeId);
  qs.set('limit', String(limit));
  return request<{ reports: AuditReport[] }>(`/api/v1/audit/reports?${qs.toString()}`);
}

// --- Health / Version ---
export async function health() {
  return request<{ status: string; version: string }>('/health');
}

export async function version() {
  return request<VersionInfo>('/version');
}
