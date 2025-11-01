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
              <a
                href={data.url_datasheet}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium transition-colors"
              >
                <Download className="w-4 h-4" />
                Datasheet
                <ExternalLink className="w-3 h-3" />
              </a>
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
        <div className="card p-6">
          <div className="text-center py-12">
            <Package className="w-12 h-12 text-[--text-tertiary] mx-auto mb-3" />
            <h3 className="text-lg font-semibold mb-1">No inventory items</h3>
            <p className="text-secondary text-sm mb-4">This component has no stock entries yet.</p>
            <button className="px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium transition-colors">
              Add Inventory Item
            </button>
          </div>
        </div>
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
