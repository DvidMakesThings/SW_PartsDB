import { useEffect, useMemo, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, RefreshCw, ChevronLeft, ChevronRight, ChevronDown, ChevronRight as ChevronRightIcon, Download, X } from 'lucide-react';
import { api } from '../api/client';
import ComponentEditModal from '../components/ComponentEditModal';

export default function Components() {
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get('page') || 1);
  const search = sp.get('search') || '';
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<{count:number; results:any[]}>({count:0, results:[]});
  const [error, setError] = useState<string|undefined>();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [editingComponent, setEditingComponent] = useState<string | null>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  const toggleRow = (id: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(id)) {
      newExpanded.delete(id);
    } else {
      newExpanded.add(id);
    }
    setExpandedRows(newExpanded);
  };

const DISPLAY_KEYS: Record<string, string> = {
  tt: 'Domain',
  ff: 'Family',
  cc: 'Class',
  ss: 'Subclass',
  xxx: 'Sequence',
  rohs: 'RoHS',
  dmtuid: 'DMTUID',
};

const formatKey = (k: string) =>
  DISPLAY_KEYS[k.toLowerCase()] ??
  k.replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

const DMT_KEYS = new Set(['tt', 'ff', 'cc', 'ss', 'xxx', 'dmtuid']);

// optional zero-pad for TT/FF/CC/SS/XXX if they are numeric strings
const zp = (v?: string | number | null, len = 2) =>
  (v ?? '') === '' ? '' : String(v).padStart(len, '0');


  const handleDatasheetClick = async (e: React.MouseEvent, componentId: string, datasheetUrl: string) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      // First, try to download the datasheet
      const response = await fetch(`/api/components/${componentId}/fetch_datasheet/`, {
        method: 'POST',
      });

      if (response.ok) {
        const result = await response.json();
        // If download successful, open the local file
        if (result.saved && result.path) {
          // Construct the media URL
          const mediaUrl = `/media/${result.path.split('/media/')[1] || result.path}`;
          window.open(mediaUrl, '_blank');
        }
      } else {
        // If download fails, fall back to opening the original URL
        window.open(datasheetUrl, '_blank');
      }
    } catch (error) {
      // On error, fall back to opening the original URL
      console.error('Failed to download datasheet:', error);
      window.open(datasheetUrl, '_blank');
    }
  };

  const params = useMemo(() => ({
    page: page > 0 ? String(page) : '1',
    search
  }), [page, search]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(undefined);
      try {
        const result = await api.listComponents(params);
        setData(result);

        // If search is active and exactly one result found, auto-open it
        if (search && result.count === 1 && result.results.length === 1) {
          setEditingComponent(result.results[0].id);
        }
      }
      catch (e:any) {
        setError(e?.message || 'Failed to load components');
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
      next.set('page', '1');
    }
    setSp(next, { replace: true });
  };

  const totalPages = Math.ceil(data.count / 50);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Components</h1>
          <p className="text-secondary">
            Manage your electronic component library
            {data.count > 0 && <span className="ml-2">· {data.count.toLocaleString()} total</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => window.open('/api/components/export_csv/', '_blank')}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-green-600 hover:bg-green-700 text-white text-sm font-medium transition-colors"
          >
            <Download className="w-4 h-4" />
            Export CSV
          </button>
          <button
            onClick={() => window.location.reload()}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--surface] hover:bg-[--surface-hover] border border-[--border] text-sm font-medium transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      {/* Search and Filters */}
      <div className="card p-4">
        <div className="flex gap-3 items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[--text-tertiary]" />
            <input
              ref={searchInputRef}
              type="text"
              placeholder="Search by MPN, manufacturer, description, DMT UID..."
              value={search}
              onChange={(e) => setQuery({search: e.target.value})}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  e.currentTarget.blur();
                  setQuery({search: e.currentTarget.value});
                }
              }}
              autoFocus
              className="w-full pl-10 pr-10 py-2.5 bg-[--bg] border border-[--border] rounded-lg text-sm focus:border-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20 transition-all"
            />
            {search && (
              <button
                onClick={() => {
                  setQuery({search: ''});
                  searchInputRef.current?.focus();
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-[--text-tertiary] hover:text-[--text]"
                title="Clear search"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          {search && (
            <div className="text-sm text-[--text-secondary] whitespace-nowrap">
              {data.count === 1 ? '1 result' : `${data.count} results`}
            </div>
          )}
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
              <p className="text-secondary">Loading components...</p>
            </div>
          </div>
        ) : data.results.length === 0 ? (
          <div className="flex items-center justify-center h-96">
            <div className="text-center">
              <div className="w-16 h-16 rounded-full bg-[--surface-hover] flex items-center justify-center mx-auto mb-4">
                <Search className="w-8 h-8 text-[--text-tertiary]" />
              </div>
              <h3 className="text-lg font-semibold mb-1">No components found</h3>
              <p className="text-secondary text-sm mb-2">
                {search ? `No results for "${search}"` : 'Get started by importing components'}
              </p>
              {search && (
                <button
                  onClick={() => {
                    setQuery({search: ''});
                    searchInputRef.current?.focus();
                  }}
                  className="text-sm text-[--accent] hover:text-[--accent-hover] underline"
                >
                  Clear search and try again
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[--border] bg-[--surface-hover]">
                  <th className="w-10"></th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">MPN</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Manufacturer</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Value</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Package</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Location</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Qty</th>
                  <th className="text-left px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider whitespace-nowrap">Operating Temp</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">RoHS</th>
                  <th className="text-center px-3 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Datasheet</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[--border]">
                {data.results.map((c: any) => {
                  const isExpanded = expandedRows.has(c.id);
                  const extras = c.extras || {};
                  const tempRange = extras['operating temperature'] || c.temp_grade || '—';
                  const location = extras['location'] || '—';
                  const quantity = extras['quantity'] || (c.inventory_items && c.inventory_items.length > 0 ? c.inventory_items.reduce((sum: number, item: any) => sum + item.quantity, 0) : '—');
                  const rohs = extras['rohs'] === 'YES' || c.rohs === true ? 'YES' : (extras['rohs'] === 'NO' || c.rohs === false ? 'NO' : '—');
                  const packageName = c.package_name || extras['package / case'] || extras['package'] || '—';

                  return (
                    <>
                      <tr key={c.id} className="hover:bg-[--surface-hover] transition-colors cursor-pointer" onClick={(e) => {
                        if (!(e.target as HTMLElement).closest('button, a')) {
                          setEditingComponent(c.id);
                        }
                      }}>
                        <td className="px-3 py-3">
                          <button
                            onClick={() => toggleRow(c.id)}
                            className="text-[--text-secondary] hover:text-[--text] transition-colors"
                          >
                            {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRightIcon className="w-4 h-4" />}
                          </button>
                        </td>
                        <td className="px-3 py-3">
                          <span className="font-mono text-sm font-medium text-[--text] whitespace-nowrap">
                            {c.mpn}
                          </span>
                        </td>
                        <td className="px-3 py-3 text-sm">{c.manufacturer}</td>
                        <td className="px-3 py-3 text-sm text-secondary whitespace-nowrap">{c.value || '—'}</td>
                        <td className="px-3 py-3 text-sm text-secondary whitespace-nowrap">{packageName}</td>
                        <td className="px-3 py-3 text-sm text-secondary">{location}</td>
                        <td className="px-3 py-3 text-center text-sm font-medium">{quantity}</td>
                        <td className="px-3 py-3 text-xs text-secondary whitespace-nowrap">{tempRange}</td>
                        <td className="px-3 py-3 text-center">
                          {rohs === 'YES' ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-500/10 text-green-400 border border-green-500/20">
                              YES
                            </span>
                          ) : rohs === 'NO' ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-500/10 text-red-400 border border-red-500/20">
                              NO
                            </span>
                          ) : (
                            <span className="text-xs text-tertiary">—</span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-center">
                          {c.url_datasheet ? (
                            <button
                              onClick={(e) => handleDatasheetClick(e, c.id, c.url_datasheet)}
                              className="inline-flex items-center gap-1 text-sm text-[--accent] hover:text-[--accent-hover]"
                              title="Download Datasheet"
                            >
                              <Download className="w-4 h-4" />
                            </button>
                          ) : (
                            <span className="text-xs text-tertiary">—</span>
                          )}
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${c.id}-details`} className="bg-[--surface-hover]/50">
                          <td colSpan={10} className="px-3 py-4">
                            <div className="space-y-4 px-8">
                              {/* Description */}
                              {c.description && (
                                <div>
                                  <h4 className="text-xs font-semibold text-[--text-secondary] uppercase tracking-wider mb-2">Description</h4>
                                  <p className="text-sm text-[--text]">{c.description}</p>
                                </div>
                              )}

                              {/* DMT Classification */}
                              {c.dmtuid && (
                                <div>
                                  <h4 className="text-xs font-semibold text-[--text-secondary] uppercase tracking-wider mb-2">DMT Classification</h4>
                                  <div className="grid grid-cols-6 gap-4">
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">UID</span>
                                      <p className="font-mono text-sm text-[--text] mt-1 whitespace-nowrap">{c.dmtuid}</p>
                                    </div>
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">Domain (TT)</span>
                                      <p className="font-mono text-sm text-[--text] mt-1">{c.dmt_tt || '—'}</p>
                                    </div>
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">Family (FF)</span>
                                      <p className="font-mono text-sm text-[--text] mt-1">{c.dmt_ff || '—'}</p>
                                    </div>
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">Class (CC)</span>
                                      <p className="font-mono text-sm text-[--text] mt-1">{c.dmt_cc || '—'}</p>
                                    </div>
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">Style (SS)</span>
                                      <p className="font-mono text-sm text-[--text] mt-1">{c.dmt_ss || '—'}</p>
                                    </div>
                                    <div>
                                      <span className="text-xs text-[--text-tertiary]">Sequence (XXX)</span>
                                      <p className="font-mono text-sm text-[--text] mt-1">{c.dmt_xxx || '—'}</p>
                                    </div>
                                  </div>
                                </div>
                              )}

                              {/* ---------- ADDITIONAL PROPERTIES ---------- */}
                              {(() => {
                                const extras = c.extras || {};
                                // drop DMT keys so they don't show twice
                                const filtered = Object.entries(extras).filter(
                                  ([k, v]) => !DMT_KEYS.has(k.toLowerCase()) && v != null && String(v).trim() !== ''
                                );
                                if (!filtered.length) return null;

                                return (
                                  <div className="grid grid-cols-12 gap-x-8 gap-y-4 mt-6">
                                    <div className="col-span-12 text-sm font-semibold text-[--text-secondary]">
                                      ADDITIONAL PROPERTIES
                                    </div>

                                    <div className="col-span-12 grid grid-cols-12 gap-x-8 gap-y-6">
                                      {filtered.map(([key, value]) => (
                                        <div key={key} className="col-span-12 sm:col-span-4">
                                          <span className="text-xs text-[--text-tertiary] block mb-1">
                                            {formatKey(key)}
                                          </span>
                                          <span className="text-sm break-words">{String(value)}</span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                );
                              })()}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })}
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
              <span className="font-medium text-[--text]">{data.count.toLocaleString()}</span> results
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

      {/* Edit Modal */}
      {editingComponent && (
        <ComponentEditModal
          componentId={editingComponent}
          onClose={() => setEditingComponent(null)}
          onSave={() => {
            setEditingComponent(null);
            window.location.reload();
          }}
        />
      )}
    </div>
  );
}
