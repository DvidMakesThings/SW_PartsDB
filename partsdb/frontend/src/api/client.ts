// frontend/src/api/client.ts

// Build a base that always points at the API root.
// - If VITE_API_BASE is unset -> ''  => base becomes '/api'
// - If VITE_API_BASE='http://backend:8000'       => base becomes 'http://backend:8000/api'
// - If VITE_API_BASE='http://192.168.0.25:8000'  => base becomes 'http://192.168.0.25:8000/api'
// - If VITE_API_BASE already ends with '/api'     => used as-is (normalized)
const RAW_BASE = (import.meta as any).env?.VITE_API_BASE || '';
const NORMALIZED_BASE = RAW_BASE.replace(/\/+$/, '');
const API_BASE =
  NORMALIZED_BASE === ''
    ? '/api'
    : /\/api$/i.test(NORMALIZED_BASE)
    ? NORMALIZED_BASE
    : `${NORMALIZED_BASE}/api`;

// Join base + path, accepting 'components/..', '/components/..' or '/api/components/..'
function buildUrl(path: string): string {
  let p = path || '';
  if (!p.startsWith('/')) p = '/' + p;
  // If caller already passes '/api/...', don't double it
  if (p.startsWith('/api/')) return `${NORMALIZED_BASE}${p}` || p;
  return `${API_BASE}${p}`;
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = buildUrl(path);
  console.info('[API] →', url, init?.method || 'GET');

  try {
    const res = await fetch(url, {
      headers: {
        Accept: 'application/json',
        // do NOT set Content-Type when body is FormData (browser sets it)
        ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
        ...(init?.headers || {}),
      },
      credentials: 'include',
      ...init,
    });

    const ct = res.headers.get('content-type') || '';
    const body = ct.includes('application/json') ? await res.json() : await res.text();

    console.info('[API] ←', url, res.status, body);
    if (!res.ok) throw new Error(typeof body === 'string' ? body : JSON.stringify(body));
    return body as T;
  } catch (err) {
    console.error('[API] ✖', url, err);
    (window as any).showError?.(`API error: ${url}`, err);
    throw err;
  }
}

export const api = {
  // DRF list endpoints (paginated)
  listComponents: (params: Record<string, any> = {}) =>
    http<{ count: number; next: string | null; previous: string | null; results: any[] }>(
      `/components/?${new URLSearchParams(params as any).toString()}`
    ),

  listInventory: (params: Record<string, any> = {}) =>
    http<{ count: number; next: string | null; previous: string | null; results: any[] }>(
      `/inventory/?${new URLSearchParams(params as any).toString()}`
    ),

  getComponent: (id: string) => http<any>(`/components/${id}/`),

  listAttachments: (params: Record<string, any> = {}) =>
    http<{ count: number; next: string | null; previous: string | null; results: any[] }>(
      `/attachments/?${new URLSearchParams(params as any).toString()}`
    ),

  uploadAttachment: async (componentId: string, file: File, type: string) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('component_id', componentId);
    fd.append('type', type);
    // no content-type header on purpose (FormData)
    return http<any>('/attachments/', { method: 'POST', body: fd });
  },

  // CSV import
  importCsv: async (file: File, dryRun: boolean, encoding: string = 'latin1') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', String(dryRun));
    fd.append('encoding', encoding);
    return http<any>('/import/csv/', { method: 'POST', body: fd });
  },
};

// Export individual functions for backwards compatibility
export const { getComponent, listAttachments, uploadAttachment } = api;
