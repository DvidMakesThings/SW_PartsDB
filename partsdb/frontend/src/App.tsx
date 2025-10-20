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
