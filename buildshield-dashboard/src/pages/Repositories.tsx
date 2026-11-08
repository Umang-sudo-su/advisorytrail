import { useState } from 'react';
import { Search, Plus, GitBranch } from 'lucide-react';
import { getRepositories } from '../api';
import { useFetch } from '../useFetch';
import type { Repository } from '../types';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

function RepoList({ repos, query }: { repos: Repository[]; query: string }) {
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
              <GitBranch size={16} aria-hidden="true" />
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
            <button type="button" className="btn">
              <Plus size={16} aria-hidden="true" />
              Trigger Local Scan
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function Repositories() {
  const { state, retry } = useFetch(getRepositories);
  const [query, setQuery] = useState('');

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
        <button type="button" className="btn btn-primary">
          <Plus size={18} aria-hidden="true" />
          Connect GitHub Repository
        </button>
      </div>

      {state.status === 'loading' && <Loading label="Loading repositories" />}
      {state.status === 'error' && <ErrorState message={state.message} onRetry={retry} />}
      {state.status === 'success' && <RepoList repos={state.data} query={query} />}
    </>
  );
}
