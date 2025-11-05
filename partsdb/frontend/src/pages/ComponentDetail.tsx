import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, Download, ExternalLink, Package, FileText, Info, Box } from 'lucide-react';
import { api } from '../api/client';

export default function ComponentDetail() {
  const { id } = useParams<{id:string}>();
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>();
  const [error, setError] = useState<string|undefined>();
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    (async()=>{
      setLoading(true);
      setError(undefined);
      try {
        setData(await api.getComponent(id!));
      }
      catch(e:any){
        setError(e?.message || 'Failed to load component');
      }
      finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handleDatasheetClick = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    if (!data?.url_datasheet) return;

    try {
      // First, try to download the datasheet
      const response = await fetch(`/api/components/${id}/fetch_datasheet/`, {
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
        window.open(data.url_datasheet, '_blank');
      }
    } catch (error) {
      // On error, fall back to opening the original URL
      console.error('Failed to download datasheet:', error);
      window.open(data.url_datasheet, '_blank');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <p className="text-secondary">Loading component...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Link to="/components" className="inline-flex items-center gap-2 text-sm text-secondary hover:text-[--text]">
          <ArrowLeft className="w-4 h-4" />
          Back to Components
        </Link>
        <div className="card p-8 border-[--error] bg-red-500/5 text-center">
          <p className="text-[--error] font-medium">Error: {error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <Link to="/components" className="inline-flex items-center gap-2 text-sm text-secondary hover:text-[--text] transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Components
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold font-mono">{data.mpn}</h1>
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-[--surface-hover] text-[--text-secondary] border border-[--border]">
                {data.category_l1 || 'Unsorted'}
              </span>
            </div>
            <p className="text-secondary text-sm mb-4">{data.manufacturer}</p>
            {data.description && (
              <p className="text-sm text-secondary max-w-2xl">{data.description}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            {data.url_datasheet && (
              <button
                onClick={handleDatasheetClick}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium transition-colors"
              >
                <Download className="w-4 h-4" />
                Datasheet
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-[--border]">
        <div className="flex gap-6">
          {[
            { id: 'overview', label: 'Overview', icon: Info },
            { id: 'inventory', label: 'Inventory', icon: Package },
            { id: 'specs', label: 'Specifications', icon: FileText },
          ].map(({ id: tabId, label, icon: Icon }) => (
            <button
              key={tabId}
              onClick={() => setActiveTab(tabId)}
              className={`
                flex items-center gap-2 px-4 py-3 border-b-2 font-medium text-sm transition-colors
                ${activeTab === tabId
                  ? 'border-[--accent] text-[--accent]'
                  : 'border-transparent text-secondary hover:text-[--text] hover:border-[--border-light]'
                }
              `}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* DMT Classification */}
          {data.dmtuid && (
            <div className="card p-6">
              <h3 className="text-sm font-semibold text-secondary uppercase tracking-wider mb-4">DMT Classification</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <InfoCard label="DMT UID" value={data.dmtuid} />
                <InfoCard label="Domain (TT)" value={data.dmt_tt} />
                <InfoCard label="Family (FF)" value={data.dmt_ff} />
                <InfoCard label="Class (CC)" value={data.dmt_cc} />
                <InfoCard label="Style (SS)" value={data.dmt_ss} />
                <InfoCard label="Sequence (XXX)" value={data.dmt_xxx} />
              </div>
            </div>
          )}

          {/* Component Details */}
          <div className="card p-6">
            <h3 className="text-sm font-semibold text-secondary uppercase tracking-wider mb-4">Component Details</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <InfoCard label="Manufacturer" value={data.manufacturer} />
              <InfoCard label="MPN" value={data.mpn} />
              <InfoCard label="Package" value={data.package_name} icon={<Box className="w-4 h-4" />} />
              <InfoCard label="Value" value={data.value} />
              <InfoCard label="Tolerance" value={data.tolerance} />
              <InfoCard label="Voltage" value={data.voltage} />
              <InfoCard label="Current" value={data.current} />
              <InfoCard label="Wattage" value={data.wattage} />
              <InfoCard label="Temperature Grade" value={data.temp_grade} />
              <InfoCard label="RoHS Compliant" value={data.rohs ? 'Yes' : 'No'} />
              <InfoCard label="Lifecycle" value={data.lifecycle} />
              <InfoCard label="Category" value={data.category_l1} />
            </div>
          </div>
        </div>
      )}

      {activeTab === 'inventory' && (
        <InventoryTab componentId={id!} component={data} />
      )}

      {activeTab === 'specs' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {data.package_l_mm && (
            <InfoCard label="Package Length" value={`${data.package_l_mm} mm`} />
          )}
          {data.package_w_mm && (
            <InfoCard label="Package Width" value={`${data.package_w_mm} mm`} />
          )}
          {data.package_h_mm && (
            <InfoCard label="Package Height" value={`${data.package_h_mm} mm`} />
          )}
          {data.pins && (
            <InfoCard label="Pin Count" value={data.pins} />
          )}
          {data.pitch_mm && (
            <InfoCard label="Pin Pitch" value={`${data.pitch_mm} mm`} />
          )}
        </div>
      )}
    </div>
  );
}

function InfoCard({ label, value, icon }: { label: string; value: any; icon?: React.ReactNode }) {
  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs font-medium text-secondary uppercase tracking-wide">{label}</span>
      </div>
      <div className="text-base font-medium">{value || '—'}</div>
    </div>
  );
}

function InventoryTab({ componentId, component }: { componentId: string; component: any }) {
  const [inventory, setInventory] = useState<any[]>([]);
  const [locations, setLocations] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingItem, setEditingItem] = useState<string | null>(null);
  const [editLocation, setEditLocation] = useState<string>('');

  useEffect(() => {
    loadInventory();
    loadLocations();
  }, [componentId]);

  const loadInventory = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/inventory/?component=${componentId}`);
      if (response.ok) {
        const data = await response.json();
        setInventory(data.results || []);
      }
    } catch (error) {
      console.error('Failed to load inventory:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadLocations = async () => {
    try {
      const response = await fetch('/api/inventory/by_location/');
      if (response.ok) {
        const data = await response.json();
        const allLocations = data.map((loc: any) => loc.location);
        setLocations(allLocations);
      }
    } catch (error) {
      console.error('Failed to load locations:', error);
    }
  };

  const handleEditLocation = (itemId: string, currentLocation: string) => {
    setEditingItem(itemId);
    setEditLocation(currentLocation);
  };

  const handleSaveLocation = async (itemId: string) => {
    try {
      const response = await fetch(`/api/inventory/${itemId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          storage_location: editLocation,
        }),
      });

      if (response.ok) {
        await loadInventory();
        setEditingItem(null);
      } else {
        alert('Failed to update location');
      }
    } catch (error) {
      console.error('Failed to update location:', error);
      alert('Failed to update location');
    }
  };

  const handleCancelEdit = () => {
    setEditingItem(null);
    setEditLocation('');
  };

  if (loading) {
    return (
      <div className="card p-6">
        <p className="text-center text-secondary">Loading inventory...</p>
      </div>
    );
  }

  if (inventory.length === 0) {
    return (
      <div className="card p-6">
        <div className="text-center py-12">
          <Package className="w-12 h-12 text-[--text-tertiary] mx-auto mb-3" />
          <h3 className="text-lg font-semibold mb-1">No inventory items</h3>
          <p className="text-secondary text-sm mb-4">This component has no stock entries yet.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full">
        <thead className="bg-[--surface-hover] border-b border-[--border]">
          <tr>
            <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Location</th>
            <th className="text-right px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Quantity</th>
            <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">UoM</th>
            <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Condition</th>
            <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Supplier</th>
            <th className="text-right px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Price</th>
            <th className="text-left px-6 py-3 text-xs font-semibold text-[--text-secondary] uppercase tracking-wider">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[--border]">
          {inventory.map((item: any) => (
            <tr key={item.id} className="hover:bg-[--surface-hover] transition-colors">
              <td className="px-6 py-4 text-sm font-medium">
                {editingItem === item.id ? (
                  <select
                    value={editLocation}
                    onChange={(e) => setEditLocation(e.target.value)}
                    className="px-3 py-1.5 bg-[--bg] border border-[--border] rounded-lg text-sm focus:border-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20"
                  >
                    {locations.map((loc) => (
                      <option key={loc} value={loc}>{loc}</option>
                    ))}
                  </select>
                ) : (
                  item.storage_location
                )}
              </td>
              <td className="px-6 py-4 text-right">
                <span className="inline-flex items-center px-2.5 py-1 rounded-md text-sm font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  {item.quantity}
                </span>
              </td>
              <td className="px-6 py-4 text-sm text-secondary">{item.uom || 'pcs'}</td>
              <td className="px-6 py-4">
                {item.condition && (
                  <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-medium ${
                    item.condition === 'new' ? 'bg-green-500/10 text-green-400 border border-green-500/20' :
                    item.condition === 'used' ? 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20' :
                    'bg-red-500/10 text-red-400 border border-red-500/20'
                  }`}>
                    {item.condition}
                  </span>
                )}
              </td>
              <td className="px-6 py-4 text-sm text-secondary">{item.supplier || '—'}</td>
              <td className="px-6 py-4 text-right text-sm font-medium">
                {item.price_each ? `$${Number(item.price_each).toFixed(2)}` : '—'}
              </td>
              <td className="px-6 py-4">
                {editingItem === item.id ? (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleSaveLocation(item.id)}
                      className="px-3 py-1 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-xs font-medium transition-colors"
                    >
                      Save
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className="px-3 py-1 rounded-lg bg-[--surface] hover:bg-[--surface-hover] border border-[--border] text-xs font-medium transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleEditLocation(item.id, item.storage_location)}
                    className="px-3 py-1 rounded-lg bg-[--surface] hover:bg-[--surface-hover] border border-[--border] text-xs font-medium transition-colors"
                  >
                    Edit Location
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
