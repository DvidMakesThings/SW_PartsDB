import api from './client';
import { d } from '../lib/debug';
import { 
  Component, 
  PaginatedResponse, 
  InventoryItem, 
  Attachment,
  ImportCsvResponse,
  StockCheckItem,
  StockCheckResult
} from './types';

// Components
export const listComponents = async (params?: {
  search?: string;
  manufacturer?: string;
  category_l1?: string;
  package_name?: string;
  in_stock_only?: boolean;
  page?: number;
}) => {
  d('API:listComponents', 'start', params);
  try {
    // Using full URL to avoid proxy issues
    const response = await api.get<PaginatedResponse<Component>>('/api/components/', { params });
    d('API:listComponents', 'success', { count: response.data.count, results: response.data.results.length });
    return response.data;
  } catch (error) {
    d('API:listComponents', 'error', error);
    throw error;
  }
};

export const getComponent = async (id: string) => {
  d('API:getComponent', 'start', { id });
  try {
    const response = await api.get<Component>(`/api/components/${id}/`);
    d('API:getComponent', 'success', { id: response.data.id, mpn: response.data.mpn });
    return response.data;
  } catch (error) {
    d('API:getComponent', 'error', { id, error });
    throw error;
  }
};

export const updateComponent = async (id: string, data: Partial<Component>) => {
  const response = await api.patch<Component>(`/api/components/${id}/`, data);
  return response.data;
};

// Inventory
export const listInventory = async (params?: {
  component_id?: string;
  page?: number;
}) => {
  const response = await api.get<PaginatedResponse<InventoryItem>>('/api/inventory/', { params });
  return response.data;
};

export const createInventory = async (data: Partial<InventoryItem>) => {
  const response = await api.post<InventoryItem>('/api/inventory/', data);
  return response.data;
};

export const updateInventory = async (id: string, data: Partial<InventoryItem>) => {
  const response = await api.patch<InventoryItem>(`/api/inventory/${id}/`, data);
  return response.data;
};

export const deleteInventory = async (id: string) => {
  const response = await api.delete(`/api/inventory/${id}/`);
  return response.data;
};

// Attachments
export const listAttachments = async (componentId?: string) => {
  const params = componentId ? { component_id: componentId } : {};
  const response = await api.get<PaginatedResponse<Attachment>>('/api/attachments/', { params });
  return response.data;
};

export const uploadAttachment = async (componentId: string, file: File, type: string) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('component_id', componentId);
  formData.append('type', type);

  const response = await api.post<Attachment>('/api/attachments/', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// Datasheet actions
export const fetchDatasheet = async (id: string) => {
  const response = await api.post<{ saved: boolean; path: string }>(`/api/components/${id}/fetch_datasheet/`);
  return response.data;
};

export const fetchMissingDatasheets = async () => {
  const response = await api.post<{ count: number }>('/api/components/fetch_missing_datasheets/');
  return response.data;
};

// CSV Import
export const importCsv = async (file: File, dryRun: boolean) => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('dry_run', dryRun.toString());

  const response = await api.post<ImportCsvResponse>('/api/import/csv', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });
  return response.data;
};

// Stock check
export const checkStock = async (items: StockCheckItem[]) => {
  const response = await api.post<StockCheckResult[]>('/api/components/check_stock', items);
  return response.data;
};