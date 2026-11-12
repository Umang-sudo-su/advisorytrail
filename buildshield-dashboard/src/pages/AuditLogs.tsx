import { useEffect, useState } from 'react';
import { Download, History, Search, ShieldCheck, TriangleAlert } from 'lucide-react';
import {
  exportAuditLogs,
  getAuditLogs,
  getAuditMonitorStats,
  type AuditLogEntry,
  type AuditMonitorStats,
} from '../api';
import { Loading, ErrorState, EmptyState } from '../components/PageState';
import { cachedPrefs, formatDateTime } from '../prefs';
import './AuditLogs.css';

const categories = [
  'All Events',
  'Finding Reviews & Dismissals',
  'GitHub Webhooks',
  'Policy Changes',
  'Settings',
  'Tenant Access',
];

type LogState =
  | { status: 'loading'; logs: AuditLogEntry[] }
  | { status: 'success'; logs: AuditLogEntry[] }
  | { status: 'error'; logs: AuditLogEntry[]; message: string };

function formatTimestamp(value: string) {
  // Honours the date, time and time-zone preferences saved in Settings.
  return formatDateTime(value, { seconds: true });
}

function actionTone(action: string) {
  const value = action.toUpperCase();
  if (value.includes('DISMISS') || value.includes('FALSE_POSITIVE') || value.includes('FINDING_STATUS')) {
    return 'badge-bad';
  }
  if (value.includes('WEBHOOK')) return 'badge-primary';
  if (value.includes('POLICY')) return 'badge-warn';
  if (value.includes('SCAN') || value.includes('REPO')) return 'badge-queued';
  return 'badge-muted';
}

export default function AuditLogs() {
  const [category, setCategory] = useState('All Events');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [state, setState] = useState<LogState>({ status: 'loading', logs: [] });
  const [reloadKey, setReloadKey] = useState(0);
  const [monitor, setMonitor] = useState<AuditMonitorStats | null>(null);
  const [exporting, setExporting] = useState<'csv' | 'json' | null>(null);
  const [exportError, setExportError] = useState('');
  const [pageSize] = useState(() => cachedPrefs().page_size);

  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;

    getAuditLogs({ category, search, limit: pageSize })
      .then((logs) => {
        if (!cancelled) setState({ status: 'success', logs });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          status: 'error',
          logs: [],
          message: error instanceof Error ? error.message : 'Could not load the audit trail.',
        });
      });

    return () => {
      cancelled = true;
    };
  }, [category, search, reloadKey, pageSize]);

  useEffect(() => {
    let cancelled = false;
    getAuditMonitorStats()
      .then((stats) => {
        if (!cancelled) setMonitor(stats);
      })
      .catch(() => {
        if (!cancelled) setMonitor(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const download = async (format: 'csv' | 'json') => {
    setExportError('');
    setExporting(format);
    try {
      const { blob, filename } = await exportAuditLogs(format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Export failed.');
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="audit-page">
      <section className="panel audit-filter" aria-label="Audit filters">
        <div className="audit-filter-row">
          <div className="pills" role="group" aria-label="Filter by event category">
            {categories.map((item) => (
              <button
                key={item}
                type="button"
                className="pill"
                aria-pressed={category === item}
                onClick={() => setCategory(item)}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="audit-tools">
            <label className="search">
              <Search size={17} aria-hidden="true" />
              <input
                type="search"
                placeholder="Search actor, action or resource"
                aria-label="Search audit trail"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => download('csv')}
              disabled={exporting !== null}
            >
              <Download size={16} aria-hidden="true" />
              {exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => download('json')}
              disabled={exporting !== null}
            >
              {exporting === 'json' ? 'Exporting…' : 'JSON'}
            </button>
          </div>
        </div>

        {exportError && (
          <p className="audit-error" role="alert">
            <TriangleAlert size={15} aria-hidden="true" />
            {exportError}
          </p>
        )}
      </section>

      <section className="panel monitor" aria-labelledby="monitor-title">
        <div className="monitor-heading">
          <span className="settings-icon" aria-hidden="true">
            <ShieldCheck size={18} />
          </span>
          <h2 id="monitor-title">Webhook Idempotency &amp; Security Monitor</h2>
        </div>

        <div className="monitor-stats">
          <span>
            Verified Signatures:{' '}
            <span className="badge badge-ok">
              {monitor?.verified_signatures_percentage ?? '—'}
            </span>
          </span>
          <span>
            Deduplicated Delivery IDs:{' '}
            <strong>{monitor ? monitor.deduplicated_delivery_ids.toLocaleString() : '—'}</strong>
          </span>
        </div>
      </section>

      <section className="panel" aria-labelledby="trail-title">
        <div className="panel-head">
          <h2 id="trail-title" className="section-title">
            Chronological Audit Trail
          </h2>
          {state.status === 'success' && (
            <span className="chip">
              {state.logs.length} {state.logs.length === 1 ? 'event' : 'events'}
            </span>
          )}
        </div>

        {state.status === 'loading' && <Loading label="Loading audit trail" />}

        {state.status === 'error' && (
          <ErrorState message={state.message} onRetry={() => setReloadKey((key) => key + 1)} />
        )}

        {state.status === 'success' && state.logs.length === 0 && (
          <EmptyState
            title="No audit events yet"
            hint="Finding reviews, webhook deliveries and scan triggers appear here."
          />
        )}

        {state.status === 'success' && state.logs.length > 0 && (
          <div className="table-wrap">
            <table className="table audit-table">
              <thead>
                <tr>
                  <th scope="col">Timestamp</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Action</th>
                  <th scope="col">Resource ID</th>
                  <th scope="col">Justification</th>
                </tr>
              </thead>
              <tbody>
                {state.logs.map((log) => (
                  <tr key={log.id}>
                    <td className="audit-time">{formatTimestamp(log.timestamp)}</td>
                    <td className="audit-actor">{log.actor}</td>
                    <td className="audit-action">
                      <span className={`badge ${actionTone(log.action)}`}>{log.action}</span>
                    </td>
                    <td className="audit-resource">{log.resource_id}</td>
                    <td className="audit-justification">{log.justification || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="audit-note">
        <History size={13} aria-hidden="true" />
        Showing the latest {state.logs.length || 50} events{category === 'All Events' ? '' : ` in ${category}`}.
      </p>
    </div>
  );
}
