// Types for API responses matching Django model and serializer structures

// Common fields
export interface BaseModel {
  id: string;
  created_at: string;
  updated_at: string;
}

// Component model
export interface Component extends BaseModel {
  mpn: string;
  manufacturer: string;
  value: string | null;
  tolerance: string | null;
  wattage: string | null;
  voltage: string | null;
  current: string | null;
  package_name: string | null;
  package_l_mm: number | null;
  package_w_mm: number | null;
  package_h_mm: number | null;
  pins: number | null;
  pitch_mm: number | null;
  description: string | null;
  lifecycle: 'ACTIVE' | 'NRND' | 'EOL' | 'UNKNOWN';
  rohs: boolean | null;
  temp_grade: string | null;
  url_datasheet: string | null;
  url_alt: string | null;
  category_l1: string;
  category_l2: string | null;
  footprint_name: string | null;
  step_model_path: string | null;
  // Relations
  inventory_items: InventoryItem[];
  attachments: Attachment[];
}

// Inventory item model
export interface InventoryItem extends BaseModel {
  component_id: string;
  quantity: number;
  uom: 'pcs' | 'reel' | 'tube' | 'tray';
  storage_location: string;
  lot_code: string | null;
  date_code: string | null;
  supplier: string | null;
  price_each: number | null;
  condition: 'new' | 'used' | 'expired';
  note: string | null;
}

// Attachment model
export interface Attachment extends BaseModel {
  component_id: string;
  type: 'datasheet' | 'three_d' | 'photo' | 'appnote' | 'other';
  file: string; // URL to the file
  source_url: string | null;
  sha256: string | null;
}

// Eagle link model
export interface EagleLink extends BaseModel {
  component_id: string;
  eagle_library: string;
  eagle_device: string;
  eagle_package: string;
  notes: string | null;
}

// Pagination response
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// Import CSV response
export interface ImportCsvResponse {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  error_rows?: { [key: string]: string }[];
}

// Stock check request/response
export interface StockCheckItem {
  manufacturer: string;
  mpn: string;
  quantity_needed: number;
}

export interface StockCheckResult {
  mpn: string;
  have: number;
  need: number;
  ok: boolean;
}

// Datasheet fetch response
export interface DatasheetFetchResponse {
  saved: boolean;
  path: string;
}