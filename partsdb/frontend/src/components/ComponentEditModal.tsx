import { useState, useEffect, useRef } from 'react';
import { X, Plus, Trash2, Save } from 'lucide-react';
import { api } from '../api/client';

interface ComponentEditModalProps {
  componentId: string;
  onClose: () => void;
  onSave: () => void;
}

const FILE_TYPES = [
  { value: 'three_d', label: '3D Model (STEP)' },
  { value: 'eagle_lib', label: 'Eagle Library' },
  { value: 'photo', label: 'Photo' },
  { value: 'appnote', label: 'Application Note' },
  { value: 'schematic', label: 'Schematic' },
  { value: 'layout', label: 'Layout/PCB' },
  { value: 'other', label: 'Other' },
];

export default function ComponentEditModal({ componentId, onClose, onSave }: ComponentEditModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [component, setComponent] = useState<any>(null);
  const [formData, setFormData] = useState<any>({});
  const [uploadingFile, setUploadingFile] = useState(false);
  const [selectedFileType, setSelectedFileType] = useState('three_d');
  const [customFileType, setCustomFileType] = useState('');

  const [showAddProperty, setShowAddProperty] = useState(false);
  const [newPropertyName, setNewPropertyName] = useState('');
  const [newPropertyValue, setNewPropertyValue] = useState('');
  const [allPropertyNames, setAllPropertyNames] = useState<string[]>([]);
  const [filteredSuggestions, setFilteredSuggestions] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadComponent();
    loadAllPropertyNames();
  }, [componentId]);

  const loadComponent = async () => {
    setLoading(true);
    try {
      const data = await api.getComponent(componentId);
      setComponent(data);
      setFormData({
        mpn: data.mpn || '',
        manufacturer: data.manufacturer || '',
        value: data.value || '',
        tolerance: data.tolerance || '',
        package_name: data.package_name || '',
        description: data.description || '',
        url_datasheet: data.url_datasheet || '',
        category_l1: data.category_l1 || '',
        rohs: data.rohs || false,
        temp_grade: data.temp_grade || '',
        extras: data.extras || {},
      });
    } catch (error) {
      console.error('Failed to load component:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadAllPropertyNames = async () => {
    try {
      const response = await fetch('/api/components/?page=1');
      const data = await response.json();
      const allKeys = new Set<string>();

      data.results.forEach((comp: any) => {
        if (comp.extras) {
          Object.keys(comp.extras).forEach(key => allKeys.add(key));
        }
      });

      setAllPropertyNames(Array.from(allKeys).sort());
    } catch (error) {
      console.error('Failed to load property names:', error);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch(`/api/components/${componentId}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      onSave();
      onClose();
    } catch (error) {
      console.error('Failed to save component:', error);
      alert('Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingFile(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('component', componentId);
    formData.append('type', selectedFileType);
    if (selectedFileType === 'other' && customFileType) {
      formData.append('custom_type', customFileType);
    }

    try {
      await fetch('/api/attachments/', {
        method: 'POST',
        body: formData,
      });
      loadComponent();
      setCustomFileType('');
      e.target.value = '';
    } catch (error) {
      console.error('Failed to upload file:', error);
      alert('Failed to upload file');
    } finally {
      setUploadingFile(false);
    }
  };

  const handleDeleteAttachment = async (attachmentId: string) => {
    if (!confirm('Delete this attachment?')) return;

    try {
      await fetch(`/api/attachments/${attachmentId}/`, {
        method: 'DELETE',
      });
      loadComponent();
    } catch (error) {
      console.error('Failed to delete attachment:', error);
      alert('Failed to delete attachment');
    }
  };

  const handlePropertyNameChange = (value: string) => {
    setNewPropertyName(value);

    if (value.length > 0) {
      const filtered = allPropertyNames.filter(name =>
        name.toLowerCase().includes(value.toLowerCase())
      ).slice(0, 10);
      setFilteredSuggestions(filtered);
    } else {
      setFilteredSuggestions([]);
    }
  };

  const addProperty = () => {
    if (!newPropertyName.trim()) return;

    setFormData({
      ...formData,
      extras: {
        ...formData.extras,
        [newPropertyName.toLowerCase()]: newPropertyValue,
      },
    });

    setNewPropertyName('');
    setNewPropertyValue('');
    setShowAddProperty(false);
    setFilteredSuggestions([]);
  };

  const updateExtras = (key: string, value: string) => {
    setFormData({
      ...formData,
      extras: {
        ...formData.extras,
        [key]: value,
      },
    });
  };

  const deleteExtrasKey = (key: string) => {
    const newExtras = { ...formData.extras };
    delete newExtras[key];
    setFormData({ ...formData, extras: newExtras });
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div className="bg-[--surface] rounded-lg p-6">
          <p className="text-[--text]">Loading...</p>
        </div>
      </div>
    );
  }

  const filledExtras = Object.entries(formData.extras || {}).filter(([_, value]) =>
    value && value !== '' && value !== '[]' && value !== "['']"
  );

  const hasDatasheetFile = component?.attachments?.some((att: any) => att.type === 'datasheet');

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-[--surface] rounded-lg max-w-3xl w-full max-h-[90vh] overflow-y-auto">
        <div className="sticky top-0 bg-[--surface] border-b border-[--border] p-6 flex items-center justify-between z-10">
          <h2 className="text-2xl font-bold">Edit Component</h2>
          <button onClick={onClose} className="text-[--text-secondary] hover:text-[--text]">
            <X className="w-6 h-6" />
          </button>
        </div>

        <div className="p-6 space-y-6">
          {/* Basic Properties - Only show filled ones */}
          <div>
            <h3 className="text-lg font-semibold mb-4">Basic Properties</h3>
            <div className="space-y-3">
              {formData.mpn && (
                <div className="grid grid-cols-3 gap-4 items-center">
                  <label className="text-sm font-medium">MPN</label>
                  <input
                    type="text"
                    value={formData.mpn}
                    onChange={(e) => setFormData({ ...formData, mpn: e.target.value })}
                    className="col-span-2 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                  />
                </div>
              )}
              {formData.manufacturer && (
                <div className="grid grid-cols-3 gap-4 items-center">
                  <label className="text-sm font-medium">Manufacturer</label>
                  <input
                    type="text"
                    value={formData.manufacturer}
                    onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                    className="col-span-2 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                  />
                </div>
              )}
              {formData.value && (
                <div className="grid grid-cols-3 gap-4 items-center">
                  <label className="text-sm font-medium">Value</label>
                  <input
                    type="text"
                    value={formData.value}
                    onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                    className="col-span-2 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                  />
                </div>
              )}
              {formData.package_name && (
                <div className="grid grid-cols-3 gap-4 items-center">
                  <label className="text-sm font-medium">Package</label>
                  <input
                    type="text"
                    value={formData.package_name}
                    onChange={(e) => setFormData({ ...formData, package_name: e.target.value })}
                    className="col-span-2 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                  />
                </div>
              )}
              {formData.description && (
                <div className="grid grid-cols-3 gap-4 items-start">
                  <label className="text-sm font-medium pt-2">Description</label>
                  <textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    className="col-span-2 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                    rows={3}
                  />
                </div>
              )}
            </div>
          </div>

          {/* Custom Properties - Only show filled ones */}
          {filledExtras.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-4">Properties</h3>
              <div className="space-y-3">
                {filledExtras.map(([key, value]) => (
                  <div key={key} className="grid grid-cols-3 gap-4 items-center">
                    <label className="text-sm font-medium capitalize">{key}</label>
                    <div className="col-span-2 flex items-center gap-2">
                      <input
                        type="text"
                        value={String(value)}
                        onChange={(e) => updateExtras(key, e.target.value)}
                        className="flex-1 px-3 py-2 bg-[--bg] border border-[--border] rounded-lg text-sm"
                      />
                      <button
                        onClick={() => deleteExtrasKey(key)}
                        className="text-red-500 hover:text-red-600"
                        title="Delete property"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Add New Property */}
          <div>
            {!showAddProperty ? (
              <button
                onClick={() => {
                  setShowAddProperty(true);
                  setTimeout(() => inputRef.current?.focus(), 100);
                }}
                className="flex items-center gap-2 text-sm text-[--accent] hover:text-[--accent-hover]"
              >
                <Plus className="w-4 h-4" />
                Add Property
              </button>
            ) : (
              <div className="p-4 bg-[--bg] rounded-lg border border-[--border]">
                <h4 className="text-sm font-semibold mb-3">Add New Property</h4>
                <div className="space-y-3">
                  <div className="relative">
                    <label className="block text-xs text-[--text-secondary] mb-1">Property Name</label>
                    <input
                      ref={inputRef}
                      type="text"
                      value={newPropertyName}
                      onChange={(e) => handlePropertyNameChange(e.target.value)}
                      placeholder="Start typing or select from suggestions"
                      className="w-full px-3 py-2 bg-[--surface] border border-[--border] rounded-lg text-sm"
                    />
                    {filteredSuggestions.length > 0 && (
                      <div className="absolute z-10 w-full mt-1 bg-[--surface] border border-[--border] rounded-lg shadow-lg max-h-48 overflow-y-auto">
                        {filteredSuggestions.map((suggestion) => (
                          <button
                            key={suggestion}
                            onClick={() => {
                              setNewPropertyName(suggestion);
                              setFilteredSuggestions([]);
                            }}
                            className="w-full text-left px-3 py-2 hover:bg-[--surface-hover] text-sm capitalize"
                          >
                            {suggestion}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                  <div>
                    <label className="block text-xs text-[--text-secondary] mb-1">Value</label>
                    <input
                      type="text"
                      value={newPropertyValue}
                      onChange={(e) => setNewPropertyValue(e.target.value)}
                      placeholder="Enter value"
                      onKeyPress={(e) => e.key === 'Enter' && addProperty()}
                      className="w-full px-3 py-2 bg-[--surface] border border-[--border] rounded-lg text-sm"
                    />
                  </div>
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setShowAddProperty(false);
                        setNewPropertyName('');
                        setNewPropertyValue('');
                        setFilteredSuggestions([]);
                      }}
                      className="px-3 py-1.5 text-sm rounded-lg border border-[--border] hover:bg-[--surface-hover]"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={addProperty}
                      disabled={!newPropertyName.trim()}
                      className="px-3 py-1.5 text-sm rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* File Attachments */}
          <div>
            <h3 className="text-lg font-semibold mb-4">File Attachments</h3>

            {/* Show datasheet if downloaded */}
            {hasDatasheetFile && (
              <div className="mb-4">
                {component.attachments
                  .filter((att: any) => att.type === 'datasheet')
                  .map((att: any) => (
                    <div key={att.id} className="flex items-center justify-between p-3 bg-green-500/10 rounded-lg border border-green-500/20">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-green-400">Datasheet</span>
                        <span className="text-xs text-[--text-secondary]">
                          {att.file?.split('/').pop()}
                        </span>
                      </div>
                      <button
                        onClick={() => handleDeleteAttachment(att.id)}
                        className="text-red-500 hover:text-red-600"
                        title="Delete attachment"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
              </div>
            )}

            {/* Other attachments */}
            {component?.attachments && component.attachments.filter((att: any) => att.type !== 'datasheet').length > 0 && (
              <div className="space-y-2 mb-4">
                {component.attachments
                  .filter((att: any) => att.type !== 'datasheet')
                  .map((att: any) => (
                    <div key={att.id} className="flex items-center justify-between p-3 bg-[--bg] rounded-lg border border-[--border]">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium capitalize">
                          {att.custom_type || att.type.replace('_', ' ')}
                        </span>
                        <span className="text-xs text-[--text-secondary]">
                          {att.file?.split('/').pop()}
                        </span>
                      </div>
                      <button
                        onClick={() => handleDeleteAttachment(att.id)}
                        className="text-red-500 hover:text-red-600"
                        title="Delete attachment"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
              </div>
            )}

            {/* Upload New File */}
            <div className="p-4 bg-[--bg] rounded-lg border border-[--border]">
              <h4 className="text-sm font-semibold mb-3">Upload New File</h4>
              <div className="space-y-3">
                <div>
                  <label className="block text-xs text-[--text-secondary] mb-1">File Type</label>
                  <select
                    value={selectedFileType}
                    onChange={(e) => setSelectedFileType(e.target.value)}
                    className="w-full px-3 py-2 bg-[--surface] border border-[--border] rounded-lg text-sm"
                  >
                    {FILE_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                </div>
                {selectedFileType === 'other' && (
                  <div>
                    <label className="block text-xs text-[--text-secondary] mb-1">Custom Type Name</label>
                    <input
                      type="text"
                      value={customFileType}
                      onChange={(e) => setCustomFileType(e.target.value)}
                      placeholder="e.g., Simulation File, Test Report"
                      className="w-full px-3 py-2 bg-[--surface] border border-[--border] rounded-lg text-sm"
                    />
                  </div>
                )}
                <div>
                  <label className="block text-xs text-[--text-secondary] mb-1">Choose File</label>
                  <input
                    type="file"
                    onChange={handleFileUpload}
                    disabled={uploadingFile}
                    className="w-full px-3 py-2 bg-[--surface] border border-[--border] rounded-lg text-sm file:mr-4 file:py-1 file:px-3 file:rounded file:border-0 file:text-sm file:bg-[--accent] file:text-white hover:file:bg-[--accent-hover]"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-[--surface] border-t border-[--border] p-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-[--surface-hover] hover:bg-[--border] border border-[--border] text-sm font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-[--accent] hover:bg-[--accent-hover] text-white text-sm font-medium disabled:opacity-50"
          >
            <Save className="w-4 h-4" />
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>
    </div>
  );
}
