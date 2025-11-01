import { useState } from 'react';
import { Upload, FileText, CheckCircle, AlertCircle, Info, Download } from 'lucide-react';
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
    setBusy(true);
    setError(undefined);
    setResult(null);
    try {
      const res = await api.importCsv(file, dry, encoding);
      setResult(res);
    } catch (e:any) {
      setError(e?.message || 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    setResult(null);
    setError(undefined);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold mb-1">Import CSV</h1>
        <p className="text-secondary">
          Import component data from CSV files
        </p>
      </div>

      {/* Info Card */}
      <div className="card p-4 border-blue-500/20 bg-blue-500/5">
        <div className="flex gap-3">
          <Info className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
          <div className="text-sm text-secondary space-y-1">
            <p className="font-medium text-[--text]">CSV Import Guidelines</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Supported columns: MPN, Manufacturer, Value, Tolerance, Package, Description, Datasheet, and more</li>
              <li>Components are automatically deduplicated by manufacturer + MPN</li>
              <li>Use dry-run mode to preview changes before committing</li>
              <li>Check encoding if you see special characters displayed incorrectly</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Upload Card */}
      <div className="card p-6">
        <h2 className="text-lg font-semibold mb-4">Upload File</h2>

        <div className="space-y-6">
          {/* File Input */}
          <div>
            <label className="block text-sm font-medium mb-2">CSV File</label>
            <div className="relative">
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={handleFileChange}
                className="hidden"
                id="csv-upload"
              />
              <label
                htmlFor="csv-upload"
                className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-[--border] rounded-lg cursor-pointer hover:border-[--accent] hover:bg-[--surface-hover] transition-all"
              >
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <FileText className="w-8 h-8 text-[--accent]" />
                    <span className="text-sm font-medium">{file.name}</span>
                    <span className="text-xs text-secondary">{(file.size / 1024).toFixed(2)} KB</span>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload className="w-8 h-8 text-[--text-tertiary]" />
                    <span className="text-sm font-medium">Click to upload CSV</span>
                    <span className="text-xs text-secondary">or drag and drop</span>
                  </div>
                )}
              </label>
            </div>
          </div>

          {/* Encoding Selection */}
          <div>
            <label className="block text-sm font-medium mb-2">File Encoding</label>
            <select
              value={encoding}
              onChange={(e) => setEncoding(e.target.value)}
              className="w-full px-4 py-2.5 bg-[--bg] border border-[--border] rounded-lg text-sm focus:border-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20 transition-all"
            >
              <option value="latin1">Latin-1 (ISO-8859-1)</option>
              <option value="utf-8">UTF-8</option>
              <option value="cp1252">Windows-1252</option>
              <option value="ascii">ASCII</option>
            </select>
            <p className="text-xs text-secondary mt-2">
              If you see character encoding errors, try a different encoding
            </p>
          </div>

          {/* Dry Run Checkbox */}
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={dry}
              onChange={(e) => setDry(e.target.checked)}
              className="w-4 h-4 rounded border-[--border] bg-[--bg] text-[--accent] focus:ring-2 focus:ring-[--accent] focus:ring-opacity-20"
            />
            <div>
              <span className="text-sm font-medium">Dry run mode</span>
              <p className="text-xs text-secondary">Preview changes without committing to database</p>
            </div>
          </label>

          {/* Submit Button */}
          <button
            onClick={onSubmit}
            disabled={!file || busy}
            className="w-full flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-[--accent] hover:bg-[--accent-hover] disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium transition-all"
          >
            {busy ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Uploading...
              </>
            ) : (
              <>
                <Upload className="w-5 h-5" />
                Upload & {dry ? 'Preview' : 'Import'}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="card p-4 border-[--error] bg-red-500/5">
          <div className="flex gap-3">
            <AlertCircle className="w-5 h-5 text-[--error] flex-shrink-0" />
            <div>
              <p className="font-medium text-[--error]">Import Failed</p>
              <p className="text-sm text-[--error] mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* Results Display */}
      {result && (
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle className="w-6 h-6 text-green-400" />
            <h2 className="text-lg font-semibold">
              {dry ? 'Preview Results' : 'Import Complete'}
            </h2>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <StatCard
              label="Created"
              value={result.created || 0}
              color="green"
            />
            <StatCard
              label="Updated"
              value={result.updated || 0}
              color="blue"
            />
            <StatCard
              label="Skipped"
              value={result.skipped || 0}
              color="yellow"
            />
            <StatCard
              label="Errors"
              value={result.errors?.length || 0}
              color="red"
            />
          </div>

          {dry && (
            <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
              <p className="text-sm text-blue-400 font-medium">
                This was a dry run. No changes were made to the database.
                Uncheck "Dry run mode" to commit these changes.
              </p>
            </div>
          )}

          {result.errors && result.errors.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-semibold mb-2 text-[--error]">
                Errors ({result.errors.length})
              </h3>
              <div className="bg-red-500/5 border border-red-500/20 rounded-lg p-4 max-h-40 overflow-y-auto">
                <ul className="space-y-1 text-sm text-[--error]">
                  {result.errors.slice(0, 10).map((err: any, idx: number) => (
                    <li key={idx}>{err}</li>
                  ))}
                  {result.errors.length > 10 && (
                    <li className="font-medium">... and {result.errors.length - 10} more</li>
                  )}
                </ul>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const colors = {
    green: 'bg-green-500/10 text-green-400 border-green-500/20',
    blue: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
    yellow: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
    red: 'bg-red-500/10 text-red-400 border-red-500/20',
  };

  return (
    <div className={`border rounded-lg p-4 ${colors[color as keyof typeof colors]}`}>
      <div className="text-2xl font-bold">{value.toLocaleString()}</div>
      <div className="text-sm opacity-80">{label}</div>
    </div>
  );
}
