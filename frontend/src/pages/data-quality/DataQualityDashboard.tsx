import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useNotification } from '../../context/NotificationContext';
import {
  getDataQualityDashboard,
  triggerReconciliation,
} from '../../api/dataQualityApi';
import {
  Refresh as RefreshIcon,
  PlayArrow as PlayIcon,
  WarningAmber as WarningIcon,
  History as HistoryIcon,
  BarChart as BarChartIcon,
  Check as CheckIcon,
  ErrorOutlined as ErrorIcon,
  InfoOutlined as InfoIcon,
  TrendingUp as TrendingUpIcon,
  Shield as ShieldIcon,
  CheckCircleOutlined as HealthIcon,
  ArrowForward as ArrowForwardIcon,
} from '@mui/icons-material';

export const DataQualityDashboard: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { showNotification } = useNotification();

  const { data: dashboard, isLoading, isFetching } = useQuery({
    queryKey: ['data-quality-dashboard'],
    queryFn: getDataQualityDashboard,
    refetchInterval: 30000,
  });

  const reconcileMutation = useMutation({
    mutationFn: triggerReconciliation,
    onSuccess: (res) => {
      showNotification(`Reconciliation completed. Issues detected: ${res.issues_detected ?? 0}`, 'success');
      queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] });
      queryClient.invalidateQueries({ queryKey: ['reconciliation-history'] });
    },
    onError: (err: any) => {
      showNotification(err?.response?.data?.detail || 'Reconciliation failed', 'error');
    },
  });

  const totalChecked = dashboard?.total_records_checked ?? 0;
  const validRecords = dashboard?.valid_records ?? 0;
  const recordsWithWarnings = dashboard?.records_with_warnings ?? 0;
  const recordsWithErrors = dashboard?.records_with_errors ?? 0;
  const unresolvedIssues = dashboard?.unresolved_issues ?? 0;

  const issuesByStatus = dashboard?.issues_by_status || {};
  const totalIssues = Object.values(issuesByStatus).reduce((a, b) => a + b, 0);
  const resolvedIssues = issuesByStatus['RESOLVED'] ?? 0;

  const healthScore = totalChecked > 0
    ? Math.max(0, Math.min(100, Math.round((validRecords / totalChecked) * 100)))
    : 100;

  const lastRunText = dashboard?.last_reconciliation_time
    ? new Date(dashboard.last_reconciliation_time).toLocaleString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      })
    : 'Never';

  const hasWarnings = unresolvedIssues > 0 || recordsWithWarnings > 0 || recordsWithErrors > 0;

  return (
    <div className="space-y-5 text-slate-100">
      {/* Page Header */}
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Data Quality Dashboard</h1>
          <p className="text-xs text-slate-400 mt-1">
            Audit and monitor consistency across sales, stock movements, products, customers, and reports.
          </p>
        </div>

        {/* Action Buttons matching screenshot */}
        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] })}
            disabled={isFetching}
            className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <RefreshIcon style={{ fontSize: 15 }} className={isFetching ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>

          <button
            onClick={() => navigate('/data-quality/issues')}
            className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <span className="flex items-center justify-center w-3.5 h-3.5 rounded bg-indigo-500/30 text-indigo-300 text-[10px] font-bold">
              !
            </span>
            <span>View Issues ({unresolvedIssues})</span>
          </button>

          <button
            onClick={() => navigate('/data-quality/reconciliation')}
            className="px-3 py-1.5 rounded-lg border border-slate-700/70 bg-slate-800/50 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 transition-colors"
          >
            <HistoryIcon style={{ fontSize: 15 }} />
            <span>History</span>
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

      {/* SYSTEM HEALTH SUMMARY Banner */}
      <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                SYSTEM HEALTH SUMMARY
              </span>
              <span
                className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${
                  hasWarnings
                    ? 'bg-amber-500/10 text-amber-400 border-amber-500/20'
                    : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                }`}
              >
                {hasWarnings ? 'Warnings Detected' : 'All Checks Passed'}
              </span>
            </div>
            <p className="text-xs text-slate-300 mt-2">
              {validRecords} of {totalChecked} records validated successfully.
            </p>
          </div>

          <div className="sm:text-right">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              Health Score
            </p>
            <p className="text-2xl font-bold text-amber-400 mt-0.5">
              {isLoading ? '...' : `${healthScore}%`}
            </p>
            <div className="w-48 h-2 bg-slate-800 rounded-full overflow-hidden mt-1.5 sm:ml-auto">
              <div
                className={`h-full transition-all duration-500 ${
                  healthScore >= 90
                    ? 'bg-emerald-500'
                    : healthScore >= 70
                    ? 'bg-amber-500'
                    : 'bg-red-500'
                }`}
                style={{ width: `${healthScore}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* 8 KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: TOTAL RECORDS CHECKED */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              TOTAL RECORDS CHECKED
            </p>
            <div className="w-8 h-8 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
              <BarChartIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-white">
              {isLoading ? '...' : totalChecked}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Last run: {lastRunText}
            </p>
          </div>
        </div>

        {/* Card 2: VALID RECORDS */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              VALID RECORDS
            </p>
            <div className="w-8 h-8 rounded-lg bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
              <CheckIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-emerald-400">
              {isLoading ? '...' : validRecords}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Passed all integrity rules
            </p>
          </div>
        </div>

        {/* Card 3: RECORDS WITH WARNINGS */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              RECORDS WITH WARNINGS
            </p>
            <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
              <WarningIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-amber-400">
              {isLoading ? '...' : recordsWithWarnings}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Open issues pending review
            </p>
          </div>
        </div>

        {/* Card 4: RECORDS WITH ERRORS */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              RECORDS WITH ERRORS
            </p>
            <div className="w-8 h-8 rounded-lg bg-rose-500/20 text-rose-400 flex items-center justify-center">
              <ErrorIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-white">
              {isLoading ? '...' : recordsWithErrors}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Issues actively investigating
            </p>
          </div>
        </div>

        {/* Card 5: UNRESOLVED ISSUES */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              UNRESOLVED ISSUES
            </p>
            <div className="w-8 h-8 rounded-lg bg-orange-500/20 text-orange-400 flex items-center justify-center">
              <InfoIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-amber-400">
              {isLoading ? '...' : unresolvedIssues}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Requiring administrative attention
            </p>
          </div>
        </div>

        {/* Card 6: TOTAL ISSUES DETECTED */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              TOTAL ISSUES DETECTED
            </p>
            <div className="w-8 h-8 rounded-lg bg-purple-500/20 text-purple-400 flex items-center justify-center">
              <TrendingUpIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-purple-400">
              {isLoading ? '...' : totalIssues}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Historical anomalies found
            </p>
          </div>
        </div>

        {/* Card 7: RESOLVED ISSUES */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              RESOLVED ISSUES
            </p>
            <div className="w-8 h-8 rounded-lg bg-teal-500/20 text-teal-400 flex items-center justify-center">
              <ShieldIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-teal-400">
              {isLoading ? '...' : resolvedIssues}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Marked resolved or cleared
            </p>
          </div>
        </div>

        {/* Card 8: DATA HEALTH SCORE */}
        <div className="bg-slate-900/90 rounded-xl border border-slate-800/80 p-5 shadow-sm flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              DATA HEALTH SCORE
            </p>
            <div className="w-8 h-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center">
              <HealthIcon style={{ fontSize: 18 }} />
            </div>
          </div>
          <div className="mt-2">
            <p className="text-3xl font-bold text-amber-400">
              {isLoading ? '...' : `${healthScore}%`}
            </p>
            <p className="text-[11px] text-slate-500 mt-3">
              Clean & consistent records ratio
            </p>
          </div>
        </div>
      </div>

      {/* Bottom 2 Action Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-1">
        {/* Card 1: Quality Issues Center */}
        <div
          onClick={() => navigate('/data-quality/issues')}
          className="bg-slate-900/90 hover:bg-slate-900 rounded-xl border border-slate-800/80 hover:border-slate-700/80 p-5 flex items-center justify-between cursor-pointer transition-all group shadow-sm"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 group-hover:bg-indigo-500/20 transition-colors shrink-0">
              <WarningIcon style={{ fontSize: 20 }} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white group-hover:text-indigo-300 transition-colors">
                Quality Issues Center
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                Inspect, filter, update resolution notes, and resolve data anomalies.
              </p>
            </div>
          </div>
          <ArrowForwardIcon className="text-slate-500 group-hover:text-white group-hover:translate-x-0.5 transition-all shrink-0 ml-3" style={{ fontSize: 18 }} />
        </div>

        {/* Card 2: Reconciliation History & Audit */}
        <div
          onClick={() => navigate('/data-quality/reconciliation')}
          className="bg-slate-900/90 hover:bg-slate-900 rounded-xl border border-slate-800/80 hover:border-slate-700/80 p-5 flex items-center justify-between cursor-pointer transition-all group shadow-sm"
        >
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 group-hover:bg-emerald-500/20 transition-colors shrink-0">
              <HistoryIcon style={{ fontSize: 20 }} />
            </div>
            <div>
              <p className="text-sm font-semibold text-white group-hover:text-emerald-300 transition-colors">
                Reconciliation History & Audit
              </p>
              <p className="text-xs text-slate-400 mt-0.5">
                View previous check execution logs, records processed, and duration.
              </p>
            </div>
          </div>
          <ArrowForwardIcon className="text-slate-500 group-hover:text-white group-hover:translate-x-0.5 transition-all shrink-0 ml-3" style={{ fontSize: 18 }} />
        </div>
      </div>
    </div>
  );
};

export default DataQualityDashboard;
