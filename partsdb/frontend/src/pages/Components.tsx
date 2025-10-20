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

  // Only send positive page numbers to API
  const params = useMemo(() => ({ 
    page: page > 0 ? String(page) : '1', 
    search 
  }), [page, search]);

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
            <button 
              onClick={()=>setQuery({page:page+1})} 
              disabled={data.results.length < 50 || (!!data.count && page * 50 >= data.count)} 
            >Next</button>
          </div>
        )}
      </div>
    </div>
  );
}