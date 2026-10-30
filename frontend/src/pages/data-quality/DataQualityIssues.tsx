import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getDataQualityIssues, type DataQualityIssue } from '../../api/dataQualityApi';
import {
  Refresh as RefreshIcon,
  Search as SearchIcon,
} from '@mui/icons-material';

const selectClass =
  'bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-300 focus:border-indigo-500 outline-none transition-all';
const inputClass =
  'bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-300 placeholder-slate-500 focus:border-indigo-500 outline-none transition-all';

const SEVERITY_BADGES: Record<string, string> = {
  CRITICAL: 'bg-rose-950/70 text-rose-400 border border-rose-800/50',
  HIGH: 'bg-rose-950/70 text-rose-400 border border-rose-800/50',
  MEDIUM: 'bg-amber-950/70 text-amber-400 border border-amber-800/50',
  LOW: 'bg-slate-800 text-slate-300 border border-slate-700/50',
};

const STATUS_BADGES: Record<string, string> = {
  OPEN: 'bg-amber-950/70 text-amber-400 border border-amber-800/50',
  INVESTIGATING: 'bg-blue-950/70 text-blue-400 border border-blue-800/50',
  RESOLVED: 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/50',
  IGNORED: 'bg-slate-800 text-slate-400 border border-slate-700/50',
};

