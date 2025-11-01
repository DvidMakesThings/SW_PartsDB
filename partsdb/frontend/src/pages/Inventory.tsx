import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, RefreshCw, ChevronLeft, ChevronRight, Package, Plus } from 'lucide-react';
import { api } from '../api/client';

export default function Inventory() {
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get('page') || 1);
  const search = sp.get('search') || '';
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{count:number; results:any[]}>({count:0, results:[]});
  const [error, setError] = useState<string|undefined>();

  const params = useMemo(() => ({
    page: page > 0 ? String(page) : '1',
    search
  }), [page, search]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(undefined);
      try {
        setData(await api.listInventory(params));
      }
      catch (e:any) {
        setError(e?.message || 'Failed to load inventory');
      }
      finally {
        setLoading(false);
      }
    })();
  }, [params]);

  const setQuery = (q: Partial<{page:number;search:string}>) => {
    const next = new URLSearchParams(sp);
    if (q.page !== undefined) next.set('page', String(q.page));
    if (q.search !== undefined) {
      next.set('search', q.search);
      next.set('page','1');
    }
    setSp(next, { replace: true });
  };

  const totalPages = Math.ceil(data.count / 50);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Inventory</h1>
          <p className="text-secondary">
            Track and manage component stock
            {data.count > 0 && <span className="ml-2">· {data.count.toLocaleString()} items</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--surface] hover:bg-[--surface-hover] border border-[--border] text-sm font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Item
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="card p-4">
        <div className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[--text-tertiary]" />
            <input
              type="text"
              placeholder="Search inventory..."
              value={search}
              onChange={(e) => setQuery({search: e.target.value})}
              className="w-full pl-10 pr-4 py-2.5 bg-[--bg] border border-[--border] rounded-lg text-sm focus:border-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20 transition-all"
            />
          </div>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="card p-4 border-[--error] bg-red-500/5">
          <p className="text-[--error] text-sm font-medium">Error: {error}</p>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-96">
            <div className="flex flex-col items-center gap-3">
              <RefreshCw className="w-8 h-8 text-[--accent] animate-spin" />
              <p className="text-secondary">Loading inventory...</p>
            </div>
          </div>
        ) : data.results.length === 0 ? (
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-[--surface-hover] flex items-center justify-center mx-auto mb-4">
                <Package className="w-8 h-8 text-[--text-tertiary]" />
              </div>
              <h3 className="text-lg font-semibold mb-1">No inventory items</h3>
              <p className="text-secondary text-sm mb-4">
                {search ? 'Try adjusting your search criteria' : 'Get started by adding inventory items'}
              </p>
              <button className="px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium transition-colors">
                Add First Item
              </button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[--border] bg-[--surface-hover]">
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">MPN</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Quantity</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">UoM</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Location</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Supplier</th>
                  <th className="text-right px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Price Each</th>
                  <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Condition</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[--border]">
                {data.results.map((it: any) => (
                  <tr key={it.id} className="hover:bg-[--surface-hover] transition-colors">
                    <td className="px-6 py-4">
                      <span className="font-mono text-sm font-medium">{it.component?.mpn || '—'}</span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
                        {it.quantity}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-secondary">{it.uom || 'pcs'}</td>
                    <td className="px-6 py-4 text-sm">{it.storage_location || '—'}</td>
                    <td className="px-6 py-4 text-sm text-secondary">{it.supplier || '—'}</td>
                    <td className="px-6 py-4 text-right text-sm font-medium">
                      {it.price_each ? `$${Number(it.price_each).toFixed(2)}` : '—'}
                    </td>
                    <td className="px-6 py-4">
                      {it.condition && (
                        <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-medium ${
                          it.condition === 'new' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                          it.condition === 'used' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                          'bg-red-500/10 text-red-400 border border-red-500/20'
                        }`}>
                          {it.condition}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {!loading && data.results.length > 0 && (
          <div className="border-t border-[--border] px-6 py-4 flex items-center justify-between">
            <div className="text-sm text-secondary">
              Showing <span className="font-medium text-[--text]">{(page - 1) * 50 + 1}</span> to{' '}
              <span className="font-medium text-[--text]">{Math.min(page * 50, data.count)}</span> of{' '}
              <span className="font-medium text-[--text]">{data.count.toLocaleString()}</span> items
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setQuery({page: Math.max(1, page - 1)})}
                disabled={page <= 1}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[--border] bg-[--surface] hover:bg-[--surface-hover] disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
                Previous
              </button>
              <div className="flex items-center gap-1 px-3 py-1.5 text-sm">
                <span className="font-medium">Page {page}</span>
                {totalPages > 0 && <span className="text-secondary">of {totalPages}</span>}
              </div>
              <button
                onClick={() => setQuery({page: page + 1})}
                disabled={page >= totalPages}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[--border] bg-[--surface] hover:bg-[--surface-hover] disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors"
              >
                Next
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
