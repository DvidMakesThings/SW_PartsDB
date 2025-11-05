const API_BASE = import.meta.env.VITE_API_BASE || 'http://192.168.0.25:8000/api';

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

  listAttachments: (params: Record<string, any> = {}) =>
    http<{count:number; next:string|null; previous:string|null; results:any[]}>(
      `/attachments/?${new URLSearchParams(params as any).toString()}`
    ),

  uploadAttachment: async (componentId: string, file: File, type: string) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('component_id', componentId);
    fd.append('type', type);
    return http<any>('/attachments/', { method: 'POST', body: fd });
  },

  // CSV import (force UTF-8 + semicolon delimiter)
  importCsv: async (file: File, dryRun: boolean, encoding: string = 'utf-8') => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', String(dryRun));
    fd.append('encoding', encoding);
    fd.append('delimiter', ';'); // ← add this
    return http<any>('/import/csv/', { method: 'POST', body: fd });
  },
};

// Export individual functions for backwards compatibility
export const { getComponent, listAttachments, uploadAttachment } = api;
