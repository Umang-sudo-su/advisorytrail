import { useEffect, useRef, useState } from 'react';
import { AuthProvider, useAuth } from './AuthContext';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import Repositories from './pages/Repositories';
import Scans from './pages/Scans';
import Findings from './pages/Findings';
import Policies from './pages/Policies';
import AuditLogs from './pages/AuditLogs';
import Settings from './pages/Settings';
import {
  LayoutDashboard,
  GitBranch,
  ShieldAlert,
  FileText,
  ShieldCheck,
  Settings as SettingsIcon,
  History,
  LogOut,
  LoaderCircle,
} from 'lucide-react';
import { applyTheme, loadSettings, watchSystemTheme } from './settings';
import { applyAppearance, cachedPrefs, setCachedPrefs } from './prefs';
import { getSettings } from './api';

const tabs = [
  { key: 'dashboard', label: 'Dashboard', hint: 'Overview & live queue', icon: LayoutDashboard },
  { key: 'repositories', label: 'Repositories', hint: 'Connected GitHub repositories', icon: GitBranch },
  { key: 'scans', label: 'Scans', hint: 'Scan lifecycle & history', icon: ShieldAlert },
  { key: 'findings', label: 'Findings', hint: 'Vulnerabilities & evidence', icon: FileText },
  { key: 'policies', label: 'Policies', hint: 'Risk rules & check preview', icon: ShieldCheck },
  { key: 'audit', label: 'Audit Logs', hint: 'Activity & webhook history', icon: History },
  { key: 'settings', label: 'Settings', hint: 'Preferences & connection', icon: SettingsIcon },
] as const;

type TabKey = (typeof tabs)[number]['key'];

function AppContent() {
  const { token, user, initializing, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<TabKey>('dashboard');
  const landingApplied = useRef(false);

  // Apply the saved palette for logged-out and logged-in states alike.
  useEffect(() => {
    const mode = loadSettings().theme;
    applyTheme(mode);
    applyAppearance(cachedPrefs());
    return watchSystemTheme(mode);
  }, []);

  // Personal preferences load once the session validates: landing page, density, motion.
  useEffect(() => {
    if (!token) {
      landingApplied.current = false;
      return;
    }
    if (!user || landingApplied.current) return;
    landingApplied.current = true;

    getSettings()
      .then((settings) => {
        setCachedPrefs(settings.user);
        applyAppearance(settings.user);
        setActiveTab(settings.user.landing_page);
      })
      .catch(() => {
        // Preferences are optional; the default landing page stays in place.
      });
  }, [token, user]);

  if (initializing) {
    return (
      <div className="boot-screen">
        <div>
          <LoaderCircle size={22} className="spin" aria-hidden="true" />
          Restoring your session…
        </div>
      </div>
    );
  }

  if (!token) {
    return <Login />;
  }

  const active = tabs.find((tab) => tab.key === activeTab) ?? tabs[0];
  const initials = (user?.username || user?.email || 'B').slice(0, 1).toUpperCase();
  const isSettings = activeTab === 'settings';

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-plate">
            <img src="/assets/logo-sidebar.png" alt="BuildShield" className="brand-logo" />
          </span>
        </div>

        <nav className="sidebar-nav" aria-label="Main">
          {tabs
            .filter((tab) => tab.key !== 'settings')
            .map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                className="nav-link"
                aria-current={activeTab === key ? 'page' : undefined}
                onClick={() => setActiveTab(key)}
              >
                <span className="nav-icon">
                  <Icon size={19} aria-hidden="true" />
                </span>
                <span>{label}</span>
              </button>
            ))}
        </nav>

        <div className="sidebar-footer">
          <button
            type="button"
            className="nav-link settings-trigger"
            aria-current={isSettings ? 'page' : undefined}
            onClick={() => setActiveTab('settings')}
          >
            <span className="nav-icon">
              <SettingsIcon size={19} aria-hidden="true" />
            </span>
            <span>Settings</span>
          </button>

          <div className="user-chip">
            <span className="avatar" aria-hidden="true">{initials}</span>
            <span className="user-meta">
              <strong>{user?.username ?? 'Signed in'}</strong>
              <small>{user?.email ?? 'BuildShield session'}</small>
            </span>
          </div>

          <button type="button" className="logout-btn" onClick={logout}>
            <LogOut size={17} aria-hidden="true" />
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div>
            <p className="topbar-eyebrow">{active.hint}</p>
            <h1>{active.label}</h1>
          </div>
          <span className="topbar-chip">osv-scanner engine</span>
        </header>

        <main className="content">
          {activeTab === 'dashboard' && <Dashboard />}
          {activeTab === 'repositories' && <Repositories />}
          {activeTab === 'scans' && <Scans />}
          {activeTab === 'findings' && <Findings />}
          {activeTab === 'policies' && <Policies />}
          {activeTab === 'audit' && <AuditLogs />}
          {activeTab === 'settings' && <Settings />}
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
