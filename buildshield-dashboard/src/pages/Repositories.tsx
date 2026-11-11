import { useEffect, useState } from 'react';
import { Search, Plus, GitBranch, X, Play } from 'lucide-react';
import { getRepositories, addRepository, triggerScan, getScan } from '../api';
import { useFetch } from '../useFetch';
import type { Repository } from '../types';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

const FINISHED_STATUSES = new Set([
  'completed',
  'succeeded',
  'success',
  'failed',
  'timed_out',
  'error',
  'partial',
]);

function RepoList({
  repos,
  query,
  onScan,
  scanning,
  scanErrors,
}: {
  repos: Repository[];
  query: string;
  onScan: (id: string | number) => void;
  scanning: Record<string, number>;
  scanErrors: Record<string, string>;
}) {
  if (repos.length === 0) {
    return (
      <EmptyState
        title="No repositories connected yet"
        hint="Connect a GitHub repository to start scanning."
      />
    );
  }

  const shown = repos.filter((repo) =>
    repo.name.toLowerCase().includes(query.trim().toLowerCase()),
  );

  if (shown.length === 0) {
    return <EmptyState title="No repositories match your search" hint="Try a different name." />;
  }

  return (
    <ul className="grid">
      {shown.map((repo) => (
        <li key={repo.id} className="card">
          <div className="card-head">
            <h2>{repo.name}</h2>
            <span className="badge badge-ok">Installed</span>
          </div>

          <div className="card-row">
            <span className="chip">
              <GitBranch size={15} aria-hidden="true" />
              {repo.branch || 'main'}
            </span>
            <div>
              <p className="label">Manifest</p>
              <div className="chips">
                {(repo.manifests || []).length > 0 ? (
                  (repo.manifests || []).map((file) => (
                    <span key={file} className="chip">
                      {file}
                    </span>
                  ))
                ) : (
                  <span className="chip muted" style={{ opacity: 0.7 }}>None</span>
                )}
              </div>
            </div>
          </div>

          <div className="card-foot">
            <div>
              <p className="label">Latest scan</p>
              <StatusBadge status={repo.latestScanStatus || 'unknown'} />
            </div>
            {scanning[String(repo.id)] ? (
              <button type="button" className="scan-btn is-scanning" disabled aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                Scanning
              </button>
            ) : (
              <button type="button" className="scan-btn" onClick={() => onScan(repo.id)}>
                <Play size={15} aria-hidden="true" />
                Trigger Local Scan
              </button>
            )}
            {scanErrors[String(repo.id)] && (
              <p className="scan-error" role="alert">
                {scanErrors[String(repo.id)]}
              </p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function Repositories() {
  const { state, retry } = useFetch(getRepositories, { pollMs: 30000 });
  const [query, setQuery] = useState('');

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRepo, setNewRepo] = useState({ name: '', url: '', branch: 'main' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  // repository id -> scan id currently running from this page
  const [scanning, setScanning] = useState<Record<string, number>>({});
  const [scanErrors, setScanErrors] = useState<Record<string, string>>({});
  const watching = Object.values(scanning).join(',');

  // The scan runs in the background, so the card keeps watching it until the
  // backend reports a finished status, then the button comes back.
  useEffect(() => {
    if (!watching) return;
    let cancelled = false;

    const check = async () => {
      await Promise.all(
        Object.entries(scanning).map(async ([repoId, scanId]) => {
          try {
            const scan = await getScan(scanId);
            if (cancelled || !FINISHED_STATUSES.has(String(scan.status).toLowerCase())) return;
            setScanning((current) => {
              if (!(repoId in current)) return current;
              const next = { ...current };
              delete next[repoId];
              return next;
            });
            retry();
          } catch {
            // A transient error must not clear the spinner; try again on the next tick.
          }
        }),
      );
    };

    void check();
    const timer = window.setInterval(check, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [watching, retry]);

  const handleAddRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setSubmitError('');
    try {
      await addRepository(newRepo);
      setIsModalOpen(false);
      setNewRepo({ name: '', url: '', branch: 'main' });
      retry();
    } catch (err: any) {
      setSubmitError(err.message || 'Failed to add repository');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTriggerScan = async (repoId: string | number) => {
    const key = String(repoId);
    setScanErrors((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });

    try {
      const scan = await triggerScan(repoId);
      if (scan?.id) {
        setScanning((current) => ({ ...current, [key]: scan.id }));
      }
      retry();
    } catch (err: any) {
      setScanErrors((current) => ({ ...current, [key]: err?.message || 'Failed to trigger scan' }));
    }
  };

  return (
    <>
      <div className="toolbar">
        <label className="search">
          <Search size={18} aria-hidden="true" />
          <input
            type="search"
            placeholder="Search repositories..."
            aria-label="Search repositories"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <button type="button" className="btn btn-primary" onClick={() => setIsModalOpen(true)}>
          <Plus size={17} aria-hidden="true" />
          Connect GitHub Repository
        </button>
      </div>

      {state.status === 'loading' && <Loading label="Loading repositories" />}
      {state.status === 'error' && <ErrorState message={state.message} onRetry={retry} />}
      {state.status === 'success' && (
        <RepoList
          repos={state.data}
          query={query}
          onScan={handleTriggerScan}
          scanning={scanning}
          scanErrors={scanErrors}
        />
      )}

      {isModalOpen && (
        <div className="modal-backdrop">
          <div className="modal" role="dialog" aria-modal="true" aria-labelledby="connect-repo-title">
            <div className="modal-head">
              <h2 id="connect-repo-title">Connect Repository</h2>
              <button
                type="button"
                className="modal-close"
                onClick={() => setIsModalOpen(false)}
                aria-label="Close dialog"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            {submitError && (
              <div className="modal-error" role="alert">
                {submitError}
              </div>
            )}

            <form onSubmit={handleAddRepo} className="modal-form">
              <div className="form-field">
                <label className="form-label" htmlFor="repo-name">Repository Name</label>
                <input
                  id="repo-name"
                  className="form-input"
                  type="text"
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({ ...newRepo, name: e.target.value })}
                  placeholder="e.g. buildshield-api"
                  required
                />
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="repo-url">GitHub URL</label>
                <input
                  id="repo-url"
                  className="form-input"
                  type="url"
                  value={newRepo.url}
                  onChange={(e) => setNewRepo({ ...newRepo, url: e.target.value })}
                  placeholder="https://github.com/user/repo"
                  required
                />
              </div>
              <div className="form-field">
                <label className="form-label" htmlFor="repo-branch">Branch</label>
                <input
                  id="repo-branch"
                  className="form-input"
                  type="text"
                  value={newRepo.branch}
                  onChange={(e) => setNewRepo({ ...newRepo, branch: e.target.value })}
                  placeholder="main"
                  required
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-ghost" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                  {isSubmitting ? 'Connecting...' : 'Connect'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
