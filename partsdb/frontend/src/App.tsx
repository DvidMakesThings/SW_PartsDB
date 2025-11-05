import { Route, Routes, Navigate } from 'react-router-dom';
import Components from './pages/Components';
import Inventory from './pages/Inventory';
import ImportCsv from './pages/ImportCsv';
import ComponentDetail from './pages/ComponentDetail';
import Navbar from './components/layout/Navbar';

export default function App() {
  return (
    <div className="min-h-screen bg-[--bg]">
      <Navbar />
      <main className="container mx-auto px-4 py-6 max-w-7xl">
        <Routes>
          <Route path="/" element={<Navigate to="/components" replace />} />
          <Route path="/components" element={<Components />} />
          <Route path="/components/:id" element={<ComponentDetail />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/import" element={<ImportCsv />} />
          <Route path="*" element={
            <div className="flex items-center justify-center h-96">
              <div className="text-center">
                <h1 className="text-2xl font-bold mb-2">404 - Not Found</h1>
                <p className="text-secondary">The page you're looking for doesn't exist.</p>
              </div>
            </div>
          } />
        </Routes>
      </main>
    </div>
  );
}
