import { useState } from 'react';
import { getFindings } from '../api';
import { useFetch } from '../useFetch';
import type { Severity, ReviewStatus } from '../types';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

const changeFilters: { key: string; label: string }[] = [
  { key: 'new', label: 'New in PR' },
  { key: 'existing', label: 'Existing' },
  { key: 'resolved', label: 'Resolved' },
  { key: 'unknown', label: 'Unknown' },
];

const severityFilters: { key: Severity; label: string }[] = [
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
];

const reviewOptions: { key: ReviewStatus; label: string }[] = [
  { key: 'open', label: 'Open' },
  { key: 'dismissed', label: 'Dismissed - Risk Accepted' },
  { key: 'false_positive', label: 'False Positive' },
];

const changeLabel: Record<string, string> = {
  new: 'NEW',
  existing: 'EXISTING',
  resolved: 'RESOLVED',
  unknown: 'UNKNOWN',
};

const severityRank: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

function FindingDetail({
  finding,
  review,
  onReview,
}: {
  finding: any;
  review: ReviewStatus;
  onReview: (status: ReviewStatus) => void;
}) {
  return (
    <div className="detail">
      <h3>Deterministic Priority Reason</h3>
      <p>{finding.priorityReason || 'Vulnerable package version detected by scanner engine.'}</p>

      <h3>Traceable Source Evidence</h3>
      <dl className="evidence">
        <dt>Scanner</dt>
        <dd>{finding.scanner}</dd>
        <dt>File</dt>
        <dd>{finding.filePath}</dd>
        <dt>Primary Advisory</dt>
        <dd>
          <a
            href={`https://github.com/advisories/${finding.advisoryId}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {finding.advisoryId}
          </a>
        </dd>
        <dt>Total Advisories</dt>
        <dd>{finding.advisoryCount} vulnerability advisories merged</dd>
      </dl>

      <h3>Remediation Diff</h3>
      {finding.fixedVersion ? (
        <div className="diff">
          <div className="diff-line diff-remove">
            - {finding.packageName}=={finding.currentVersion}
          </div>
          <div className="diff-line diff-add">
            + {finding.packageName}=={finding.fixedVersion}
          </div>
        </div>
      ) : (
        <p className="muted">No fixed version is available yet.</p>
      )}

      <h3>Human Review Status</h3>
      <div className="pills" role="group" aria-label="Human review status">
        {reviewOptions.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className="pill"
            aria-pressed={review === key}
            onClick={() => onReview(key)}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

function FindingsView({ findings }: { findings: any[] }) {
  const [change, setChange] = useState<string>('new');
  const [activeSeverities, setActiveSeverities] = useState<Severity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, ReviewStatus>>({});

  const map = new Map<string, any>();

  findings.forEach((f) => {
    let details = f.details;
    if (typeof details === 'string') {
      try { details = JSON.parse(details); } catch (e) { details = {}; }
    }
    details = details || {};

    const pkgName = f.package_name || 'unknown';
    const pkgVer = f.package_version || '0.0.0';
    const key = `${pkgName}@${pkgVer}`;
    const sev = (f.severity || 'low').toLowerCase();

    if (!map.has(key)) {
      map.set(key, {
        id: String(f.id),
        change: 'new',
        severity: sev,
        packageName: pkgName,
        currentVersion: pkgVer,
        fixedVersion: details.fixed_version || null,
        priorityReason: details.summary || null,
        scanner: details.ecosystem || 'osv-scanner',
        filePath: 'N/A',
        advisoryId: f.osv_id || 'UNKNOWN',
        advisoryCount: 1,
        reviewStatus: (f.status || 'open').toLowerCase() as ReviewStatus,
      });
    } else {
      const existing = map.get(key);
      existing.advisoryCount += 1;
      if ((severityRank[sev] ?? 99) < (severityRank[existing.severity] ?? 99)) {
        existing.severity = sev;
        existing.advisoryId = f.osv_id || existing.advisoryId;
      }
    }
  });

  const normalizedFindings = Array.from(map.values());

  const countFor = (c: string) => normalizedFindings.filter((f) => f.change === c).length;

  const shown = normalizedFindings
    .filter(
      (f) =>
        f.change === change &&
        (activeSeverities.length === 0 || activeSeverities.includes(f.severity as Severity)),
    )
    .sort((a, b) => (severityRank[a.severity] ?? 99) - (severityRank[b.severity] ?? 99));

  const selected = shown.find((f) => f.id === selectedId) ?? shown[0];

  const toggleSeverity = (s: Severity) => {
    setActiveSeverities((current) =>
      current.includes(s) ? current.filter((x) => x !== s) : [...current, s],
    );
  };

  return (
    <>
      <section className="filter-panel" aria-label="Filters">
        <div>
          <h2 className="filter-title">Change Relationship</h2>
          <div className="pills" role="group" aria-label="Filter by change relationship">
            {changeFilters.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className="pill"
                aria-pressed={change === key}
                onClick={() => setChange(key)}
              >
                {label} ({countFor(key)})
              </button>
            ))}
          </div>
        </div>

        <div>
          <h2 className="filter-title">Severity</h2>
          <div className="pills" role="group" aria-label="Filter by severity">
            {severityFilters.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className="pill"
                aria-pressed={activeSeverities.includes(key)}
                onClick={() => toggleSeverity(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="split">
        <section className="panel" aria-labelledby="list-title">
          <h2 id="list-title" className="section-title">
            Normalized Dependency Findings ({shown.length} unique packages)
          </h2>
          {shown.length === 0 ? (
            <EmptyState
              title="No findings match these filters"
              hint="Try another change relationship or clear the severity filters."
            />
          ) : (
            <ul className="finding-list">
              {shown.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="finding-row"
                    aria-pressed={selected?.id === f.id}
                    onClick={() => setSelectedId(f.id)}
                  >
                    <span>
                      <strong>{f.packageName}</strong> ({f.currentVersion} {'->'} Fixed: {f.fixedVersion ?? 'none yet'})
                    </span>
                    <span className="row-badges">
                      <span className={`badge badge-${f.change}`}>{changeLabel[f.change]}</span>
                      <span className={`badge badge-${f.severity}`}>{f.severity.toUpperCase()}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel" aria-labelledby="detail-title">
          <h2 id="detail-title" className="section-title">
            Finding Detail &amp; Evidence Inspector
          </h2>
          {selected ? (
            <FindingDetail
              finding={selected}
              review={reviews[selected.id] ?? selected.reviewStatus}
              onReview={(status) => setReviews((current) => ({ ...current, [selected.id]: status }))}
            />
          ) : (
            <EmptyState title="No finding selected" hint="Pick a finding from the list to see its evidence." />
          )}
        </section>
      </div>
    </>
  );
}

export default function Findings() {
  const { state, retry } = useFetch(getFindings, { pollMs: 10000 });

  if (state.status === 'loading') return <Loading label="Loading findings" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  if (state.data.length === 0) {
    return <EmptyState title="No findings yet" hint="Findings appear here after a scan finds a vulnerable dependency." />;
  }
  return <FindingsView findings={state.data} />;
}
