import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../../context/AuthContext';
import { useNotification } from '../../context/NotificationContext';
import { getDataQualityIssue, updateDataQualityIssueStatus } from '../../api/dataQualityApi';
import { ArrowBack as ArrowBackIcon, Save as SaveIcon } from '@mui/icons-material';

const inputClass =
  'bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-800 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 outline-none transition-all';

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

  const { data: issue, isLoading } = useQuery({
    queryKey: ['data-quality-issue', effectiveId],
    queryFn: () => getDataQualityIssue(effectiveId!),
    enabled: !!effectiveId,
  });

  React.useEffect(() => {
    if (issue?.status) {
      setStatus(issue.status);
    }
  }, [issue?.status]);

  const updateMutation = useMutation({
    mutationFn: () => updateDataQualityIssueStatus(effectiveId!, { status, resolution_note: resolutionNote }),
    onSuccess: () => {
      showNotification('Issue status updated', 'success');
      queryClient.invalidateQueries({ queryKey: ['data-quality-issue', effectiveId] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-issues'] });
      queryClient.invalidateQueries({ queryKey: ['data-quality-dashboard'] });
    },
    onError: (err: any) => {
      showNotification(err?.response?.data?.detail || 'Failed to update issue', 'error');
    },
  });

  if (isLoading) {
    return <div className="p-8 text-center text-slate-500">Loading...</div>;
  }

  if (!issue) {
    return <div className="p-8 text-center text-slate-500">Issue not found</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/data-quality')} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg">
          <ArrowBackIcon />
        </button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Issue Details</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Issue ID: {issue.id}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Issue Information</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-slate-500 dark:text-slate-400">Type</p>
              <p className="text-slate-900 dark:text-white mt-1">{issue.issue_type.replace(/_/g, ' ')}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Severity</p>
              <div className="mt-1">
                <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${SEVERITY_COLORS[issue.severity] || 'bg-slate-100 text-slate-700'}`}>
                  {issue.severity}
                </span>
              </div>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Module</p>
              <p className="text-slate-900 dark:text-white mt-1 font-medium">{issue.affected_module}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Status</p>
              <div className="mt-1">
                <span className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${STATUS_COLORS[issue.status] || 'bg-slate-100 text-slate-700'}`}>
                  {issue.status}
                </span>
              </div>
            </div>
            <div className="col-span-2">
              <p className="text-slate-500 dark:text-slate-400">Affected Record</p>
              <p className="text-slate-900 dark:text-white mt-1 font-mono text-xs">{issue.affected_record_id || '-'}</p>
            </div>
            <div className="col-span-2">
              <p className="text-slate-500 dark:text-slate-400">Description</p>
              <p className="text-slate-900 dark:text-white mt-1">{issue.description}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Detected At</p>
              <p className="text-slate-900 dark:text-white mt-1">{new Date(issue.detected_at).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-slate-500 dark:text-slate-400">Resolved At</p>
              <p className="text-slate-900 dark:text-white mt-1">{issue.resolved_at ? new Date(issue.resolved_at).toLocaleString() : '-'}</p>
            </div>
            {issue.resolved_by_name && (
              <div>
                <p className="text-slate-500 dark:text-slate-400">Resolved By</p>
                <p className="text-slate-900 dark:text-white mt-1">{issue.resolved_by_name}</p>
              </div>
            )}
            {issue.resolution_note && (
              <div className="col-span-2">
                <p className="text-slate-500 dark:text-slate-400">Resolution Note</p>
                <p className="text-slate-900 dark:text-white mt-1">{issue.resolution_note}</p>
              </div>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 space-y-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-white">Details</h3>
          <pre className="bg-slate-50 dark:bg-slate-950 p-4 rounded-lg text-xs overflow-auto max-h-96 text-slate-700 dark:text-slate-300">
            {JSON.stringify(issue.details, null, 2)}
          </pre>

          {isAdmin && (
            <div className="space-y-4 pt-4 border-t border-slate-200 dark:border-slate-800">
              <h4 className="font-medium text-slate-900 dark:text-white">Update Status</h4>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass + ' w-full'}>
                <option value="OPEN">Open</option>
                <option value="INVESTIGATING">Investigating</option>
                <option value="RESOLVED">Resolved</option>
                <option value="IGNORED">Ignored</option>
              </select>
              <textarea
                placeholder="Resolution note (optional)"
                value={resolutionNote}
                onChange={(e) => setResolutionNote(e.target.value)}
                className={inputClass + ' w-full h-24'}
              />
              <button
                onClick={() => updateMutation.mutate()}
                disabled={updateMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-medium disabled:opacity-50"
              >
                <SaveIcon style={{ fontSize: 18 }} />
                {updateMutation.isPending ? 'Updating...' : 'Update Status'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default DataQualityIssueDetail;