export const DataQualityIssues: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Inputs
  const [searchInput, setSearchInput] = useState('');
  const [issueTypeInput, setIssueTypeInput] = useState('');
  const [statusInput, setStatusInput] = useState('');
  const [severityInput, setSeverityInput] = useState('');
  const [moduleInput, setModuleInput] = useState('');
  const [dateFromInput, setDateFromInput] = useState('');
  const [dateToInput, setDateToInput] = useState('');

  // Applied
  const [applied, setApplied] = useState({
    search: '',
    issue_type: '',
    status: '',
    severity: '',
    module: '',
    date_from: '',
    date_to: '',
  });

  const [page, setPage] = useState(1);
  const limit = 25;

  const { data: issuesData, isLoading, isFetching } = useQuery({
    queryKey: ['data-quality-issues', { ...applied, page, limit }],
    queryFn: () =>
      getDataQualityIssues({
        search: applied.search || undefined,
        issue_type: applied.issue_type || undefined,
        status: applied.status || undefined,
        severity: applied.severity || undefined,
        affected_module: applied.module || undefined,
        date_from: applied.date_from || undefined,
        date_to: applied.date_to || undefined,
        page,
        limit,
      }),
  });

  const handleApply = () => {
    setPage(1);
    setApplied({
      search: searchInput,
      issue_type: issueTypeInput,
      status: statusInput,
      severity: severityInput,
      module: moduleInput,
      date_from: dateFromInput,
      date_to: dateToInput,
    });
  };

  const handleClear = () => {
    setSearchInput('');
    setIssueTypeInput('');
    setStatusInput('');
    setSeverityInput('');
    setModuleInput('');
    setDateFromInput('');
    setDateToInput('');
    setPage(1);
    setApplied({
      search: '',
      issue_type: '',
      status: '',
      severity: '',
      module: '',
      date_from: '',
      date_to: '',
    });
  };

  const issues: DataQualityIssue[] = issuesData?.data || [];
  const total = issuesData?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const formatIssueType = (type: string) => {
    if (!type) return '-';
    return type
      .toLowerCase()
      .split('_')
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(' ');
  };

  const formatStatus = (status: string) => {
    if (!status) return '-';
    return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
  };

  return (
    <div className="space-y-4 text-slate-100">
      {/* Breadcrumb matching screenshot */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400">
        <button
          onClick={() => navigate('/data-quality')}
          className="hover:text-white transition-colors flex items-center gap-1"
        >
          <span>&larr;</span>
          <span>Data Quality</span>
        </button>
        <span className="text-slate-600">/</span>
        <span className="text-slate-300">Issues</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Data Quality Issues</h1>
          <p className="text-xs text-slate-400 mt-1">
            Review, investigate, and resolve data anomalies across your retail modules.
          </p>
        </div>

        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] })}
          disabled={isFetching}
          className="self-start sm:self-auto px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors"
        >
          <RefreshIcon style={{ fontSize: 15 }} className={isFetching ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Filter Card matching Screenshot 2 */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-4 space-y-3 shadow-sm">
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2.5">
          {/* Search */}
          <div className="relative lg:col-span-1">
            <input
              type="text"
              placeholder="Search description..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleApply()}
              className={`${inputClass} w-full pl-7`}
            />
            <SearchIcon
              className="absolute left-2.5 top-2.5 text-slate-500 pointer-events-none"
              style={{ fontSize: 14 }}
            />
          </div>

          {/* Issue Type */}
          <select
            value={issueTypeInput}
            onChange={(e) => setIssueTypeInput(e.target.value)}
            className={selectClass}
          >
            <option value="">All Issue Types</option>
            <option value="DUPLICATE_SKU">Duplicate Product SKU</option>
            <option value="MISSING_MANDATORY_FIELDS">Missing Mandatory Fields</option>
            <option value="SALE_EXCEEDS_STOCK">Sale Exceeds Stock</option>
            <option value="SALE_INACTIVE_OR_MISSING_PRODUCT">Inactive Product Sale</option>
            <option value="SALE_INVALID_CUSTOMER">Invalid Customer Sale</option>
            <option value="STOCK_INCONSISTENCY">Stock Inconsistency</option>
            <option value="ORPHAN_TRANSACTION">Orphan Transaction</option>
          </select>

          {/* Status */}
          <select
            value={statusInput}
            onChange={(e) => setStatusInput(e.target.value)}
            className={selectClass}
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
            <option value="IGNORED">Ignored</option>
          </select>

          {/* Severity */}
          <select
            value={severityInput}
            onChange={(e) => setSeverityInput(e.target.value)}
            className={selectClass}
          >
            <option value="">All Severities</option>
            <option value="CRITICAL">Critical</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
          </select>

          {/* Module */}
          <select
            value={moduleInput}
            onChange={(e) => setModuleInput(e.target.value)}
            className={selectClass}
          >
            <option value="">All Modules</option>
            <option value="Products">Products</option>
            <option value="Inventory">Inventory</option>
            <option value="Sales">Sales</option>
            <option value="Customers">Customers</option>
            <option value="Reports">Reports</option>
          </select>

          {/* Date from */}
          <input
            type="date"
            placeholder="dd-mm-yyyy"
            value={dateFromInput}
            onChange={(e) => setDateFromInput(e.target.value)}
            className={inputClass}
          />

          {/* Date to */}
          <input
            type="date"
            placeholder="dd-mm-yyyy"
            value={dateToInput}
            onChange={(e) => setDateToInput(e.target.value)}
            className={inputClass}
          />
        </div>

        {/* Buttons Row */}
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={handleApply}
            className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-all"
          >
            Apply Filters
          </button>
          <button
            onClick={handleClear}
            className="px-3 py-1.5 rounded-lg border border-slate-700/80 hover:bg-slate-800 text-slate-300 text-xs font-medium transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Issues Table */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                <th className="px-4 py-3.5">ID</th>
                <th className="px-4 py-3.5">ISSUE TYPE</th>
                <th className="px-4 py-3.5">SEVERITY</th>
                <th className="px-4 py-3.5">MODULE</th>
                <th className="px-4 py-3.5">DESCRIPTION</th>
                <th className="px-4 py-3.5">STATUS</th>
                <th className="px-4 py-3.5">DETECTED</th>
                <th className="px-4 py-3.5 text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    Loading data quality issues...
                  </td>
                </tr>
              ) : issues.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                    No data anomalies found.
                  </td>
                </tr>
              ) : (
                issues.map((issue) => (
                  <tr
                    key={issue.id}
                    className="hover:bg-slate-800/40 transition-colors"
                  >
                    {/* ID */}
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-400">
                      {issue.id ? `${issue.id.slice(0, 8)}…` : '-'}
                    </td>

                    {/* ISSUE TYPE */}
                    <td className="px-4 py-3 text-slate-200 font-medium">
                      {formatIssueType(issue.issue_type)}
                    </td>

                    {/* SEVERITY */}
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                          SEVERITY_BADGES[issue.severity] || 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {issue.severity}
                      </span>
                    </td>

                    {/* MODULE */}
                    <td className="px-4 py-3">
                      <span className="inline-block px-2 py-0.5 rounded bg-slate-800/80 text-slate-300 text-[10px] border border-slate-700/50">
                        {issue.affected_module}
                      </span>
                    </td>

                    {/* DESCRIPTION */}
                    <td
                      className="px-4 py-3 text-slate-400 max-w-sm truncate text-xs"
                      title={issue.description}
                    >
                      {issue.description}
                    </td>

                    {/* STATUS */}
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-semibold ${
                          STATUS_BADGES[issue.status] || 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {formatStatus(issue.status)}
                      </span>
                    </td>

                    {/* DETECTED */}
                    <td className="px-4 py-3 text-slate-400 text-[11px]">
                      {issue.detected_at
                        ? new Date(issue.detected_at).toLocaleDateString('en-GB')
                        : '-'}
                    </td>

                    {/* ACTIONS */}
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => navigate(`/data-quality/issues/${issue.id}`)}
                        className="px-3 py-1 rounded border border-indigo-500/40 hover:bg-indigo-500/10 text-indigo-400 text-xs font-medium transition-colors"
                      >
                        View Details
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between pt-1">
        <p className="text-xs text-slate-400">
          Showing {issues.length} of {total} issues
        </p>
        <div className="flex items-center gap-2 text-xs">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-3 py-1 rounded border border-slate-700/80 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Previous
          </button>
          <span className="px-2 text-slate-400">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => (p < totalPages ? p + 1 : p))}
            disabled={page >= totalPages}
            className="px-3 py-1 rounded border border-slate-700/80 text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
};

export default DataQualityIssues;
