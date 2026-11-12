import { useMemo, useState } from 'react';
import { Search } from 'lucide-react';
import { bulkUpdateFindingStatus, getFindings, updateFindingStatus } from '../api';
import { useFetch } from '../useFetch';
import type { Severity, ReviewStatus } from '../types';
import { Loading, ErrorState, EmptyState } from '../components/PageState';
import { cachedPrefs } from '../prefs';

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

const reviewLabel: Record<ReviewStatus, string> = {
  open: 'Open',
  dismissed: 'Dismissed',
  false_positive: 'False positive',
};

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

type Advisory = {
  id: string;
  advisoryId: string;
  summary: string;
  severity: Severity;
  status: ReviewStatus;
};

type FindingGroup = {
  id: string;
  change: string;
  severity: Severity;
  packageName: string;
  currentVersion: string;
  fixedVersion: string | null;
  priorityReason: string | null;
  scanner: string;
  advisories: Advisory[];
  reviewStatus: ReviewStatus;
};

function groupReviewStatus(advisories: Advisory[], reviews: Record<string, ReviewStatus>): ReviewStatus {
  const statuses = advisories.map((a) => reviews[a.id] ?? a.status);
  if (statuses.every((s) => s === 'dismissed')) return 'dismissed';
  if (statuses.every((s) => s === 'false_positive')) return 'false_positive';
  return 'open';
}

