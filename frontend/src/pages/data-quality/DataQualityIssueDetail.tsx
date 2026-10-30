import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../context/AuthContext';
import { useNotification } from '../../context/NotificationContext';
import {
  getDataQualityIssue,
  updateDataQualityIssueStatus,
  getDataQualityIssueHistory,
} from '../../api/dataQualityApi';
import {
  ArrowBack as ArrowBackIcon,
  Save as SaveIcon,
  WarningAmber as WarningIcon,
  Inventory as InventoryIcon,
  Receipt as ReceiptIcon,
  Code as CodeIcon,
  ExpandMore as ExpandMoreIcon,
  ExpandLess as ExpandLessIcon,
} from '@mui/icons-material';

const inputClass =
  'bg-slate-900 border border-slate-700/80 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 outline-none transition-all';

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-rose-950/70 text-rose-400 border border-rose-800/50',
  HIGH: 'bg-rose-950/70 text-rose-400 border border-rose-800/50',
  MEDIUM: 'bg-amber-950/70 text-amber-400 border border-amber-800/50',
  LOW: 'bg-slate-800 text-slate-300 border border-slate-700/50',
};

const STATUS_COLORS: Record<string, string> = {
  OPEN: 'bg-amber-950/70 text-amber-400 border border-amber-800/50',
  INVESTIGATING: 'bg-blue-950/70 text-blue-400 border border-blue-800/50',
  RESOLVED: 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/50',
  IGNORED: 'bg-slate-800 text-slate-400 border border-slate-700/50',
};

