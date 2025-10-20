### “Replace stubs with working pages (Components, Inventory, Import)”

**Goal:** Implement real, working pages that hit the backend API. Keep the on-screen error overlay from `main.tsx`. If anything errors, show it on screen and in console.

**Do exactly this; stop on first error.**

#### 0) Keep these as-is

* `index.html`
* `vite.config.ts`
* `src/main.tsx` (with the global error overlay)

#### 1) Add a tiny API client with verbose logs

`partsdb/frontend/src/api/client.ts`

```ts
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
  importCsv: async (file: File, dryRun: boolean) => {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('dry_run', String(dryRun));
    return http<any>('/import/csv', { method: 'POST', body: fd });
  },
};
```

#### 2) Replace `src/App.tsx` with real routing and nav

`partsdb/frontend/src/App.tsx`

```tsx
import { useEffect } from 'react';
import { Link, Route, Routes, Navigate } from 'react-router-dom';
import Components from './pages/Components';
import Inventory from './pages/Inventory';
import ImportCsv from './pages/ImportCsv';
import ComponentDetail from './pages/ComponentDetail';

function Nav() {
  useEffect(() => console.info('[UI] Nav mounted'), []);
  return (
    <div style={{background:'#161616',borderBottom:'1px solid #2a2d35'}}>
      <div style={{display:'flex',gap:16,alignItems:'center',padding:'10px 16px',maxWidth:1200,margin:'0 auto'}}>
        <div style={{fontWeight:700}}>PartsDB</div>
        <Link to="/components">Components</Link>
        <Link to="/inventory">Inventory</Link>
        <Link to="/import">Import</Link>
        <a href="http://127.0.0.1:8000/admin/" target="_blank" rel="noreferrer" style={{marginLeft:'auto'}}>Admin</a>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <>
      <Nav />
      <Routes>
        <Route path="/" element={<Navigate to="/components" replace />} />
        <Route path="/components" element={<Components />} />
        <Route path="/components/:id" element={<ComponentDetail />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/import" element={<ImportCsv />} />
        <Route path="*" element={<div style={{padding:24}}>Not Found</div>} />
      </Routes>
    </>
  );
}
```

#### 3) Implement **Components** page (list + filters + pagination)

`partsdb/frontend/src/pages/Components.tsx`

```tsx
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';

export default function Components() {
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get('page') || 1);
  const search = sp.get('search') || '';
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{count:number; results:any[]}>({count:0, results:[]});
  const [error, setError] = useState<string|undefined>();

  const params = useMemo(() => ({ page: String(page), search }), [page, search]);

  useEffect(() => {
    (async () => {
      setLoading(true); setError(undefined);
      try { setData(await api.listComponents(params)); }
      catch (e:any) { setError(e?.message || 'Failed to load'); }
      finally { setLoading(false); }
    })();
  }, [params]);

  const setQuery = (q: Partial<{page:number;search:string}>) => {
    const next = new URLSearchParams(sp);
    if (q.page !== undefined) next.set('page', String(q.page));
    if (q.search !== undefined) {
      next.set('search', q.search);
      next.set('page', '1');
    }
    setSp(next, { replace: true });
  };

  return (
    <div style={{maxWidth:1200,margin:'0 auto',padding:16}}>
      <div style={{background:'#1e1e1e',border:'1px solid #2a2d35',borderRadius:10,padding:16}}>
        <h2 style={{marginTop:0}}>Components</h2>

        <div style={{display:'flex',gap:8,marginBottom:12}}>
          <input
            placeholder="Search by MPN / Manufacturer"
            value={search}
            onChange={(e)=>setQuery({search:e.target.value})}
            style={{flex:1,background:'#121212',color:'#e0e3ea',border:'1px solid #2a2d35',borderRadius:6,padding:'8px 10px'}}
          />
        </div>

        {error && <div style={{color:'#f87171',marginBottom:8}}>Error: {error}</div>}
        {loading ? <div>Loading…</div> : (
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'collapse'}}>
              <thead>
                <tr style={{background:'#181818'}}>
                  {['MPN','Manufacturer','Value','Package','Category','In Stock','Actions'].map(h=>(
                    <th key={h} style={{textAlign:'left',padding:'8px 10px',borderBottom:'1px solid #2a2d35'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.results.map((c:any)=>(
                  <tr key={c.id} style={{borderBottom:'1px solid #2a2d35'}}>
                    <td style={{padding:'8px 10px'}}><Link to={`/components/${c.id}`}>{c.mpn}</Link></td>
                    <td style={{padding:'8px 10px'}}>{c.manufacturer}</td>
                    <td style={{padding:'8px 10px'}}>{c.value || '-'}</td>
                    <td style={{padding:'8px 10px'}}>{c.package_name || '-'}</td>
                    <td style={{padding:'8px 10px'}}>{c.category_l1 || 'Unsorted'}</td>
                    <td style={{padding:'8px 10px'}}>{c.in_stock ? 'Yes' : 'No'}</td>
                    <td style={{padding:'8px 10px'}}><Link to={`/components/${c.id}`}>View</Link></td>
                  </tr>
                ))}
                {data.results.length === 0 && <tr><td colSpan={7} style={{padding:10,opacity:.7}}>No results</td></tr>}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && data.count > 0 && (
          <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:12}}>
            <button onClick={()=>setQuery({page:Math.max(1,page-1)})} disabled={page<=1}>Prev</button>
            <div style={{opacity:.8,alignSelf:'center'}}>Page {page}</div>
            <button onClick={()=>setQuery({page:page+1})} disabled={data.results.length===0}>Next</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

#### 4) Implement **ComponentDetail** (readonly is fine for now)

`partsdb/frontend/src/pages/ComponentDetail.tsx`

```tsx
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';

