import { useState } from 'react';
import { api } from '../api/client';

export default function ImportCsv() {
  const [file, setFile] = useState<File|null>(null);
  const [dry, setDry] = useState(true);
  const [encoding, setEncoding] = useState('latin1');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any|null>(null);
  const [error, setError] = useState<string|undefined>();

  const onSubmit = async () => {
    if (!file) return;
    setBusy(true); setError(undefined); setResult(null);
    try {
      const res = await api.importCsv(file, dry, encoding);
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
          <div>
            <label style={{display:'block',marginBottom:4}}>File Encoding:</label>
            <select 
              value={encoding} 
              onChange={(e)=>setEncoding(e.target.value)}
              style={{background:'#121212',color:'#e0e3ea',border:'1px solid #2a2d35',borderRadius:6,padding:'8px 10px',width:'100%'}}
            >
              <option value="latin1">Latin-1 (ISO-8859-1)</option>
              <option value="utf-8">UTF-8</option>
              <option value="cp1252">Windows-1252</option>
              <option value="ascii">ASCII</option>
            </select>
            <div style={{fontSize:'0.8em',opacity:0.7,marginTop:4}}>
              If you see character encoding errors, try a different encoding
            </div>
          </div>
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