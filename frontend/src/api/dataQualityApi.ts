import axiosInstance from './axios';

export interface DataQualityIssue {
  id: string;
  company_id: string;
  issue_type: string;
  severity: string;
  affected_module: string;
  affected_record_id: string | null;
  affected_record_type: string | null;
  description: string;
  details: Record<string, any> | null;
  status: string;
  detected_at: string;
  detected_by_run_id: string | null;
  resolved_by: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  previous_status: string | null;
  created_at: string;
  updated_at: string;
}

export interface DataQualityIssueListResponse {
  data: DataQualityIssue[];
  total: number;
  page: number;
  limit: number;
}

export interface ReconciliationRun {
  id: string;
  company_id: string;
  execution_id: string;
  started_at: string;
  completed_at: string | null;
  triggered_by: string | null;
  triggered_by_name: string | null;
  records_checked: number;
  issues_detected: number;
  issues_resolved: number;
  failed_checks: number;
  status: string;
  error_message: string | null;
  summary: Record<string, any> | null;
}

export interface ReconciliationRunListResponse {
  data: ReconciliationRun[];
  total: number;
  page: number;
  limit: number;
}

export interface DataQualityDashboard {
  total_records_checked: number;
  valid_records: number;
  records_with_warnings: number;
  records_with_errors: number;
  unresolved_issues: number;
  last_reconciliation_time: string | null;
  issues_by_status: Record<string, number>;
  issues_by_severity: Record<string, number>;
  issues_by_module: Record<string, number>;
}

export const getDataQualityDashboard = async (): Promise<DataQualityDashboard> => {
  const { data } = await axiosInstance.get('/data-quality/dashboard');
  return data;
};

export const getDataQualityIssues = async (params?: {
  issue_type?: string;
  severity?: string;
  affected_module?: string;
  status?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  limit?: number;
}): Promise<DataQualityIssueListResponse> => {
  const { data } = await axiosInstance.get('/data-quality/issues', { params });
  return data;
};

export const getDataQualityIssue = async (issueId: string): Promise<DataQualityIssue> => {
  const { data } = await axiosInstance.get(`/data-quality/issues/${issueId}`);
  return data;
};

export const updateDataQualityIssueStatus = async (issueId: string, payload: { status: string; resolution_note?: string }): Promise<any> => {
  const { data } = await axiosInstance.put(`/data-quality/issues/${issueId}/status`, payload);
  return data;
};

export const triggerReconciliation = async (): Promise<any> => {
  const { data } = await axiosInstance.post('/data-quality/reconcile');
  return data;
};

export const getReconciliationHistory = async (params?: { page?: number; limit?: number }): Promise<ReconciliationRunListResponse> => {
  const { data } = await axiosInstance.get('/data-quality/reconciliation/history', { params });
  return data;
};
