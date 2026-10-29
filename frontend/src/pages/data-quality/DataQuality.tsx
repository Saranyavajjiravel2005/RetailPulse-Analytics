import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useNotification } from '../../context/NotificationContext';
import {
  getDataQualityDashboard,
  getDataQualityIssues,
  triggerReconciliation,
  getReconciliationHistory,
  type DataQualityIssue,
  type ReconciliationRun,
} from '../../api/dataQualityApi';
import {
  CheckCircle as CheckCircleIcon,
  Warning as WarningIcon,
  Error as ErrorIcon,
  Refresh as RefreshIcon,
  Search as SearchIcon,
  FilterList as FilterIcon,
  Visibility as ViewIcon,
  History as HistoryIcon,
} from '@mui/icons-material';
import { Pagination } from '../../components/Pagination';

const inputClass =
  'bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg px-3 py-2 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 outline-none transition-all';

const SEVERITY_COLORS: Record<string, string> = {
  LOW: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  MEDIUM: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  HIGH: 'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
  CRITICAL: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  INVESTIGATING: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  RESOLVED: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  IGNORED: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
};

export const DataQuality: React.FC = () => {
  const { user } = useAuth();
  const { showNotification } = useNotification();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === 'COMPANY_ADMIN' || user?.role === 'SUPER_ADMIN';

  const [activeTab, setActiveTab] = useState<'dashboard' | 'issues' | 'history'>('dashboard');
  const [search, setSearch] = useState('');
  const [issueTypeFilter, setIssueTypeFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [moduleFilter, setModuleFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const [limit] = useState(25);
  const [showFilters, setShowFilters] = useState(false);

  const { data: dashboard, isLoading: dashLoading } = useQuery({
    queryKey: ['data-quality-dashboard'],
    queryFn: getDataQualityDashboard,
  });

  const { data: issuesData, isLoading: issuesLoading } = useQuery({
    queryKey: ['data-quality-issues', { search, issueTypeFilter, severityFilter, moduleFilter, statusFilter, dateFrom, dateTo, page, limit }],
    queryFn: () =>
      getDataQualityIssues({
        search: search || undefined,
        issue_type: issueTypeFilter || undefined,
        severity: severityFilter || undefined,
        affected_module: moduleFilter || undefined,
        status: statusFilter || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page,
        limit,
      }),
  });

  const { data: historyData } = useQuery({
    queryKey: ['reconciliation-history'],
    queryFn: () => getReconciliationHistory({ page: 1, limit: 50 }),
  });

  const reconcileMutation = useMutation({
    mutationFn: triggerReconciliation,
    onSuccess: (res) => {
      showNotification(`Reconciliation completed. Issues detected: ${res.issues_detected}`, 'success');
      queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] });
      queryClient.invalidateQueries({ queryKey: ['reconciliation-history'] });
    },
    onError: (err: any) => {
      showNotification(err?.response?.data?.detail || 'Reconciliation failed', 'error');
    },
  });

  const resetFilters = () => {
    setSearch('');
    setIssueTypeFilter('');
    setSeverityFilter('');
    setModuleFilter('');
    setStatusFilter('');
    setDateFrom('');
    setDateTo('');
    setPage(1);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Data Quality & Reconciliation</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">Monitor data consistency across Sales, Inventory, Products, and Customers</p>
        </div>
        {isAdmin && (
          <button
            onClick={() => reconcileMutation.mutate()}
            disabled={reconcileMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <RefreshIcon style={{ fontSize: 18 }} className={reconcileMutation.isPending ? 'animate-spin' : ''} />
            {reconcileMutation.isPending ? 'Running Reconciliation...' : 'Run Reconciliation'}
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-slate-200 dark:border-slate-800">
        <button onClick={() => setActiveTab('dashboard')} className={`px-4 py-2 text-sm font-medium`}>Dashboard</button>
        <button onClick={() => setActiveTab('issues')} className={`px-4 py-2 text-sm font-medium`}>Issues</button>
        <button onClick={() => setActiveTab('history')} className={`px-4 py-2 text-sm font-medium`}>Reconciliation History</button>
      </div>

      {activeTab === 'dashboard' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-4">
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Total Records Checked</p>
              <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">{dashboard?.total_records_checked || 0}</p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Valid Records</p>
              <p className="text-2xl font-bold text-emerald-600 mt-1">{dashboard?.valid_records || 0}</p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Records with Warnings</p>
              <p className="text-2xl font-bold text-amber-600 mt-1">{dashboard?.records_with_warnings || 0}</p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Records with Errors</p>
              <p className="text-2xl font-bold text-red-600 mt-1">{dashboard?.records_with_errors || 0}</p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Unresolved Issues</p>
              <p className="text-2xl font-bold text-orange-600 mt-1">{dashboard?.unresolved_issues || 0}</p>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4">
              <p className="text-xs text-slate-500 dark:text-slate-400">Last Reconciliation</p>
              <p className="text-xs font-medium text-slate-900 dark:text-white mt-1">{dashboard?.last_reconciliation_time ? new Date(dashboard.last_reconciliation_time).toLocaleString() : 'Never'}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Issues by Status</h3>
              <div className="space-y-2">
                {Object.entries(dashboard?.issues_by_status || {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center">
                    <span className="text-sm text-slate-600 dark:text-slate-400">{k}</span>
                    <span className="text-sm font-medium text-slate-900 dark:text-white">{v as number}</span>
                  </div>
                ))}
                {Object.keys(dashboard?.issues_by_status || {}).length === 0 && <p className="text-sm text-slate-500">No issues</p>}
              </div>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Issues by Severity</h3>
              <div className="space-y-2">
                {Object.entries(dashboard?.issues_by_severity || {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center">
                    <span className="text-sm text-slate-600 dark:text-slate-400">{k}</span>
                    <span className="text-sm font-medium text-slate-900 dark:text-white">{v as number}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-4">Issues by Module</h3>
              <div className="space-y-2">
                {Object.entries(dashboard?.issues_by_module || {}).map(([k, v]) => (
                  <div key={k} className="flex justify-between items-center">
                    <span className="text-sm text-slate-600 dark:text-slate-400">{k}</span>
                    <span className="text-sm font-medium text-slate-900 dark:text-white">{v as number}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'issues' && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" style={{ fontSize: 18 }} />
                <input
                  type="text"
                  placeholder="Search issues..."
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                  className={`${inputClass} w-full pl-9`}
                />
              </div>
              <button onClick={() => setShowFilters(!showFilters)} className="flex items-center gap-2 px-3 py-2 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800">
                <FilterIcon style={{ fontSize: 18 }} /> Filters
              </button>
              <button onClick={resetFilters} className="px-3 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white">Reset</button>
            </div>
            {showFilters && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
                <select value={issueTypeFilter} onChange={(e) => { setIssueTypeFilter(e.target.value); setPage(1); }} className={inputClass}>
                  <option value="">All Types</option>
                  <option value="SALE_EXCEEDS_STOCK">Sale Exceeds Stock</option>
                  <option value="INVENTORY_INCONSISTENT_WITH_MOVEMENTS">Inventory Inconsistent</option>
                  <option value="SALE_INACTIVE_OR_MISSING_PRODUCT">Inactive/Missing Product</option>
                  <option value="SALE_INVALID_CUSTOMER">Invalid Customer</option>
                  <option value="DUPLICATE_OR_INVALID_PRODUCT_SKU">Duplicate/Invalid SKU</option>
                  <option value="MISSING_MANDATORY_PRODUCT_CUSTOMER_INFO">Missing Mandatory Info</option>
                  <option value="STOCK_MOVEMENT_INCONSISTENT">Stock Movement Inconsistent</option>
                  <option value="REPORT_TOTAL_MISMATCH">Report Total Mismatch</option>
                </select>
                <select value={severityFilter} onChange={(e) => { setSeverityFilter(e.target.value); setPage(1); }} className={inputClass}>
                  <option value="">All Severities</option>
                  <option value="LOW">Low</option>
                  <option value="MEDIUM">Medium</option>
                  <option value="HIGH">High</option>
                  <option value="CRITICAL">Critical</option>
                </select>
                <select value={moduleFilter} onChange={(e) => { setModuleFilter(e.target.value); setPage(1); }} className={inputClass}>
                  <option value="">All Modules</option>
                  <option value="Sales">Sales</option>
                  <option value="Inventory">Inventory</option>
                  <option value="Products">Products</option>
                  <option value="Customers">Customers</option>
                </select>
                <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className={inputClass}>
                  <option value="">All Status</option>
                  <option value="OPEN">Open</option>
                  <option value="INVESTIGATING">Investigating</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="IGNORED">Ignored</option>
                </select>
                <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1); }} className={inputClass} />
              </div>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Issue ID</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Type</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Severity</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Module</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Affected Record</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Description</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Detected</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Status</th>
                  <th className="text-right text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Actions</th>
                </tr>
              </thead>
              <tbody>
                {issuesLoading && <tr><td colSpan={9} className="text-center py-8 text-slate-500">Loading...</td></tr>}
                {!issuesLoading && issuesData?.data?.length === 0 && <tr><td colSpan={9} className="text-center py-8 text-slate-500">No issues found</td></tr>}
                {issuesData?.data?.map((issue: DataQualityIssue) => (
                  <tr key={issue.id} className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="px-4 py-3 text-xs font-mono text-slate-600 dark:text-slate-400">{issue.id.slice(0, 8)}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{issue.issue_type.replace(/_/g, ' ')}</td>
<td className="px-4 py-3"><span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${SEVERITY_COLORS[issue.severity] || 'bg-slate-100 text-slate-700'}`}>{issue.severity}</span></td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{issue.affected_module}</td>
                    <td className="px-4 py-3 text-xs font-mono text-slate-600 dark:text-slate-400">{issue.affected_record_id?.slice(0, 8) || '-'}</td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400 max-w-xs truncate">{issue.description}</td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{new Date(issue.detected_at).toLocaleString()}</td>
<td className="px-4 py-3"><span className={`px-2.5 py-1 rounded-full text-xs font-semibold ${STATUS_COLORS[issue.status] || 'bg-slate-100 text-slate-700'}`}>{issue.status}</span></td>
                    <td className="px-4 py-3 text-right">
<button onClick={() => navigate(`/data-quality/issues/${issue.id}`)} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded">
                        <ViewIcon style={{ fontSize: 18 }} className="text-slate-500" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {issuesData && (
            <div className="p-4 border-t border-slate-200 dark:border-slate-800">
              <Pagination
                currentPage={page}
                totalPages={Math.ceil((issuesData.total || 0) / limit)}
                onPageChange={setPage}
              />
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800">
          <div className="p-4 border-b border-slate-200 dark:border-slate-800">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white flex items-center gap-2"><HistoryIcon /> Reconciliation History</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Execution ID</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Started</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Completed</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Triggered By</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Records Checked</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Issues Detected</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Issues Resolved</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Failed Checks</th>
                  <th className="text-left text-xs font-medium text-slate-500 dark:text-slate-400 px-4 py-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {historyData?.data?.map((run: ReconciliationRun) => (
                  <tr key={run.id} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-4 py-3 text-xs font-mono text-slate-600 dark:text-slate-400">{run.execution_id}</td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{new Date(run.started_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{run.completed_at ? new Date(run.completed_at).toLocaleString() : '-'}</td>
                    <td className="px-4 py-3 text-xs text-slate-600 dark:text-slate-400">{run.triggered_by_name || '-'}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{run.records_checked}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{run.issues_detected}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{run.issues_resolved}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{run.failed_checks}</td>
                    <td className="px-4 py-3 text-xs text-slate-900 dark:text-white">{run.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

export default DataQuality;
