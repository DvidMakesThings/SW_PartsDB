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