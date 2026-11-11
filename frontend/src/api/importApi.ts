import axiosInstance from './axios';

export type ImportType = 'PRODUCTS' | 'INVENTORY' | 'CUSTOMERS' | 'SALES';

export type ImportStatus =
  | 'UPLOADED'
  | 'PENDING'
  | 'VALIDATING'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'COMPLETED_WITH_ERRORS'
  | 'FAILED'
  | 'CANCELLED';

export type DuplicateAction = 'SKIP' | 'UPDATE' | 'REJECT';

export interface ImportHistoryItem {
  id: string;
  company_id: string;
  import_type: string;
  filename: string;
  uploaded_by: string | null;
  uploaded_by_name: string | null;
  total_records: number;
  successful_records: number;
  failed_records: number;
  duplicate_records: number;
  skipped_records: number;
  status: string;
  created_at: string;
  completed_at: string | null;
  duration_seconds?: number | null;
}

export interface ImportErrorItem {
  id?: string;
  import_id?: string;
  row_number: number;
  field: string | null;
  error_type?: string;
  error_message: string;
  raw_data: string | null;
}

export interface ImportPreviewResponse {
  import_id: string;
  import_type: string;
  filename: string;
  total_records: number;
  columns: string[];
  preview_rows: Record<string, string>[];
  valid_records: number;
  invalid_records: number;
  duplicate_records: number;
  errors: ImportErrorItem[];
  status?: string;
}

export interface ImportResultResponse {
  import_id: string;
  import_type: string;
  filename: string;
  total_records: number;
  successful_records: number;
  failed_records: number;
  duplicate_records: number;
  skipped_records: number;
  status: string;
  errors: ImportErrorItem[];
  duration_seconds?: number | null;
  reconciliation?: {
    status?: string;
    issues_detected?: number;
    message?: string;
  } | null;
}

export interface ImportUploadResponse {
  import_id: string;
  import_type: string;
  filename: string;
  total_records: number;
  status: string;
}

export const getImportHistory = async (params?: {
  import_type?: ImportType;
  status?: ImportStatus;
  skip?: number;
  limit?: number;
}): Promise<ImportHistoryItem[]> => {
  const { data } = await axiosInstance.get('/import/history', { params });
  return data;
};

export const getImportDetail = async (importId: string): Promise<ImportHistoryItem> => {
  const { data } = await axiosInstance.get(`/import/${importId}`);
  return data;
};

export const getImportErrors = async (importId: string): Promise<ImportErrorItem[]> => {
  const { data } = await axiosInstance.get(`/import/${importId}/errors`);
  return data;
};

export const uploadImport = async (importType: ImportType, file: File): Promise<ImportUploadResponse> => {
  const form = new FormData();
  form.append('import_type', importType);
  form.append('file', file);
  const { data } = await axiosInstance.post('/import/upload', form);
  return data;
};

export const validateImport = async (
  importType: ImportType,
  file: File,
  importId?: string,
  duplicateAction: DuplicateAction = 'SKIP'
): Promise<ImportPreviewResponse> => {
  const form = new FormData();
  form.append('import_type', importType);
  form.append('file', file);
  form.append('duplicate_action', duplicateAction);
  if (importId) {
    form.append('import_id', importId);
  }
  const { data } = await axiosInstance.post('/import/validate', form);
  return data;
};

export const startImport = async (
  importType: ImportType,
  file: File,
  importId?: string,
  duplicateAction: DuplicateAction = 'SKIP'
): Promise<ImportUploadResponse> => {
  const form = new FormData();
  form.append('import_type', importType);
  form.append('file', file);
  form.append('duplicate_action', duplicateAction);
  if (importId) {
    form.append('import_id', importId);
  }
  const { data } = await axiosInstance.post('/import/start', form);
  return data;
};

export const processImport = async (
  importType: ImportType,
  file: File,
  importId?: string,
  duplicateAction: DuplicateAction = 'SKIP'
): Promise<ImportResultResponse> => {
  const form = new FormData();
  form.append('import_type', importType);
  form.append('file', file);
  form.append('duplicate_action', duplicateAction);
  if (importId) {
    form.append('import_id', importId);
  }
  const { data } = await axiosInstance.post('/import/process', form);
  return data;
};

export const downloadTemplate = async (importType: ImportType): Promise<Blob> => {
  const response = await axiosInstance.get(`/import/template/${importType}`, {
    responseType: 'blob',
  });
  return response.data;
};

export const downloadErrorReport = async (importId: string): Promise<Blob> => {
  const response = await axiosInstance.get(`/import/${importId}/errors/download`, {
    responseType: 'blob',
  });
  return response.data;
};

export const cancelImport = async (importId: string): Promise<ImportHistoryItem> => {
  const { data } = await axiosInstance.post(`/import/${importId}/cancel`);
  return data;
};
