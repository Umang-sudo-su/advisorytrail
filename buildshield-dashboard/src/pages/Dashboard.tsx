import type { ReactNode } from 'react';
import { LoaderCircle, TriangleAlert, CircleCheck, GitPullRequest } from 'lucide-react';
import { getDashboard } from '../api';
import { useFetch } from '../useFetch';
import type { DashboardData, Severity, TrendPoint } from '../types';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

const severityOrder: { key: Severity; label: string }[] = [
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
];

function scoreClass(score: number) {
  if (score >= 90) return 'badge-ok';
  if (score >= 80) return 'badge-warn';
  return 'badge-bad';
}

function StatCard({
  title,
  value,
  tone,
  children,
}: {
  title: string;
  value: number;
  tone: 'plain' | 'danger' | 'success' | 'warn';
  children: ReactNode;
}) {
  return (
    <div className={`stat stat-${tone}`}>
      <p className="stat-title">{title}</p>
      <p className="stat-value">{value}</p>
      <div className="stat-note">{children}</div>
    </div>
  );
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const width = 400;
  const height = 170;
  const pad = 28;

  const scores = points.map((p) => p.score);
  const min = Math.min(...scores) - 5;
  const max = Math.max(...scores) + 5;
  const step = points.length > 1 ? (width - pad * 2) / (points.length - 1) : 0;

  const coords = points.map((p, i) => ({
    x: pad + i * step,
    y: height - pad - ((p.score - min) / (max - min)) * (height - pad * 2),
    ...p,
  }));

  const summary = points.map((p) => `${p.month} ${p.score}`).join(', ');

  return (
    <svg
      className="trend"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Repository health score by month: ${summary}`}
    >
      <polyline
        points={coords.map((c) => `${c.x},${c.y}`).join(' ')}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="3"
      />
      {coords.map((c) => (
        <g key={c.month}>
          <circle cx={c.x} cy={c.y} r="5" fill="var(--primary)" />
          <text x={c.x} y={height - 6} textAnchor="middle" fontSize="13" fill="var(--muted)">
            {c.month}
          </text>
        </g>
      ))}
    </svg>
  );
}

function DashboardView({ data }: { data: DashboardData }) {
  const maxSeverity = Math.max(...Object.values(data.severity), 1);

  return (
    <>
      <section className="stat-grid" aria-label="Scan summary">
        <StatCard title="Active PR Scans" value={data.activeScans} tone="plain">
          <LoaderCircle size={18} className="spin" aria-hidden="true" />
          Running
        </StatCard>
        <StatCard title="New PR Vulnerabilities" value={data.newHighCritical} tone="danger">
          <TriangleAlert size={18} aria-hidden="true" />
          High/Critical
        </StatCard>
        <StatCard title="Clean PRs" value={data.cleanPrs} tone="success">
          <CircleCheck size={18} aria-hidden="true" />
          Success
        </StatCard>
        <StatCard title="Failed / Incomplete Scans" value={data.failedScans} tone="warn">
          <TriangleAlert size={18} aria-hidden="true" />
          Needs Attention
        </StatCard>
      </section>

      <div className="split">
        <section className="panel" aria-labelledby="queue-title">
          <h2 id="queue-title" className="section-title">
            Live Pull Request Scan Queue
          </h2>
          {data.queue.length === 0 ? (
            <EmptyState title="No scans in the queue" hint="New pull requests appear here when they are scanned." />
          ) : (
            <ul className="queue">
              {data.queue.map((item) => {
                const bad = item.status === 'failed' || item.status === 'timed_out';
                return (
                  <li key={item.id} className="queue-row">
                    <GitPullRequest size={20} aria-hidden="true" />
                    <div className="queue-title">
                      <strong>
                        PR #{item.prNumber}: {item.title}
                      </strong>
                      <span className="muted">{item.repoName}</span>
                    </div>
                    <code className="chip">{item.sha}</code>
                    <StatusBadge status={item.status} />
                    <div
                      className="progress"
                      role="progressbar"
                      aria-label={`PR #${item.prNumber} scan progress`}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={item.progress}
                    >
                      <div
                        className={bad ? 'progress-fill progress-bad' : 'progress-fill'}
                        style={{ width: `${item.progress}%` }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section className="panel" aria-labelledby="health-title">
          <h2 id="health-title" className="section-title">
            Recent Repository Health &amp; Findings Breakdown
          </h2>

          <h3 className="sub-title">Health trends</h3>
          <TrendChart points={data.healthTrend} />

          <h3 className="sub-title">Severity breakdown</h3>
          <ul className="bars">
            {severityOrder.map(({ key, label }) => (
              <li key={key} className="bar-row">
                <span className="bar-label">{label}</span>
                <div className="bar-track">
                  <div
                    className={`bar-fill bar-${key}`}
                    style={{ width: `${(data.severity[key] / maxSeverity) * 100}%` }}
                  />
                </div>
                <span className="bar-count">{data.severity[key]}</span>
              </li>
            ))}
          </ul>

          <h3 className="sub-title">Recently scanned repositories</h3>
          <ul className="repo-scores">
            {data.recentRepos.map((repo) => (
              <li key={repo.name}>
                <span>{repo.name}</span>
                <span className={`badge ${scoreClass(repo.score)}`}>{repo.score.toFixed(1)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}

export default function Dashboard() {
  const { state, retry } = useFetch(getDashboard);

  if (state.status === 'loading') return <Loading label="Loading dashboard" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  return <DashboardView data={state.data} />;
}