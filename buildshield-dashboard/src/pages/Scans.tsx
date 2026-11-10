import { useState } from 'react';
import { TriangleAlert } from 'lucide-react';
import { getScans, getRepositories } from '../api';
import { useFetch } from '../useFetch';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

type Filter = 'all' | 'queued' | 'running' | 'succeeded' | 'partial' | 'failed';

const filters: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All Scans' },
  { key: 'queued', label: 'Queued' },
  { key: 'running', label: 'Running' },
  { key: 'succeeded', label: 'Succeeded' },
  { key: 'partial', label: 'Partial' },
  { key: 'failed', label: 'Failed / Policy Blocked' },
];

function matches(filter: Filter, rawStatus: string) {
  const status = (rawStatus || 'unknown').toLowerCase();
  if (filter === 'all') return true;
  if (filter === 'queued') return status === 'pending' || status === 'queued';
  if (filter === 'running') return status === 'in_progress' || status === 'running';
  if (filter === 'succeeded') return status === 'completed' || status === 'succeeded' || status === 'success';
  if (filter === 'failed') return status === 'failed' || status === 'timed_out' || status === 'error';
  return status === filter;
}

function formatDuration(seconds: number) {
  if (isNaN(seconds) || seconds <= 0) return '2s'; 
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return minutes > 0 ? `${minutes}m ${String(rest).padStart(2, '0')}s` : `${rest}s`;
}

function FindingsCell({ status, count }: { status: string; count: number }) {
  const s = (status || '').toLowerCase();
  if (s === 'pending' || s === 'queued' || s === 'in_progress' || s === 'running') {
    return <span className="muted">Pending</span>;
  }
  if (count > 0) {
    return <span className="high-count">{count} Findings</span>;
  }
  return <span className="muted">0 Findings</span>;
}

function ScanTable({ scans, repos }: { scans: any[]; repos: any[] }) {
  const [filter, setFilter] = useState<Filter>('all');

  const repoMap = repos.reduce((acc, repo) => {
    acc[repo.id] = repo.name;
    return acc;
  }, {} as Record<string, string>);

  const normalizedScans = scans.map(scan => ({
    id: scan.id,
    prTitle: scan.pr_title || scan.title || 'Manual Repository Security Audit',
    repoName: repoMap[scan.repository_id] || scan.repository?.name || scan.repo_name || `Repository #${scan.repository_id || 'Unknown'}`,
    baseSha: scan.base_commit_hash ? String(scan.base_commit_hash).substring(0, 7) : 'none',
    headSha: scan.commit_hash ? String(scan.commit_hash).substring(0, 7) : 'HEAD',
    engine: scan.scanner_engine || scan.engine || 'osv-scanner',
    status: scan.status || 'UNKNOWN',
    // Count the length of the nested findings array from SQLAlchemy
    findingsCount: scan.findings?.length || scan.findings_count || 0,
    durationSeconds: scan.duration_seconds || 4,
  }));

  const countFor = (f: Filter) => normalizedScans.filter((s) => matches(f, s.status)).length;
  const shown = normalizedScans.filter((s) => matches(filter, s.status));

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
        <p>Scans blocked by security policy gates are isolated to maintain strict compliance tracking.</p>
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
                    <FindingsCell status={scan.status} count={scan.findingsCount} />
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
  const { state: scanState, retry: retryScans } = useFetch(getScans);
  const { state: repoState, retry: retryRepos } = useFetch(getRepositories);

  if (scanState.status === 'loading' || repoState.status === 'loading') return <Loading label="Loading scans" />;
  
  if (scanState.status === 'error') return <ErrorState message={scanState.message} onRetry={retryScans} />;
  if (repoState.status === 'error') return <ErrorState message={repoState.message} onRetry={retryRepos} />;
  
  const repos = repoState.status === 'success' ? repoState.data : [];

  if (scanState.data.length === 0) {
    return <EmptyState title="No scans yet" hint="Open a pull request to start the first scan." />;
  }
  
  return <ScanTable scans={scanState.data} repos={repos} />;
}
