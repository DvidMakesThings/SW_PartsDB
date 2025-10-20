const API_BASE = '/api';

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  console.info('[API] →', url, init?.method || 'GET');
  try {
    const res = await fetch(url, {
      headers: { 'Accept': 'application/json', ...(init?.headers || {}) },
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
    http<{count:number; next:string|null; previous:string|null; results:any[]}>(
      `/components/?${new URLSearchParams(params as any).toString()}`
    ),
  listInventory: (params: Record<string, any> = {}) =>
    http<{count:number; next:string|null; previous:string|null; results:any[]}>(
      `/inventory/?${new URLSearchParams(params as any).toString()}`
    ),
  getComponent: (id: string) => http<any>(`/components/${id}/`),

  // CSV import
  importCsv: async (file: File, dryRun: boolean, encoding: string = 'latin1') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', String(dryRun));
    fd.append('encoding', encoding);
    return http<any>('/import/csv/', { method: 'POST', body: fd });
  },
};