export const DataQualityIssueDetail: React.FC = () => {
  const { id, issueId } = useParams<{ id?: string; issueId?: string }>();
  const effectiveId = id || issueId;
  const navigate = useNavigate();
  const { user } = useAuth();
  const { showNotification } = useNotification();
  const queryClient = useQueryClient();
  const isAdmin = user?.role === 'COMPANY_ADMIN' || user?.role === 'SUPER_ADMIN';

  const [status, setStatus] = useState('');
  const [resolutionNote, setResolutionNote] = useState('');
  const [showRawJson, setShowRawJson] = useState(false);

  const { data: issue, isLoading } = useQuery({
    queryKey: ['data-quality-issue', effectiveId],
    queryFn: () => getDataQualityIssue(effectiveId!),
    enabled: !!effectiveId,
  });

  const { data: historyData } = useQuery({
    queryKey: ['data-quality-issue-history', effectiveId],
    queryFn: () => getDataQualityIssueHistory(effectiveId!),
    enabled: !!effectiveId,
  });

  React.useEffect(() => {
    if (issue?.status) {
      setStatus(issue.status);
    }
  }, [issue?.status]);

  const updateMutation = useMutation({
    mutationFn: () =>
      updateDataQualityIssueStatus(effectiveId!, {
        status,
        resolution_note: resolutionNote,
      }),
    onSuccess: () => {
      showNotification('Issue status updated', 'success');
      queryClient.invalidateQueries({ queryKey: ['data-quality-issue', effectiveId] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issue-history', effectiveId] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] });
    },
    onError: (err: any) => {
      showNotification(err?.response?.data?.detail || 'Failed to update issue', 'error');
    },
  });

  if (isLoading) {
    return <div className="p-8 text-center text-slate-400 text-xs">Loading issue details...</div>;
  }

  if (!issue) {
    return <div className="p-8 text-center text-slate-400 text-xs">Issue not found</div>;
  }

  const details = issue.details || {};
  const isInventoryMismatch =
    issue.issue_type === 'INVENTORY_INCONSISTENT_WITH_MOVEMENTS' ||
    details.current_inventory !== undefined ||
    details.expected_quantity !== undefined;

  const isTotalMismatch =
    issue.issue_type === 'REPORT_TOTAL_MISMATCH' || details.header_total !== undefined;

  return (
    <div className="space-y-4 text-slate-100">
      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400">
        <button
          onClick={() => navigate('/data-quality')}
          className="hover:text-white transition-colors"
        >
          Data Quality
        </button>
        <span className="text-slate-600">/</span>
        <button
          onClick={() => navigate('/data-quality/issues')}
          className="hover:text-white transition-colors"
        >
          Issues
        </button>
        <span className="text-slate-600">/</span>
        <span className="text-slate-300 font-mono text-[11px]">{issue.id.slice(0, 8)}…</span>
      </div>

      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/data-quality/issues')}
          className="p-1.5 rounded-lg border border-slate-700/80 bg-slate-800/50 hover:bg-slate-800 text-slate-300 transition-colors"
          title="Back to Issues"
        >
          <ArrowBackIcon style={{ fontSize: 16 }} />
        </button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Issue Details</h1>
          <p className="text-xs text-slate-400 font-mono mt-0.5">ID: {issue.id}</p>
        </div>
      </div>

      {/* Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Issue Information Card */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 space-y-4 shadow-sm">
          <h3 className="text-sm font-semibold text-white">Issue Information</h3>
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <p className="text-slate-400">Type</p>
              <p className="text-white mt-1 font-medium">
                {issue.issue_type?.replace(/_/g, ' ') || '-'}
              </p>
            </div>
            <div>
              <p className="text-slate-400">Severity</p>
              <div className="mt-1">
                <span
                  className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                    SEVERITY_COLORS[issue.severity] || 'bg-slate-800 text-slate-300'
                  }`}
                >
                  {issue.severity}
                </span>
              </div>
            </div>
            <div>
              <p className="text-slate-400">Module</p>
              <p className="text-white mt-1 font-medium">{issue.affected_module}</p>
            </div>
            <div>
              <p className="text-slate-400">Status</p>
              <div className="mt-1">
                <span
                  className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-semibold ${
                    STATUS_COLORS[issue.status] || 'bg-slate-800 text-slate-300'
                  }`}
                >
                  {issue.status}
                </span>
              </div>
            </div>
            <div className="col-span-2">
              <p className="text-slate-400">Affected Record</p>
              <p className="text-slate-300 mt-1 font-mono text-[11px]">
                {issue.affected_record_id || '-'} {issue.affected_record_type ? `(${issue.affected_record_type})` : ''}
              </p>
            </div>
            <div className="col-span-2">
              <p className="text-slate-400">Description</p>
              <p className="text-white mt-1 text-xs">{issue.description}</p>
            </div>
            <div>
              <p className="text-slate-400">Detected At</p>
              <p className="text-slate-300 mt-1">
                {issue.detected_at ? new Date(issue.detected_at).toLocaleString() : '-'}
              </p>
            </div>
            <div>
              <p className="text-slate-400">Resolved At</p>
              <p className="text-slate-300 mt-1">
                {issue.resolved_at ? new Date(issue.resolved_at).toLocaleString() : '-'}
              </p>
            </div>
            {issue.resolved_by_name && (
              <div>
                <p className="text-slate-400">Resolved By</p>
                <p className="text-white mt-1">{issue.resolved_by_name}</p>
              </div>
            )}
            {issue.resolution_note && (
              <div className="col-span-2">
                <p className="text-slate-400">Resolution Note</p>
                <p className="text-slate-200 mt-1">{issue.resolution_note}</p>
              </div>
            )}
          </div>
        </div>

        {/* Update Status Card */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 space-y-4 shadow-sm">
          <h3 className="text-sm font-semibold text-white">Issue Resolution</h3>
          {isAdmin ? (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-slate-400 block mb-1">Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className={`${inputClass} w-full`}
                >
                  <option value="OPEN">Open</option>
                  <option value="INVESTIGATING">Investigating</option>
                  <option value="RESOLVED">Resolved</option>
                  <option value="IGNORED">Ignored</option>
                </select>
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1">Resolution Note</label>
                <textarea
                  placeholder="Explain resolution, root cause, or rationale..."
                  value={resolutionNote}
                  onChange={(e) => setResolutionNote(e.target.value)}
                  className={`${inputClass} w-full h-24 resize-none`}
                />
              </div>
              <button
                onClick={() => updateMutation.mutate()}
                disabled={updateMutation.isPending}
                className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-all disabled:opacity-50"
              >
                <SaveIcon style={{ fontSize: 16 }} />
                <span>{updateMutation.isPending ? 'Saving...' : 'Save Status Update'}</span>
              </button>
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              Only Administrators have permission to modify issue statuses and resolution notes.
            </p>
          )}
        </div>

        {/* Structured Inconsistency Breakdown */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 space-y-4 lg:col-span-2 shadow-sm">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white flex items-center gap-2">
              <WarningIcon style={{ fontSize: 18 }} className="text-amber-400" />
              <span>Inconsistency Analysis</span>
            </h3>
            <button
              onClick={() => setShowRawJson(!showRawJson)}
              className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1"
            >
              <CodeIcon style={{ fontSize: 14 }} />
              <span>{showRawJson ? 'Hide Raw Details' : 'View Raw Details'}</span>
              {showRawJson ? <ExpandLessIcon style={{ fontSize: 14 }} /> : <ExpandMoreIcon style={{ fontSize: 14 }} />}
            </button>
          </div>

          {/* Inventory Mismatch Detailed View */}
          {isInventoryMismatch && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/60 p-4 rounded-lg border border-slate-800/80">
                <div>
                  <span className="text-[11px] text-slate-400">Product Name</span>
                  <p className="text-sm font-bold text-white mt-0.5">{details.product_name || 'N/A'}</p>
                  <p className="text-[10px] text-slate-500 font-mono">SKU: {details.sku || '-'}</p>
                </div>
                <div>
                  <span className="text-[11px] text-slate-400">Current Inventory</span>
                  <p className="text-sm font-bold text-blue-400 mt-0.5">{details.current_inventory ?? '-'}</p>
                </div>
                <div>
                  <span className="text-[11px] text-slate-400">Expected Quantity</span>
                  <p className="text-sm font-bold text-emerald-400 mt-0.5">{details.expected_quantity ?? '-'}</p>
                </div>
                <div>
                  <span className="text-[11px] text-slate-400">Discrepancy (Diff)</span>
                  <p className="text-sm font-bold text-rose-400 mt-0.5">
                    {details.difference !== undefined ? (details.difference > 0 ? `+${details.difference}` : details.difference) : '-'}
                  </p>
                </div>
              </div>

              {/* Relevant Stock Movements */}
              {details.relevant_stock_movements && details.relevant_stock_movements.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <InventoryIcon style={{ fontSize: 15 }} className="text-indigo-400" />
                    <span>Relevant Stock Movements</span>
                  </h4>
                  <div className="overflow-x-auto rounded-lg border border-slate-800">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950/80 text-[10px] text-slate-400 uppercase">
                        <tr>
                          <th className="px-3 py-2">Movement Type</th>
                          <th className="px-3 py-2">Prev Qty</th>
                          <th className="px-3 py-2">Changed</th>
                          <th className="px-3 py-2">Updated Qty</th>
                          <th className="px-3 py-2">Date</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {details.relevant_stock_movements.map((mv: any, idx: number) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="px-3 py-2 text-slate-300 font-medium">{mv.type}</td>
                            <td className="px-3 py-2 text-slate-400">{mv.previous_quantity}</td>
                            <td className="px-3 py-2 text-indigo-400 font-semibold">{mv.quantity_changed}</td>
                            <td className="px-3 py-2 text-emerald-400 font-semibold">{mv.updated_quantity}</td>
                            <td className="px-3 py-2 text-slate-500 text-[11px]">
                              {mv.created_at ? new Date(mv.created_at).toLocaleString() : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Related Sales */}
              {details.related_sales && details.related_sales.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <ReceiptIcon style={{ fontSize: 15 }} className="text-emerald-400" />
                    <span>Related Sales</span>
                  </h4>
                  <div className="overflow-x-auto rounded-lg border border-slate-800">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950/80 text-[10px] text-slate-400 uppercase">
                        <tr>
                          <th className="px-3 py-2">Invoice</th>
                          <th className="px-3 py-2">Quantity Sold</th>
                          <th className="px-3 py-2">Sale Date</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60">
                        {details.related_sales.map((s: any, idx: number) => (
                          <tr key={idx} className="hover:bg-slate-800/30">
                            <td className="px-3 py-2 text-slate-200 font-mono text-[11px]">{s.invoice_number}</td>
                            <td className="px-3 py-2 text-indigo-400 font-semibold">{s.quantity}</td>
                            <td className="px-3 py-2 text-slate-500 text-[11px]">
                              {s.sale_date ? new Date(s.sale_date).toLocaleString() : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Total Mismatch Detailed View */}
          {isTotalMismatch && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/60 p-4 rounded-lg border border-slate-800/80 text-xs">
              <div>
                <span className="text-[11px] text-slate-400">Invoice Number</span>
                <p className="text-sm font-bold text-white mt-0.5">{details.invoice_number || 'N/A'}</p>
              </div>
              <div>
                <span className="text-[11px] text-slate-400">Header Total</span>
                <p className="text-sm font-bold text-blue-400 mt-0.5">
                  ${typeof details.header_total === 'number' ? details.header_total.toFixed(2) : details.header_total}
                </p>
              </div>
              <div>
                <span className="text-[11px] text-slate-400">Calculated Line Total</span>
                <p className="text-sm font-bold text-emerald-400 mt-0.5">
                  ${typeof details.calculated_items_total === 'number' ? details.calculated_items_total.toFixed(2) : details.calculated_items_total}
                </p>
              </div>
              <div>
                <span className="text-[11px] text-slate-400">Difference</span>
                <p className="text-sm font-bold text-rose-400 mt-0.5">
                  ${typeof details.difference === 'number' ? details.difference.toFixed(2) : details.difference}
                </p>
              </div>
            </div>
          )}

          {/* Raw JSON viewer */}
          {showRawJson && (
            <pre className="bg-slate-950 p-4 rounded-lg text-xs overflow-auto max-h-64 text-slate-300 border border-slate-800 font-mono">
              {JSON.stringify(details, null, 2)}
            </pre>
          )}
        </div>

        {/* Status History Card */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 space-y-4 lg:col-span-2 shadow-sm">
          <h3 className="text-sm font-semibold text-white">Status History & Audit Trail</h3>
          {historyData && historyData.length > 0 ? (
            <div className="space-y-2.5">
              {historyData.map((h) => (
                <div
                  key={h.id}
                  className="border border-slate-800 rounded-lg p-3 text-xs bg-slate-950/40"
                >
                  <div className="flex justify-between items-center">
                    <span className="text-white font-medium">
                      {h.previous_status || 'INITIAL'} &rarr;{' '}
                      <span className="text-indigo-400 font-semibold">{h.new_status}</span>
                    </span>
                    <span className="text-slate-500 text-[11px]">
                      {h.changed_at ? new Date(h.changed_at).toLocaleString() : '-'}
                    </span>
                  </div>
                  {h.changed_by_name && (
                    <p className="text-slate-400 mt-1">Changed by: {h.changed_by_name}</p>
                  )}
                  {h.resolution_note && (
                    <p className="text-slate-300 mt-1 bg-slate-900 p-2 rounded border border-slate-800">
                      Note: {h.resolution_note}
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500">No previous status changes recorded.</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default DataQualityIssueDetail;
