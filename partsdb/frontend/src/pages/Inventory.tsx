import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Search, RefreshCw, Package, ChevronDown, ChevronRight } from 'lucide-react';

interface LocationInventory {
  location: string;
  total_items: number;
  total_components: number;
  components: {
    id: string;
    mpn: string;
    manufacturer: string;
    description: string;
    quantity: number;
    uom: string;
  }[];
}

export default function Inventory() {
  const [loading, setLoading] = useState(true);
  const [locations, setLocations] = useState<LocationInventory[]>([]);
  const [error, setError] = useState<string|undefined>();
  const [expandedLocation, setExpandedLocation] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadLocations();
  }, []);

  const loadLocations = async () => {
    setLoading(true);
    setError(undefined);
    try {
      const response = await fetch('/api/inventory/by_location/');
      if (!response.ok) throw new Error('Failed to load inventory');
      const data = await response.json();
      setLocations(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load inventory');
    } finally {
      setLoading(false);
    }
  };

  const filteredLocations = locations.filter(loc =>
    loc.location.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold mb-1">Inventory by Location</h1>
          <p className="text-secondary">
            View components organized by storage location
            {locations.length > 0 && <span className="ml-2">· {locations.length} location{locations.length !== 1 ? 's' : ''}</span>}
          </p>
        </div>
        <button
          onClick={loadLocations}
          className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--surface] hover:bg-[--surface-hover] border border-[--border] text-sm font-medium transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Search */}
      <div className="card p-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[--text-tertiary]" />
          <input
            type="text"
            placeholder="Search locations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2.5 bg-[--bg] border border-[--border] rounded-lg text-sm focus:border-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20 transition-all"
          />
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="card p-4 border-[--error] bg-red-500/5">
          <p className="text-[--error] text-sm font-medium">Error: {error}</p>
        </div>
      )}

      {/* Loading State */}
      {loading ? (
        <div className="flex items-center justify-center h-96">
          <div className="flex flex-col items-center gap-3">
            <RefreshCw className="w-8 h-8 text-[--accent] animate-spin" />
            <p className="text-secondary">Loading inventory...</p>
          </div>
        </div>
      ) : filteredLocations.length === 0 ? (
        <div className="flex items-center justify-center h-96">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full bg-[--surface-hover] flex items-center justify-center mx-auto mb-4">
              <Package className="w-8 h-8 text-[--text-tertiary]" />
            </div>
            <h3 className="text-lg font-semibold mb-1">No inventory items</h3>
            <p className="text-secondary text-sm">
              {searchQuery ? 'No locations match your search' : 'Get started by importing inventory items'}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredLocations.map((location) => (
            <div
              key={location.location}
              className="card overflow-hidden"
            >
              <button
                onClick={() => setExpandedLocation(expandedLocation === location.location ? null : location.location)}
                className="w-full px-6 py-4 flex items-center justify-between hover:bg-[--surface-hover] transition-colors"
              >
                <div className="flex items-center gap-4">
                  <div className="text-2xl">📦</div>
                  <div className="text-left">
                    <h2 className="text-lg font-semibold">{location.location}</h2>
                    <p className="text-sm text-secondary">
                      {location.total_components} component{location.total_components !== 1 ? 's' : ''} · {location.total_items} total items
                    </p>
                  </div>
                </div>
                {expandedLocation === location.location ? (
                  <ChevronDown className="w-5 h-5 text-[--text-secondary]" />
                ) : (
                  <ChevronRight className="w-5 h-5 text-[--text-secondary]" />
                )}
              </button>

              {expandedLocation === location.location && (
                <div className="border-t border-[--border]">
                  <table className="w-full">
                    <thead className="bg-[--surface-hover]">
                      <tr>
                        <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">MPN</th>
                        <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Manufacturer</th>
                        <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Description</th>
                        <th className="text-right px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Quantity</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[--border]">
                      {location.components.map((component, idx) => (
                        <tr key={idx} className="hover:bg-[--surface-hover] transition-colors">
                          <td className="px-6 py-4">
                            <Link
                              to={`/components/${component.id}`}
                              className="font-mono text-sm font-medium text-[--accent] hover:text-[--accent-hover]"
                            >
                              {component.mpn}
                            </Link>
                          </td>
                          <td className="px-6 py-4 text-sm">{component.manufacturer}</td>
                          <td className="px-6 py-4 text-sm text-secondary max-w-md truncate">
                            {component.description || '—'}
                          </td>
                          <td className="px-6 py-4 text-right">
                            <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
                              {component.quantity} {component.uom}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