function AdvisoryRow({
  advisory,
  review,
  busy,
  onReview,
}: {
  advisory: Advisory;
  review: ReviewStatus;
  busy: boolean;
  onReview: (status: ReviewStatus) => void;
}) {
  return (
    <li className="advisory-item">
      <div className="advisory-head">
        <a
          href={`https://github.com/advisories/${advisory.advisoryId}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          {advisory.advisoryId}
        </a>
        <span className={`badge badge-${advisory.severity}`}>
          {advisory.severity.toUpperCase()}
        </span>
        <span className="badge badge-muted">{reviewLabel[review]}</span>
      </div>
      <p className="advisory-summary">{advisory.summary || 'No advisory summary provided.'}</p>
      <div className="pills" role="group" aria-label={`Review status for ${advisory.advisoryId}`}>
        {reviewOptions.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            className="pill"
            aria-pressed={review === key}
            disabled={busy}
            onClick={() => onReview(key)}
          >
            {label}
          </button>
        ))}
      </div>
    </li>
  );
}

function FindingDetail({
  group,
  reviews,
  busyId,
  bulkBusy,
  error,
  onReview,
  onBulkReview,
}: {
  group: FindingGroup;
  reviews: Record<string, ReviewStatus>;
  busyId: string | null;
  bulkBusy: boolean;
  error: string;
  onReview: (advisoryId: string, status: ReviewStatus) => void;
  onBulkReview: (status: ReviewStatus) => void;
}) {
  return (
    <div className="detail">
      <h3>Deterministic Priority Reason</h3>
      <p>{group.priorityReason || 'Vulnerable package version detected by scanner engine.'}</p>

      <h3>Traceable Source Evidence</h3>
      <dl className="evidence">
        <dt>Scanner</dt>
        <dd>{group.scanner}</dd>
        <dt>File</dt>
        <dd>root manifest</dd>
        <dt>Advisories</dt>
        <dd>{group.advisories.length} affecting this version</dd>
      </dl>

      <h3>Remediation Diff</h3>
      {group.fixedVersion ? (
        <div className="diff">
          <div className="diff-line diff-remove">
            - {group.packageName}=={group.currentVersion}
          </div>
          <div className="diff-line diff-add">
            + {group.packageName}=={group.fixedVersion}
          </div>
        </div>
      ) : (
        <p className="muted">No fixed version is available yet.</p>
      )}

      <h3>Advisories &amp; Review</h3>
      <p className="muted">
        Each advisory is reviewed on its own; dismissing one leaves the others open.
      </p>
      {group.advisories.length > 1 && (
        <div className="bulk-review">
          <span className="muted">Set all {group.advisories.length} advisories:</span>
          <div className="pills" role="group" aria-label="Bulk review status for this package">
            {reviewOptions.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                className="pill"
                disabled={bulkBusy}
                onClick={() => onBulkReview(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {bulkBusy && <span className="muted" role="status">Saving…</span>}
        </div>
      )}
      <ul className="advisory-list">
        {group.advisories.map((advisory) => (
          <AdvisoryRow
            key={advisory.id}
            advisory={advisory}
            review={reviews[advisory.id] ?? advisory.status}
            busy={busyId === advisory.id}
            onReview={(status) => onReview(advisory.id, status)}
          />
        ))}
      </ul>

      {error && (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

function FindingsView({ findings, onReviewed }: { findings: any[]; onReviewed: () => void }) {
  const [change, setChange] = useState<string>('new');
  const [activeSeverities, setActiveSeverities] = useState<Severity[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [reviews, setReviews] = useState<Record<string, ReviewStatus>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [reviewError, setReviewError] = useState('');
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const pageSize = cachedPrefs().page_size;

  // Rebuilding this map parses every finding's JSON details, so it must not run on
  // each keystroke in the search box or each filter click.
  const groups = useMemo<FindingGroup[]>(() => {
    const map = new Map<string, FindingGroup>();

    findings.forEach((f) => {
      let details = f.details;
      if (typeof details === 'string') {
        try { details = JSON.parse(details); } catch { details = {}; }
      }
      details = details || {};

      const pkgName = f.package_name || 'unknown';
      const pkgVer = f.package_version || '0.0.0';
      const key = `${pkgName}@${pkgVer}`;
      const severity = String(f.severity || 'low').toLowerCase() as Severity;
      const status = String(f.status || 'open').toLowerCase() as ReviewStatus;

      const advisory: Advisory = {
        id: String(f.id),
        advisoryId: f.osv_id || 'UNKNOWN',
        summary: details.summary || '',
        severity,
        status,
      };

      const existing = map.get(key);
      if (!existing) {
        map.set(key, {
          id: String(f.id),
          change: 'new',
          severity,
          packageName: pkgName,
          currentVersion: pkgVer,
          fixedVersion: details.fixed_version || null,
          priorityReason: advisory.summary || null,
          scanner: details.ecosystem || 'osv-scanner',
          advisories: [advisory],
          reviewStatus: status,
        });
        return;
      }

      existing.advisories.push(advisory);
      if ((severityRank[severity] ?? 99) < (severityRank[existing.severity] ?? 99)) {
        existing.severity = severity;
        existing.priorityReason = advisory.summary || existing.priorityReason;
      }
      if (!existing.fixedVersion && details.fixed_version) {
        existing.fixedVersion = details.fixed_version;
      }
    });

    return Array.from(map.values()).map((group) => ({
      ...group,
      reviewStatus: groupReviewStatus(group.advisories, reviews),
    }));
  }, [findings, reviews]);

  const countFor = (c: string) => groups.filter((f) => f.change === c).length;

  // Reviews are persisted per advisory; the local map only makes the click instant.
  const handleReview = async (findingId: string, status: ReviewStatus) => {
    const previous = reviews[findingId] ?? 'open';
    const apiStatus = status.toUpperCase() as 'OPEN' | 'DISMISSED' | 'FALSE_POSITIVE';

    setReviews((current) => ({ ...current, [findingId]: status }));
    setBusyId(findingId);
    setReviewError('');
    try {
      await updateFindingStatus(findingId, apiStatus);
      onReviewed();
    } catch (error) {
      setReviews((current) => ({ ...current, [findingId]: previous }));
      setReviewError(error instanceof Error ? error.message : 'Could not save the review.');
    } finally {
      setBusyId(null);
    }
  };

  // One request updates every advisory of the selected package.
  const handleBulkReview = async (group: FindingGroup, status: ReviewStatus) => {
    const ids = group.advisories.map((advisory) => advisory.id);
    const previous: Record<string, ReviewStatus> = {};
    group.advisories.forEach((advisory) => {
      previous[advisory.id] = reviews[advisory.id] ?? advisory.status;
    });

    setReviews((current) => {
      const next = { ...current };
      ids.forEach((id) => { next[id] = status; });
      return next;
    });
    setBulkBusy(true);
    setReviewError('');
    try {
      await bulkUpdateFindingStatus(ids, status.toUpperCase() as 'OPEN' | 'DISMISSED' | 'FALSE_POSITIVE');
      onReviewed();
    } catch (error) {
      setReviews((current) => ({ ...current, ...previous }));
      setReviewError(error instanceof Error ? error.message : 'Could not save the bulk review.');
    } finally {
      setBulkBusy(false);
    }
  };

  const needle = query.trim().toLowerCase();
  const matchesQuery = (group: FindingGroup) =>
    needle === '' ||
    [
      group.packageName,
      group.currentVersion,
      group.fixedVersion ?? '',
      group.severity,
      ...group.advisories.map((a) => `${a.advisoryId} ${a.summary}`),
    ]
      .join(' ')
      .toLowerCase()
      .includes(needle);

  const shown = groups
    .filter(
      (f) =>
        f.change === change &&
        matchesQuery(f) &&
        (activeSeverities.length === 0 || activeSeverities.includes(f.severity)),
    )
    .sort((a, b) => (severityRank[a.severity] ?? 99) - (severityRank[b.severity] ?? 99));

  // The default page size from Settings truncates the list, with an explicit way to see everything.
  const visible = showAll ? shown : shown.slice(0, pageSize);
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
        <section className="panel findings-list-panel" aria-labelledby="list-title">
          <div className="panel-head">
            <h2 id="list-title" className="section-title">
              Normalized Dependency Findings ({shown.length} unique packages)
            </h2>
            <label className="search-box">
              <Search size={15} aria-hidden="true" />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search package or advisory"
                aria-label="Search findings by package, version or advisory"
              />
            </label>
          </div>
          {shown.length === 0 ? (
            <EmptyState
              title="No findings match these filters"
              hint="Try another change relationship or clear the severity filters."
            />
          ) : (
            <ul className="finding-list">
              {visible.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="finding-row"
                    aria-pressed={selected?.id === f.id}
                    onClick={() => setSelectedId(f.id)}
                  >
                    <span className="finding-main">
                      <strong>{f.packageName}</strong>
                      <span className="finding-meta">
                        {f.currentVersion} {'->'} fixed: {f.fixedVersion ?? 'none yet'} ·{' '}
                        {f.advisories.length} advisor{f.advisories.length === 1 ? 'y' : 'ies'}
                      </span>
                    </span>
                    <span className="row-badges">
                      <span className={`badge badge-${f.change}`}>{changeLabel[f.change]}</span>
                      <span className={`badge badge-${f.severity}`}>{f.severity.toUpperCase()}</span>
                      {f.reviewStatus !== 'open' && (
                        <span className="badge badge-muted">{reviewLabel[f.reviewStatus]}</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {shown.length > pageSize && (
            <button type="button" className="btn btn-ghost" onClick={() => setShowAll((current) => !current)}>
              {showAll ? 'Show fewer findings' : `Show all ${shown.length} findings`}
            </button>
          )}
        </section>

        <section className="panel findings-detail-panel" aria-labelledby="detail-title">
          <h2 id="detail-title" className="section-title">
            Finding Detail &amp; Evidence Inspector
          </h2>
          {selected ? (
            <FindingDetail
              group={selected}
              reviews={reviews}
              busyId={busyId}
              bulkBusy={bulkBusy}
              error={reviewError}
              onReview={(advisoryId, status) => void handleReview(advisoryId, status)}
              onBulkReview={(status) => void handleBulkReview(selected, status)}
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
  const { state, retry, refresh } = useFetch(getFindings, { pollMs: 30000 });

  if (state.status === 'loading') return <Loading label="Loading findings" />;
  if (state.status === 'error') return <ErrorState message={state.message} onRetry={retry} />;
  if (state.data.length === 0) {
    return <EmptyState title="No findings yet" hint="Findings appear here after a scan finds a vulnerable dependency." />;
  }
  // Reviews refresh quietly: a spinner here would remount the view and drop the selection.
  return <FindingsView findings={state.data} onReviewed={refresh} />;
}
