import { useState } from 'react';
import { getFindings } from '../api';
import { useFetch } from '../useFetch';
import type { Finding, ChangeType, Severity, ReviewStatus } from '../types';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

const changeFilters: { key: ChangeType; label: string }[] = [
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

const changeLabel: Record<ChangeType, string> = {
  new: 'NEW',
  existing: 'EXISTING',
  resolved: 'RESOLVED',
  unknown: 'UNKNOWN',
};

const severityRank: Record<Severity, number> = {
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
  finding: Finding;
  review: ReviewStatus;
  onReview: (status: ReviewStatus) => void;
}) {
  return (
    <div className="detail">
      <h3>Deterministic Priority Reason</h3>
      <p>{finding.priorityReason}</p>

      <h3>Traceable Source Evidence</h3>
      <dl className="evidence">
        <dt>Scanner</dt>
        <dd>{finding.scanner}</dd>
        <dt>File</dt>
        <dd>{finding.filePath}</dd>
        <dt>Advisory</dt>
        <dd>
          <a
            href={`https://github.com/advisories/${finding.advisoryId}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            {finding.advisoryId}
          </a>
        </dd>
        <dt>Fingerprint</dt>
        <dd>{finding.fingerprint}</dd>
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

function FindingsView({ findings }: { findings: Finding[] }) {
  const [change, setChange] = useState<ChangeType>('new');
  const [activeSeverities, setActiveSeverities] = useState<Severity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, ReviewStatus>>({});

  const countFor = (c: ChangeType) => findings.filter((f) => f.change === c).length;

  const shown = findings
    .filter(
      (f) =>
        f.change === change &&
        (activeSeverities.length === 0 || activeSeverities.includes(f.severity)),
    )
    .sort((a, b) => severityRank[a.severity] - severityRank[b.severity]);

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
            Normalized Dependency Findings
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
                      {f.packageName} ({f.currentVersion} {'->'} Fixed: {f.fixedVersion ?? 'none yet'})
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
  const { state, retry } = useFetch(getFindings);

  if (state.status === 'loading') return <Loading label="Loading findings" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  if (state.data.length === 0) {
    return <EmptyState title="No findings yet" hint="Findings appear here after a scan finds a vulnerable dependency." />;
  }
  return <FindingsView findings={state.data} />;
}