import { useState } from 'react';
import { Search, Plus, GitBranch, X, Play } from 'lucide-react';
import { getRepositories, addRepository, triggerScan } from '../api';
import { useFetch } from '../useFetch';
import type { Repository } from '../types';
import StatusBadge from '../components/StatusBadge';
import { Loading, ErrorState, EmptyState } from '../components/PageState';

function RepoList({ repos, query, onScan }: { repos: Repository[]; query: string; onScan: (id: string | number) => void }) {
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
            <button 
              type="button" 
              className="btn btn-primary" 
              style={{ backgroundColor: '#2563eb', color: 'white', border: 'none' }}
              onClick={() => onScan(repo.id)}
            >
              <Play size={16} aria-hidden="true" />
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
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newRepo, setNewRepo] = useState({ name: '', url: '', branch: 'main' });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

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
    try {
      await triggerScan(repoId);
      alert('Scan triggered successfully!');
      retry(); // Refresh the data to show updated scan status
    } catch (err: any) {
      // If the schema expected a different payload field, we will see it here
      alert(`Failed to trigger scan: ${err.message}`);
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
          <Plus size={18} aria-hidden="true" />
          Connect GitHub Repository
        </button>
      </div>

      {state.status === 'loading' && <Loading label="Loading repositories" />}
      {state.status === 'error' && <ErrorState message={state.message} onRetry={retry} />}
      {state.status === 'success' && <RepoList repos={state.data} query={query} onScan={handleTriggerScan} />}

      {isModalOpen && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 p-6 rounded-lg shadow-xl w-full max-w-md border border-gray-700">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold text-white m-0">Connect Repository</h2>
              <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-white bg-transparent border-none cursor-pointer">
                <X size={20} />
              </button>
            </div>
            
            {submitError && <div className="bg-red-500/20 text-red-400 p-3 rounded mb-4 text-sm">{submitError}</div>}
            
            <form onSubmit={handleAddRepo} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Repository Name</label>
                <input 
                  type="text" 
                  value={newRepo.name}
                  onChange={(e) => setNewRepo({...newRepo, name: e.target.value})}
                  className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none text-white"
                  placeholder="e.g. buildshield-api"
                  required 
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">GitHub URL</label>
                <input 
                  type="url" 
                  value={newRepo.url}
                  onChange={(e) => setNewRepo({...newRepo, url: e.target.value})}
                  className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none text-white"
                  placeholder="https://github.com/user/repo"
                  required 
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-1 text-gray-300">Branch</label>
                <input 
                  type="text" 
                  value={newRepo.branch}
                  onChange={(e) => setNewRepo({...newRepo, branch: e.target.value})}
                  className="w-full p-2 rounded bg-gray-900 border border-gray-600 focus:border-blue-500 outline-none text-white"
                  placeholder="main"
                  required 
                />
              </div>
              <div className="flex justify-end gap-3 mt-4">
                <button 
                  type="button" 
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 rounded bg-transparent border border-gray-600 text-white hover:bg-gray-700"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={isSubmitting}
                  className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white font-bold disabled:opacity-50"
                >
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
