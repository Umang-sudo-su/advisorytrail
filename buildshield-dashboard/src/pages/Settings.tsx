import { useEffect, useState } from 'react';
import { Check, Download, LogOut, Palette, Server, TriangleAlert, User } from 'lucide-react';
import { useAuth } from '../AuthContext';
import { exportAuditLogs, getHealth } from '../api';
import {
  applyTheme,
  DEFAULT_API_BASE,
  DEFAULT_COMMIT_REF,
  defaultSettings,
  loadSettings,
  saveSettings,
  watchSystemTheme,
  type AppSettings,
  type ThemeMode,
} from '../settings';
import './Settings.css';

const themes: { key: ThemeMode; label: string }[] = [
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
  { key: 'system', label: 'System' },
];

type HealthState =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'ok'; detail: string }
  | { state: 'error'; detail: string };

export default function Settings() {
  const { user, remember, setRemember, logout } = useAuth();

  const [settings, setSettings] = useState<AppSettings>(() => loadSettings());
  const [apiDraft, setApiDraft] = useState(() => settings.apiBaseUrl);
  const [refDraft, setRefDraft] = useState(() => settings.defaultCommitRef);
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<HealthState>({ state: 'idle' });
  const [exporting, setExporting] = useState<'csv' | 'json' | null>(null);
  const [exportError, setExportError] = useState('');

  useEffect(() => {
    applyTheme(settings.theme);
    return watchSystemTheme(settings.theme);
  }, [settings.theme]);

  useEffect(() => {
    if (!saved) return;
    const timer = setTimeout(() => setSaved(false), 2500);
    return () => clearTimeout(timer);
  }, [saved]);

  const persist = (next: AppSettings) => {
    setSettings(next);
    saveSettings(next);
    setSaved(true);
  };

  const changeTheme = (theme: ThemeMode) => persist({ ...settings, theme });

  const saveConnection = () => {
    const apiBaseUrl = apiDraft.trim().replace(/\/$/, '') || DEFAULT_API_BASE;
    const defaultCommitRef = refDraft.trim() || DEFAULT_COMMIT_REF;
    persist({ ...settings, apiBaseUrl, defaultCommitRef });
    setApiDraft(apiBaseUrl);
    setRefDraft(defaultCommitRef);
    setHealth({ state: 'idle' });
  };

  const resetConnection = () => {
    setApiDraft(defaultSettings().apiBaseUrl);
    setRefDraft(DEFAULT_COMMIT_REF);
    setHealth({ state: 'idle' });
  };

  const checkHealth = async () => {
    setHealth({ state: 'checking' });
    try {
      const result = await getHealth();
      setHealth({
        state: 'ok',
        detail: `${result.status}${result.database ? ` · database ${result.database}` : ''}`,
      });
    } catch (error) {
      setHealth({
        state: 'error',
        detail: error instanceof Error ? error.message : 'Health check failed.',
      });
    }
  };

  const downloadAudit = async (format: 'csv' | 'json') => {
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
    <div className="settings-page">
      <div className="settings-grid">
        <section className="settings-card" aria-labelledby="appearance-title">
          <div className="settings-head">
            <span className="settings-icon" aria-hidden="true"><Palette size={18} /></span>
            <div>
              <h2 id="appearance-title">Appearance</h2>
              <p>Choose how BuildShield looks on this device.</p>
            </div>
          </div>

          <div className="segmented" role="group" aria-label="Colour theme">
            {themes.map(({ key, label }) => (
              <button
                key={key}
                type="button"
                aria-pressed={settings.theme === key}
                onClick={() => changeTheme(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <p className="settings-note">
            Dark mode reuses the same teal palette on deep surfaces. System follows your OS setting.
          </p>
        </section>

        <section className="settings-card" aria-labelledby="account-title">
          <div className="settings-head">
            <span className="settings-icon" aria-hidden="true"><User size={18} /></span>
            <div>
              <h2 id="account-title">Account</h2>
              <p>Identity attached to this session.</p>
            </div>
          </div>

          <dl className="settings-list">
            <div>
              <dt>Username</dt>
              <dd>{user?.username ?? '—'}</dd>
            </div>
            <div>
              <dt>Email</dt>
              <dd>{user?.email ?? '—'}</dd>
            </div>
            <div>
              <dt>Status</dt>
              <dd><span className="badge badge-ok">Active</span></dd>
            </div>
          </dl>

          <div className="setting-row">
            <span className="setting-copy">
              <strong>Keep me signed in</strong>
              <small>Store the token on this device instead of only this tab.</small>
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={remember}
              aria-label="Keep me signed in"
              className="switch"
              onClick={() => setRemember(!remember)}
            >
              <span className="switch-knob" />
            </button>
          </div>
        </section>

        <section className="settings-card" aria-labelledby="api-title">
          <div className="settings-head">
            <span className="settings-icon" aria-hidden="true"><Server size={18} /></span>
            <div>
              <h2 id="api-title">API connection</h2>
              <p>Where the dashboard reads repositories, scans and findings.</p>
            </div>
          </div>

          <div className="settings-fields">
            <div className="form-field">
              <label className="form-label" htmlFor="api-base">API base URL</label>
              <input
                id="api-base"
                className="form-input"
                type="url"
                value={apiDraft}
                onChange={(event) => setApiDraft(event.target.value)}
                placeholder="http://localhost:8000"
                spellCheck={false}
              />
            </div>
            <div className="form-field">
              <label className="form-label" htmlFor="commit-ref">Default commit ref for scans</label>
              <input
                id="commit-ref"
                className="form-input"
                type="text"
                value={refDraft}
                onChange={(event) => setRefDraft(event.target.value)}
                placeholder="HEAD"
                spellCheck={false}
              />
            </div>
          </div>

          <div className="settings-actions">
            <button type="button" className="btn btn-primary" onClick={saveConnection}>
              Save connection
            </button>
            <button type="button" className="btn btn-ghost" onClick={resetConnection}>
              Reset defaults
            </button>
            <button
              type="button"
              className="btn"
              onClick={checkHealth}
              disabled={health.state === 'checking'}
            >
              {health.state === 'checking' ? 'Checking…' : 'Test connection'}
            </button>
          </div>

          {health.state === 'ok' && (
            <p className="settings-feedback settings-ok" role="status">
              <Check size={14} aria-hidden="true" /> API healthy — {health.detail}
            </p>
          )}
          {health.state === 'error' && (
            <p className="settings-feedback settings-error" role="alert">
              <TriangleAlert size={14} aria-hidden="true" /> {health.detail}
            </p>
          )}
        </section>

        <section className="settings-card" aria-labelledby="export-title">
          <div className="settings-head">
            <span className="settings-icon" aria-hidden="true"><Download size={18} /></span>
            <div>
              <h2 id="export-title">Audit export</h2>
              <p>Download the platform audit trail straight from the API.</p>
            </div>
          </div>

          <div className="settings-actions">
            <button type="button" className="btn" onClick={() => downloadAudit('csv')} disabled={exporting !== null}>
              {exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
            </button>
            <button type="button" className="btn" onClick={() => downloadAudit('json')} disabled={exporting !== null}>
              {exporting === 'json' ? 'Exporting…' : 'Export JSON'}
            </button>
          </div>

          {exportError && (
            <p className="settings-feedback settings-error" role="alert">
              <TriangleAlert size={14} aria-hidden="true" /> {exportError}
            </p>
          )}
        </section>
      </div>

      <section className="settings-card settings-card-danger" aria-labelledby="session-title">
        <div className="settings-head">
          <span className="settings-icon" aria-hidden="true"><LogOut size={18} /></span>
          <div>
            <h2 id="session-title">Session</h2>
            <p>Signing out removes the stored token from this browser.</p>
          </div>
        </div>

        <div className="settings-actions">
          <button type="button" className="logout-btn" onClick={logout}>
            <LogOut size={16} aria-hidden="true" />
            <span>Sign out of BuildShield</span>
          </button>
        </div>
      </section>

      <p className="settings-saved" role="status">{saved ? 'Settings saved.' : ''}</p>
    </div>
  );
}
