import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useNotification } from '../../context/NotificationContext';
import {
  getReconciliationHistory,
  triggerReconciliation,
  type ReconciliationRun,
} from '../../api/dataQualityApi';
import {
  PlayArrow as PlayIcon,
  Refresh as RefreshIcon,
} from '@mui/icons-material';

const STATUS_BADGES: Record<string, string> = {
  COMPLETED: 'bg-emerald-950/70 text-emerald-400 border border-emerald-800/50',
  COMPLETED_WITH_ISSUES: 'bg-amber-950/70 text-amber-400 border border-amber-800/50',
  FAILED: 'bg-rose-950/70 text-rose-400 border border-rose-800/50',
  RUNNING: 'bg-blue-950/70 text-blue-400 border border-blue-800/50',
  QUEUED: 'bg-slate-800 text-slate-400 border border-slate-700/50',
};

export const ReconciliationHistory: React.FC = () => {
  const navigate = useNavigate();
  const { showNotification } = useNotification();
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const limit = 25;

  const { data: historyData, isLoading, isFetching } = useQuery({
    queryKey: ['reconciliation-history', { page, limit }],
    queryFn: () => getReconciliationHistory({ page, limit }),
  });

  const reconcileMutation = useMutation({
    mutationFn: triggerReconciliation,
    onSuccess: (res) => {
      showNotification(`Reconciliation completed. Issues detected: ${res.issues_detected ?? 0}`, 'success');
      queryClient.invalidateQueries({ queryKey: ['reconciliation-history'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] });
    },
    onError: (err: any) => {
      showNotification(err?.response?.data?.detail || 'Reconciliation failed', 'error');
    },
  });

  const runs: ReconciliationRun[] = historyData?.data || [];
  const total = historyData?.total || 0;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const formatStatus = (st: string) => {
    if (!st) return 'COMPLETED';
    return st.replace(/_/g, ' ');
  };

  return (
    <div className="space-y-4 text-slate-100">
      {/* Breadcrumb matching Screenshot 1 */}
      <div className="flex items-center gap-1.5 text-xs text-slate-400">
        <button
          onClick={() => navigate('/data-quality')}
          className="hover:text-white transition-colors flex items-center gap-1"
        >
          <span>&larr;</span>
          <span>Data Quality</span>
        </button>
        <span className="text-slate-600">/</span>
        <span className="text-slate-300">Reconciliation</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Reconciliation History</h1>
          <p className="text-xs text-slate-400 mt-1">
            Audit logs of reconciliation runs verifying transactional and inventory records.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['reconciliation-history'] })}
            disabled={isFetching}
            className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <RefreshIcon style={{ fontSize: 15 }} className={isFetching ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => reconcileMutation.mutate()}
            disabled={reconcileMutation.isPending}
            className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-900/30 transition-all disabled:opacity-50"
          >
            {reconcileMutation.isPending ? (
              <RefreshIcon style={{ fontSize: 15 }} className="animate-spin" />
            ) : (
              <PlayIcon style={{ fontSize: 16 }} />
            )}
            <span>{reconcileMutation.isPending ? 'Running...' : 'Run Reconciliation'}</span>
          </button>
        </div>
      </div>

      {/* Table matching Screenshot 1 */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                <th className="px-4 py-3.5">RUN ID</th>
                <th className="px-4 py-3.5">STARTED AT</th>
                <th className="px-4 py-3.5">STATUS</th>
                <th className="px-4 py-3.5">RECORDS CHECKED</th>
                <th className="px-4 py-3.5">ISSUES DETECTED</th>
                <th className="px-4 py-3.5">FAILED CHECKS</th>
                <th className="px-4 py-3.5 text-right">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    Loading reconciliation history...
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-500">
                    No reconciliation runs recorded yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.id}
                    className="hover:bg-slate-800/40 transition-colors"
                  >
                    {/* RUN ID */}
                    <td className="px-4 py-3.5 font-mono text-[11px] text-slate-400">
                      {run.execution_id || (run.id ? `${run.id.slice(0, 8)}…` : '-')}
                    </td>

                    {/* STARTED AT */}
                    <td className="px-4 py-3.5 text-slate-200 font-medium">
                      {run.started_at
                        ? new Date(run.started_at).toLocaleString('en-GB', {
                            day: '2-digit',
                            month: '2-digit',
                            year: 'numeric',
                            hour: 'numeric',
                            minute: '2-digit',
                            second: '2-digit',
                            hour12: true,
                          })
                        : '-'}
                    </td>

                    {/* STATUS */}
                    <td className="px-4 py-3.5">
                      <span
                        className={`inline-block px-2.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ${
                          STATUS_BADGES[run.status] || 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {formatStatus(run.status)}
                      </span>
                    </td>

                    {/* RECORDS CHECKED */}
                    <td className="px-4 py-3.5 text-slate-300 font-semibold">
                      {run.records_checked ?? 0}
                    </td>

                    {/* ISSUES DETECTED */}
                    <td className="px-4 py-3.5 text-amber-400 font-semibold">
                      {run.issues_detected ?? 0}
                    </td>

                    {/* FAILED CHECKS */}
                    <td className="px-4 py-3.5 text-slate-400">
                      {run.failed_checks ?? 0}
                    </td>

                    {/* ACTIONS */}
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={() => navigate('/data-quality/issues')}
                        className="px-3 py-1 rounded border border-indigo-500/40 hover:bg-indigo-500/10 text-indigo-400 text-xs font-medium transition-colors"
                      >
                        View Issues
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination matching Screenshot 1 */}
      <div className="flex items-center justify-between pt-1">
        <p className="text-xs text-slate-400">
          Showing {runs.length} of {total} runs
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

export default ReconciliationHistory;
