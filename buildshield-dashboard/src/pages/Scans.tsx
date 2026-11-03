import { useState } from 'react';
import { TriangleAlert } from 'lucide-react';
import { getScans } from '../api';
import { useFetch } from '../useFetch';
import type { Scan, ScanStatus } from '../types';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

type Filter = 'all' | 'queued' | 'running' | 'succeeded' | 'partial' | 'failed';

const filters: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All Scans' },
  { key: 'queued', label: 'Queued' },
  { key: 'running', label: 'Running' },
  { key: 'succeeded', label: 'Succeeded' },
  { key: 'partial', label: 'Partial' },
  { key: 'failed', label: 'Failed / Timed Out' },
];

function matches(filter: Filter, status: ScanStatus) {
  if (filter === 'all') return true;
  if (filter === 'failed') return status === 'failed' || status === 'timed_out';
  return status === filter;
}

function formatDuration(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return minutes > 0 ? `${minutes}m ${String(rest).padStart(2, '0')}s` : `${rest}s`;
}

function FindingsCell({ scan }: { scan: Scan }) {
  if (scan.status === 'failed' || scan.status === 'timed_out') {
    return <span className="badge badge-incomplete">Incomplete</span>;
  }
  if (scan.status === 'queued' || scan.status === 'running') {
    return <span className="muted">Pending</span>;
  }
  if (scan.highCount > 0) {
    return <span className="high-count">{scan.highCount} High</span>;
  }
  return <span className="muted">0 Findings</span>;
}

function ScanTable({ scans }: { scans: Scan[] }) {
  const [filter, setFilter] = useState<Filter>('all');

  const countFor = (f: Filter) => scans.filter((s) => matches(f, s.status)).length;
  const shown = scans.filter((s) => matches(filter, s.status));

  return (
    <>
      <div className="pills" role="group" aria-label="Filter scans by status">
        {filters.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className="pill"
            aria-pressed={filter === key}
            onClick={() => setFilter(key)}
          >
            {label} ({countFor(key)})
          </button>
        ))}
      </div>

      <div className="banner-warn" role="note">
        <TriangleAlert size={22} aria-hidden="true" />
        <p>Failed or incomplete scans are isolated from clean scans so errors are never mistaken for clean results</p>
      </div>

      <h2 className="section-title">Scan Executions</h2>

      {shown.length === 0 ? (
        <EmptyState title="No scans with this status" hint="Choose another filter to see more scans." />
      ) : (
        <div className="table-wrap">
          <table className="table" aria-label="Scan executions">
            <thead>
              <tr>
                <th scope="col">Scan ID</th>
                <th scope="col">Repository &amp; PR</th>
                <th scope="col">Base vs Head SHA</th>
                <th scope="col">Scanner Engine</th>
                <th scope="col">Status</th>
                <th scope="col">Findings</th>
                <th scope="col">Duration</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((scan) => (
                <tr key={scan.id}>
                  <td>{scan.id}</td>
                  <td>
                    <strong>{scan.prTitle}</strong>
                    <br />
                    <span className="muted">{scan.repoName}</span>
                  </td>
                  <td>
                    <code className="chip">
                      {scan.baseSha} {'->'} {scan.headSha}
                    </code>
                  </td>
                  <td>
                    <span className="chip">{scan.engine}</span>
                  </td>
                  <td>
                    <StatusBadge status={scan.status} />
                  </td>
                  <td>
                    <FindingsCell scan={scan} />
                  </td>
                  <td>{formatDuration(scan.durationSeconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export default function Scans() {
  const { state, retry } = useFetch(getScans);

  if (state.status === 'loading') return <Loading label="Loading scans" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  if (state.data.length === 0) {
    return <EmptyState title="No scans yet" hint="Open a pull request to start the first scan." />;
  }
  return <ScanTable scans={state.data} />;
}