export default function ComponentDetail() {
  const { id } = useParams<{id:string}>();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string|undefined>();

  useEffect(() => {
    (async()=>{
      setLoading(true); setError(undefined);
      try { setData(await api.getComponent(id!)); }
      catch(e:any){ setError(e?.message || 'Failed'); }
      finally { setLoading(false); }
    })();
  }, [id]);

  return (
    <div style={{maxWidth:1000,margin:'0 auto',padding:16}}>
      <div style={{background:'#1e1e1e',border:'1px solid #2a2d35',borderRadius:10,padding:16}}>
        <div style={{marginBottom:8}}><Link to="/components">← Back</Link></div>
        {loading ? 'Loading…' : error ? <div style={{color:'#f87171'}}>Error: {error}</div> : (
          <>
            <h2 style={{marginTop:0}}>{data.mpn}</h2>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
              <Field label="Manufacturer" value={data.manufacturer}/>
              <Field label="Package" value={data.package_name}/>
              <Field label="Value" value={data.value}/>
              <Field label="Category" value={data.category_l1}/>
              <Field label="Datasheet URL" value={data.url_datasheet}/>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
function Field({label,value}:{label:string;value:any}) {
  return (
    <div style={{border:'1px solid #2a2d35',borderRadius:8,padding:10}}>
      <div style={{opacity:.7,fontSize:12,marginBottom:4}}>{label}</div>
      <div>{value || '-'}</div>
    </div>
  );
}
```

#### 5) Implement **Inventory** page (list + pagination)

`partsdb/frontend/src/pages/Inventory.tsx`

```tsx
import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api } from '../api/client';

export default function Inventory() {
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get('page') || 1);
  const search = sp.get('search') || '';
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{count:number; results:any[]}>({count:0, results:[]});
  const [error, setError] = useState<string|undefined>();

  const params = useMemo(() => ({ page: String(page), search }), [page, search]);

  useEffect(() => {
    (async () => {
      setLoading(true); setError(undefined);
      try { setData(await api.listInventory(params)); }
      catch (e:any) { setError(e?.message || 'Failed to load'); }
      finally { setLoading(false); }
    })();
  }, [params]);

  const setQuery = (q: Partial<{page:number;search:string}>) => {
    const next = new URLSearchParams(sp);
    if (q.page !== undefined) next.set('page', String(q.page));
    if (q.search !== undefined) { next.set('search', q.search); next.set('page','1'); }
    setSp(next, { replace: true });
  };

  return (
    <div style={{maxWidth:1200,margin:'0 auto',padding:16}}>
      <div style={{background:'#1e1e1e',border:'1px solid #2a2d35',borderRadius:10,padding:16}}>
        <h2 style={{marginTop:0}}>Inventory</h2>
        <div style={{display:'flex',gap:8,marginBottom:12}}>
          <input placeholder="Search…" value={search} onChange={(e)=>setQuery({search:e.target.value})}
            style={{flex:1,background:'#121212',color:'#e0e3ea',border:'1px solid #2a2d35',borderRadius:6,padding:'8px 10px'}}/>
        </div>
        {error && <div style={{color:'#f87171',marginBottom:8}}>Error: {error}</div>}
        {loading ? 'Loading…' : (
          <div style={{overflowX:'auto'}}>
            <table style={{width:'100%',borderCollapse:'collapse'}}>
              <thead>
                <tr style={{background:'#181818'}}>
                  {['MPN','Qty','UoM','Location','Supplier','Price'].map(h=>(
                    <th key={h} style={{textAlign:'left',padding:'8px 10px',borderBottom:'1px solid #2a2d35'}}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.results.map((it:any)=>(
                  <tr key={it.id} style={{borderBottom:'1px solid #2a2d35'}}>
                    <td style={{padding:'8px 10px'}}>{it.component?.mpn || '-'}</td>
                    <td style={{padding:'8px 10px'}}>{it.quantity}</td>
                    <td style={{padding:'8px 10px'}}>{it.uom || 'pcs'}</td>
                    <td style={{padding:'8px 10px'}}>{it.storage_location || '-'}</td>
                    <td style={{padding:'8px 10px'}}>{it.supplier || '-'}</td>
                    <td style={{padding:'8px 10px'}}>{it.price_each ?? '-'}</td>
                  </tr>
                ))}
                {data.results.length === 0 && <tr><td colSpan={6} style={{padding:10,opacity:.7}}>No results</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        {!loading && data.count > 0 && (
          <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:12}}>
            <button onClick={()=>setQuery({page:Math.max(1,page-1)})} disabled={page<=1}>Prev</button>
            <div style={{opacity:.8,alignSelf:'center'}}>Page {page}</div>
            <button onClick={()=>setQuery({page:page+1})} disabled={data.results.length===0}>Next</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

#### 6) Implement **ImportCsv** page (upload + dry-run)

`partsdb/frontend/src/pages/ImportCsv.tsx`

```tsx
import { useState } from 'react';
import { api } from '../api/client';

export default function ImportCsv() {
  const [file, setFile] = useState<File|null>(null);
  const [dry, setDry] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any|null>(null);
  const [error, setError] = useState<string|undefined>();

  const onSubmit = async () => {
    if (!file) return;
    setBusy(true); setError(undefined); setResult(null);
    try {
      const res = await api.importCsv(file, dry);
      setResult(res);
    } catch (e:any) {
      setError(e?.message || 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{maxWidth:800,margin:'0 auto',padding:16}}>
      <div style={{background:'#1e1e1e',border:'1px solid #2a2d35',borderRadius:10,padding:16}}>
        <h2 style={{marginTop:0}}>Import CSV</h2>
        <div style={{display:'grid',gap:12}}>
          <input type="file" accept=".csv,text/csv" onChange={(e)=>setFile(e.target.files?.[0] || null)} />
          <label style={{display:'flex',alignItems:'center',gap:8}}>
            <input type="checkbox" checked={dry} onChange={(e)=>setDry(e.target.checked)} />
            Dry run (do not commit changes)
          </label>
          <button onClick={onSubmit} disabled={!file || busy}>{busy ? 'Uploading…' : 'Upload'}</button>
          {error && <div style={{color:'#f87171'}}>Error: {error}</div>}
          {result && (
            <div style={{border:'1px solid #2a2d35',borderRadius:8,padding:10}}>
              <div>created: {result.created}</div>
              <div>updated: {result.updated}</div>
              <div>skipped: {result.skipped}</div>
              <div>errors: {result.errors?.length || 0}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```
