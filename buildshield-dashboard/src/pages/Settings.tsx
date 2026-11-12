import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import {
  Bell,
  Check,
  GitBranch,
  HelpCircle,
  Info,
  KeyRound,
  LoaderCircle,
  Palette,
  Plus,
  RefreshCw,
  ScanLine,
  Search,
  SlidersHorizontal,
  Trash2,
  TriangleAlert,
  UserRound,
  Users,
} from 'lucide-react';
import {
  changePassword,
  connectGitHub,
  createApiToken,
  createWebhook,
  deleteWebhook,
  disableTwoFactor,
  disconnectGitHub,
  enableTwoFactor,
  getHealth,
  getSessions,
  getSettings,
  getTwoFactorStatus,
  inviteMember,
  removeMember as removeMemberApi,
  revokeApiToken,
  revokeOtherSessions,
  revokeSession,
  runScheduledScansNow,
  saveUserPreferences,
  saveWorkspaceSettings,
  sendTestNotification,
  setupTwoFactor,
  testWebhook,
  updateMemberRole,
  updateWebhook,
  type SessionInfo,
  type TwoFactorSetup,
} from '../api';
import { useAuth } from '../useAuth';
import { ErrorState, Loading } from '../components/PageState';
import { applyAppearance, cachedPrefs, formatDateTime, setCachedPrefs, TIME_ZONES } from '../prefs';
import { applyTheme, loadSettings, saveSettings, watchSystemTheme, type ThemeMode } from '../settings';
import type { ScanConfig, SettingsPayload, UserPreferences } from '../types';
import './Settings.css';

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';
type Tone = 'ok' | 'bad';
type SectionKey =
  | 'general'
  | 'account'
  | 'github'
  | 'scan'
  | 'notifications'
  | 'team'
  | 'appearance'
  | 'api'
  | 'about';

const sections: { key: SectionKey; label: string; hint: string; icon: typeof Bell }[] = [
  { key: 'general', label: 'General', hint: 'Workspace defaults and how BuildShield behaves for you.', icon: SlidersHorizontal },
  { key: 'account', label: 'Account & Login', hint: 'Your identity, password and sign-in security.', icon: UserRound },
  { key: 'github', label: 'GitHub Integration', hint: 'Connection health, repository access and permissions.', icon: GitBranch },
  { key: 'scan', label: 'Scan Configuration', hint: 'When scans run and how much of the server they may use.', icon: ScanLine },
  { key: 'notifications', label: 'Notifications', hint: 'Which events notify you, and where they are delivered.', icon: Bell },
  { key: 'team', label: 'Team & Permissions', hint: 'Workspace membership and role assignments.', icon: Users },
  { key: 'appearance', label: 'Appearance', hint: 'Themes, density and motion for this account.', icon: Palette },
  { key: 'api', label: 'API & Webhooks', hint: 'Programmatic access and outbound event delivery.', icon: KeyRound },
  { key: 'about', label: 'About & Help', hint: 'Version, scanner engine and system status.', icon: Info },
];

const notificationGroups: { title: string; events: { key: string; label: string }[] }[] = [
  {
    title: 'New findings',
    events: [
      { key: 'new_findings_critical', label: 'Critical severity found' },
      { key: 'new_findings_high', label: 'High severity found' },
      { key: 'new_findings_medium', label: 'Medium severity found' },
      { key: 'new_findings_low', label: 'Low severity found' },
    ],
  },
  {
    title: 'Scan status',
    events: [
      { key: 'scan_completed', label: 'Scan completed' },
      { key: 'scan_failed', label: 'Scan failed or timed out' },
      { key: 'scan_partial', label: 'Scan partial or incomplete' },
      { key: 'scan_queued', label: 'Scan queued or started' },
    ],
  },
  {
    title: 'Pull request updates',
    events: [
      { key: 'pr_scan_completed', label: 'Pull-request scan completed' },
      { key: 'pr_result_changed', label: 'Result changed after new commits' },
      { key: 'check_run_updated', label: 'Check run created or updated' },
    ],
  },
  {
    title: 'Integration alerts',
    events: [
      { key: 'github_attention', label: 'GitHub connection needs attention' },
      { key: 'webhook_unhealthy', label: 'Webhook connection unhealthy' },
      { key: 'repo_access_changed', label: 'Repository access changed' },
    ],
  },
  {
    title: 'Team and account alerts',
    events: [
      { key: 'invite_received', label: 'Invitation received' },
      { key: 'member_changed', label: 'Workspace membership changed' },
      { key: 'account_security', label: 'Account security notice' },
    ],
  },
];

const roleLabels: Record<string, string> = {
  owner: 'Owner',
  admin: 'Admin',
  security_analyst: 'Security Analyst',
  developer: 'Developer',
  viewer: 'Viewer',
};

function browserLabel() {
  const agent = navigator.userAgent;
  if (/Edg\//.test(agent)) return 'Microsoft Edge';
  if (/OPR\//.test(agent)) return 'Opera';
  if (/Chrome\//.test(agent)) return 'Google Chrome';
  if (/Firefox\//.test(agent)) return 'Mozilla Firefox';
  if (/Safari\//.test(agent)) return 'Safari';
  return 'This browser';
}

function StatusChip({ status, message, onRetry }: { status: SaveStatus; message?: string; onRetry?: () => void }) {
  if (status === 'idle') return null;
  if (status === 'saving') {
    return (
      <span className="settings-status settings-status-saving" role="status">
        <LoaderCircle size={13} className="spin" aria-hidden="true" /> Saving…
      </span>
    );
  }
  if (status === 'saved') {
    return (
      <span className="settings-status settings-status-saved" role="status">
        <Check size={13} aria-hidden="true" /> Saved
      </span>
    );
  }
  return (
    <span className="settings-status settings-status-error" role="alert">
      Not saved{message ? ` — ${message}` : ''}
      {onRetry && (
        <button type="button" onClick={onRetry}>
          Retry
        </button>
      )}
    </span>
  );
}

function Row({ label, help, control }: { label: string; help?: string; control: ReactNode }) {
  return (
    <div className="settings-row">
      <div className="settings-row-copy">
        <span className="settings-row-label">
          {label}
          {help && <HelpCircle size={13} aria-hidden="true" />}
        </span>
        {help && <span className="settings-row-help">{help}</span>}
      </div>
      <div className="settings-row-control">{control}</div>
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className="switch"
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-knob" />
    </button>
  );
}

function Select({
  value,
  onChange,
  options,
  ariaLabel,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  ariaLabel: string;
  disabled?: boolean;
}) {
  return (
    <select
      className="form-input settings-control-wide"
      aria-label={ariaLabel}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export default function Settings() {
  const { remember, setRemember } = useAuth();

  const [payload, setPayload] = useState<SettingsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [section, setSection] = useState<SectionKey>('general');
  const [query, setQuery] = useState('');

  const [theme, setTheme] = useState<ThemeMode>(() => loadSettings().theme);

  const [nameDraft, setNameDraft] = useState('');
  const [branchesDraft, setBranchesDraft] = useState('');
  const [timeoutDraft, setTimeoutDraft] = useState('600');

  const [prefsStatus, setPrefsStatus] = useState<SaveStatus>('idle');
  const [prefsError, setPrefsError] = useState('');
  const [scanStatus, setScanStatus] = useState<SaveStatus>('idle');
  const [scanError, setScanError] = useState('');
  const [nameStatus, setNameStatus] = useState<SaveStatus>('idle');
  const [nameError, setNameError] = useState('');

  const [pwCurrent, setPwCurrent] = useState('');
  const [pwNew, setPwNew] = useState('');
  const [pwConfirm, setPwConfirm] = useState('');
  const [pwState, setPwState] = useState<{ status: SaveStatus; message: string }>({ status: 'idle', message: '' });

  const [health, setHealth] = useState<{ state: 'idle' | 'checking' | 'ok' | 'error'; detail: string }>({
    state: 'idle',
    detail: '',
  });
  const [testNotice, setTestNotice] = useState<{ tone: Tone; text: string } | null>(null);

  const [memberEmail, setMemberEmail] = useState('');
  const [memberRole, setMemberRole] = useState('developer');
  const [memberNotice, setMemberNotice] = useState<{ tone: Tone; text: string } | null>(null);
  const [memberBusy, setMemberBusy] = useState(false);

  const [tokenName, setTokenName] = useState('');
  const [tokenExpiry, setTokenExpiry] = useState('90');
  const [tokenSecret, setTokenSecret] = useState<string | null>(null);
  const [tokenNotice, setTokenNotice] = useState<{ tone: Tone; text: string } | null>(null);
  const [tokenBusy, setTokenBusy] = useState(false);

  const [webhookName, setWebhookName] = useState('');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookEvents, setWebhookEvents] = useState<string[]>([]);
  const [webhookSecret, setWebhookSecret] = useState<string | null>(null);
  const [webhookNotice, setWebhookNotice] = useState<{ tone: Tone; text: string } | null>(null);
  const [webhookBusy, setWebhookBusy] = useState(false);

  const [copied, setCopied] = useState<string | null>(null);

  const [twoFactor, setTwoFactor] = useState<{ enabled: boolean; recovery: number } | null>(null);
  const [twoFactorSetup, setTwoFactorSetup] = useState<TwoFactorSetup | null>(null);
  const [twoFactorCode, setTwoFactorCode] = useState('');
  const [twoFactorPassword, setTwoFactorPassword] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [twoFactorNotice, setTwoFactorNotice] = useState<{ tone: Tone; text: string } | null>(null);

  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [sessionNotice, setSessionNotice] = useState<{ tone: Tone; text: string } | null>(null);

  const [githubToken, setGithubToken] = useState('');
  const [githubBusy, setGithubBusy] = useState(false);
  const [githubNotice, setGithubNotice] = useState<{ tone: Tone; text: string } | null>(null);

  const [scheduleNotice, setScheduleNotice] = useState<{ tone: Tone; text: string } | null>(null);
  const [tokenScopes, setTokenScopes] = useState('read,write');

  const pendingPrefs = useRef<Partial<UserPreferences>>({});
  const failedPrefs = useRef<Partial<UserPreferences> | null>(null);
  const prefsTimer = useRef<number | null>(null);
  const pendingScan = useRef<Partial<ScanConfig>>({});
  const failedScan = useRef<Partial<ScanConfig> | null>(null);
  const scanTimer = useRef<number | null>(null);

  const browser = useMemo(() => browserLabel(), []);

  const load = useCallback(async () => {
    try {
      const data = await getSettings();
      setLoadError('');
      setPayload(data);
      setCachedPrefs(data.user);
      applyAppearance(data.user);
      setNameDraft(data.workspace.name);
      setBranchesDraft(data.workspace.scan.branches.join(', '));
      setTimeoutDraft(String(data.workspace.scan.timeout_seconds));
      setHealth({ state: 'idle', detail: '' });
      setWebhookEvents((current) =>
        current.length > 0 ? current : data.integrations.webhook_events.map((item) => item.id),
      );

      const [status, sessionList] = await Promise.all([getTwoFactorStatus(), getSessions()]);
      setTwoFactor({ enabled: status.enabled, recovery: status.recovery_codes_remaining });
      setSessions(sessionList);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : 'Could not load settings.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Deferred one microtask so the effect body never triggers a cascading render.
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
    };
  }, [load]);

  useEffect(() => {
    applyTheme(theme);
    return watchSystemTheme(theme);
  }, [theme]);

  const user = payload?.user ?? null;
  const workspace = payload?.workspace ?? null;

  // Warn before leaving with an unsaved workspace draft, since it needs an explicit Save.
  useEffect(() => {
    if (!payload) return;
    const dirty =
      nameDraft.trim() !== payload.workspace.name ||
      branchesDraft.trim() !== payload.workspace.scan.branches.join(', ');
    if (!dirty) return;

    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [branchesDraft, nameDraft, payload]);

  const flushPrefs = useCallback(async () => {
    const patch = pendingPrefs.current;
    if (Object.keys(patch).length === 0) return;
    pendingPrefs.current = {};
    setPrefsStatus('saving');
    setPrefsError('');

    try {
      const result = await saveUserPreferences(patch);
      setPayload((current) => (current ? { ...current, user: result.user } : current));
      setCachedPrefs(result.user);
      applyAppearance(result.user);
      failedPrefs.current = null;
      setPrefsStatus('saved');
    } catch (error) {
      failedPrefs.current = patch;
      setPrefsError(error instanceof Error ? error.message : 'Could not save your preferences.');
      setPrefsStatus('error');
    }
  }, []);

  const updatePrefs = (patch: Partial<UserPreferences>) => {
    setPayload((current) => (current ? { ...current, user: { ...current.user, ...patch } } : current));
    const merged = { ...cachedPrefs(), ...patch };
    setCachedPrefs(merged);
    if (patch.density !== undefined || patch.reduce_motion !== undefined) applyAppearance(merged);

    pendingPrefs.current = { ...pendingPrefs.current, ...patch };
    if (prefsTimer.current) window.clearTimeout(prefsTimer.current);
    prefsTimer.current = window.setTimeout(() => void flushPrefs(), 400);
  };

  const retryPrefs = () => {
    if (!failedPrefs.current) return;
    pendingPrefs.current = failedPrefs.current;
    failedPrefs.current = null;
    void flushPrefs();
  };

  const flushScan = useCallback(async () => {
    const scan = pendingScan.current;
    if (Object.keys(scan).length === 0) return;
    pendingScan.current = {};
    setScanStatus('saving');
    setScanError('');

    try {
      const result = await saveWorkspaceSettings({ scan });
      setPayload((current) => (current ? { ...current, workspace: result.workspace } : current));
      setBranchesDraft(result.workspace.scan.branches.join(', '));
      setTimeoutDraft(String(result.workspace.scan.timeout_seconds));
      failedScan.current = null;
      setScanStatus('saved');
    } catch (error) {
      failedScan.current = scan;
      setScanError(error instanceof Error ? error.message : 'Could not save the scan configuration.');
      setScanStatus('error');
    }
  }, []);

  const updateScan = (patch: Partial<ScanConfig>) => {
    setPayload((current) =>
      current
        ? { ...current, workspace: { ...current.workspace, scan: { ...current.workspace.scan, ...patch } } }
        : current,
    );
    pendingScan.current = { ...pendingScan.current, ...patch };
    if (scanTimer.current) window.clearTimeout(scanTimer.current);
    scanTimer.current = window.setTimeout(() => void flushScan(), 400);
  };

  const retryScan = () => {
    if (!failedScan.current) return;
    pendingScan.current = failedScan.current;
    failedScan.current = null;
    void flushScan();
  };

  const saveName = async (event?: FormEvent) => {
    event?.preventDefault();
    const name = nameDraft.trim();
    if (!name) {
      setNameStatus('error');
      setNameError('Workspace name cannot be empty.');
      return;
    }

    setNameStatus('saving');
    setNameError('');
    try {
      const result = await saveWorkspaceSettings({ name });
      setPayload((current) => (current ? { ...current, workspace: result.workspace } : current));
      setNameDraft(result.workspace.name);
      setNameStatus('saved');
    } catch (error) {
      setNameStatus('error');
      setNameError(error instanceof Error ? error.message : 'Could not save the workspace name.');
    }
  };

  const saveBranches = async () => {
    const branches = branchesDraft
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

    setScanStatus('saving');
    setScanError('');
    try {
      const result = await saveWorkspaceSettings({ scan: { branches } });
      setPayload((current) => (current ? { ...current, workspace: result.workspace } : current));
      setBranchesDraft(result.workspace.scan.branches.join(', '));
      setScanStatus('saved');
    } catch (error) {
      setScanStatus('error');
      setScanError(error instanceof Error ? error.message : 'Could not save the branch patterns.');
    }
  };

  const changeTheme = (next: ThemeMode) => {
    setTheme(next);
    saveSettings({ ...loadSettings(), theme: next });
  };

  const submitPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (pwNew.length < 8) {
      setPwState({ status: 'error', message: 'The new password must be at least 8 characters.' });
      return;
    }
    if (pwNew !== pwConfirm) {
      setPwState({ status: 'error', message: 'The new passwords do not match.' });
      return;
    }

    setPwState({ status: 'saving', message: '' });
    try {
      await changePassword(pwCurrent, pwNew);
      setPwState({
        status: 'saved',
        message: 'Password updated. Previously issued session tokens keep working until they expire.',
      });
      setPwCurrent('');
      setPwNew('');
      setPwConfirm('');
    } catch (error) {
      setPwState({
        status: 'error',
        message: error instanceof Error ? error.message : 'Could not change the password.',
      });
    }
  };

  const submitInvite = async (event: FormEvent) => {
    event.preventDefault();
    if (!memberEmail.trim()) return;

    setMemberBusy(true);
    setMemberNotice(null);
    try {
      const result = await inviteMember(memberEmail.trim(), memberRole);
      setMemberNotice({ tone: 'ok', text: result.note });
      setMemberEmail('');
      await load();
    } catch (error) {
      setMemberNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not invite that member.',
      });
    } finally {
      setMemberBusy(false);
    }
  };

  const changeMemberRole = async (id: number, role: string) => {
    setMemberNotice(null);
    try {
      await updateMemberRole(id, role);
      await load();
    } catch (error) {
      setMemberNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not change that role.',
      });
    }
  };

  const removeMemberById = async (id: number, email: string) => {
    if (!window.confirm(`Remove ${email} from this workspace? Their access ends immediately.`)) return;
    setMemberNotice(null);
    try {
      await removeMemberApi(id);
      setMemberNotice({ tone: 'ok', text: `${email} removed from the workspace.` });
      await load();
    } catch (error) {
      setMemberNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not remove that member.',
      });
    }
  };

  const submitToken = async (event: FormEvent) => {
    event.preventDefault();
    const name = tokenName.trim();
    if (name.length < 2) {
      setTokenNotice({ tone: 'bad', text: 'Give the token a name of at least 2 characters.' });
      return;
    }

    setTokenBusy(true);
    setTokenNotice(null);
    try {
      const result = await createApiToken(
        name,
        tokenExpiry === '0' ? null : Number(tokenExpiry),
        tokenScopes === 'read' ? ['read'] : ['read', 'write'],
      );
      setTokenSecret(result.secret);
      setTokenNotice({ tone: 'ok', text: result.note });
      setTokenName('');
      await load();
    } catch (error) {
      setTokenNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not create the token.',
      });
    } finally {
      setTokenBusy(false);
    }
  };

  const revokeToken = async (id: number, name: string) => {
    if (!window.confirm(`Revoke the API token "${name}"? Requests using it start failing immediately.`)) return;
    try {
      await revokeApiToken(id);
      setTokenNotice({ tone: 'ok', text: `Token "${name}" revoked.` });
      await load();
    } catch (error) {
      setTokenNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not revoke the token.',
      });
    }
  };

  const toggleWebhookEvent = (id: string) => {
    setWebhookEvents((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  const submitWebhook = async (event: FormEvent) => {
    event.preventDefault();
    if (webhookName.trim().length < 2) {
      setWebhookNotice({ tone: 'bad', text: 'Give the endpoint a name of at least 2 characters.' });
      return;
    }
    if (!/^https?:\/\//i.test(webhookUrl.trim())) {
      setWebhookNotice({ tone: 'bad', text: 'The destination must be an absolute http(s) URL.' });
      return;
    }

    setWebhookBusy(true);
    setWebhookNotice(null);
    try {
      const result = await createWebhook(webhookName.trim(), webhookUrl.trim(), webhookEvents);
      setWebhookSecret(result.secret);
      setWebhookNotice({ tone: 'ok', text: result.note });
      setWebhookName('');
      setWebhookUrl('');
      await load();
    } catch (error) {
      setWebhookNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not create the endpoint.',
      });
    } finally {
      setWebhookBusy(false);
    }
  };

  const toggleEndpoint = async (id: number, enabled: boolean) => {
    try {
      await updateWebhook(id, { enabled });
      await load();
    } catch (error) {
      setWebhookNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not update the endpoint.',
      });
    }
  };

  const sendTestEvent = async (id: number) => {
    try {
      const result = await testWebhook(id);
      setWebhookNotice({
        tone: result.delivered ? 'ok' : 'bad',
        text: result.delivered
          ? 'Test event delivered and signed with the endpoint secret.'
          : `Delivery failed (${result.detail}).`,
      });
      await load();
    } catch (error) {
      setWebhookNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not send the test event.',
      });
    }
  };

  const removeEndpoint = async (id: number, name: string) => {
    if (!window.confirm(`Delete the webhook endpoint "${name}"? Future deliveries stop; audit history is kept.`)) return;
    try {
      await deleteWebhook(id);
      setWebhookNotice({ tone: 'ok', text: `Endpoint "${name}" deleted.` });
      await load();
    } catch (error) {
      setWebhookNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not delete the endpoint.',
      });
    }
  };

  const runTestNotification = async () => {
    setTestNotice(null);
    try {
      const result = await sendTestNotification();
      setTestNotice({ tone: result.delivered ? 'ok' : 'bad', text: result.detail });
    } catch (error) {
      setTestNotice({
        tone: 'bad',
        text: error instanceof Error ? error.message : 'Could not send a test notification.',
      });
    }
  };

  const checkHealth = async () => {
    setHealth({ state: 'checking', detail: '' });
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

  const copyValue = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(value);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      setCopied(null);
    }
  };

  const startTwoFactor = async () => {
    setTwoFactorNotice(null);
    try {
      setTwoFactorSetup(await setupTwoFactor());
      setRecoveryCodes(null);
    } catch (error) {
      setTwoFactorNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not start 2FA setup.' });
    }
  };

  const confirmTwoFactor = async () => {
    setTwoFactorNotice(null);
    try {
      const result = await enableTwoFactor(twoFactorCode.trim());
      setRecoveryCodes(result.recovery_codes);
      setTwoFactorSetup(null);
      setTwoFactorCode('');
      setTwoFactor({ enabled: true, recovery: result.recovery_codes.length });
      setTwoFactorNotice({ tone: 'ok', text: 'Two-factor authentication is on. Save the recovery codes now.' });
    } catch (error) {
      setTwoFactorNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'That code was not accepted.' });
    }
  };

  const disable2fa = async () => {
    setTwoFactorNotice(null);
    try {
      await disableTwoFactor(twoFactorPassword);
      setTwoFactorPassword('');
      setRecoveryCodes(null);
      setTwoFactor({ enabled: false, recovery: 0 });
      setTwoFactorNotice({ tone: 'ok', text: 'Two-factor authentication is off.' });
    } catch (error) {
      setTwoFactorNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not disable 2FA.' });
    }
  };

  const revokeOneSession = async (id: number, label: string) => {
    if (!window.confirm(`Sign out ${label}?`)) return;
    setSessionNotice(null);
    try {
      await revokeSession(id);
      const list = await getSessions();
      setSessions(list);
    } catch (error) {
      setSessionNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not revoke that session.' });
    }
  };

  const revokeAllOtherSessions = async () => {
    if (!window.confirm('Sign out every other device? They will need to sign in again.')) return;
    setSessionNotice(null);
    try {
      const result = await revokeOtherSessions();
      setSessionNotice({ tone: 'ok', text: `${result.revoked} other session(s) signed out.` });
      setSessions(await getSessions());
    } catch (error) {
      setSessionNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not revoke sessions.' });
    }
  };

  const connectGithubAccount = async (event: FormEvent) => {
    event.preventDefault();
    if (!githubToken.trim()) return;
    setGithubBusy(true);
    setGithubNotice(null);
    try {
      const result = await connectGitHub(githubToken.trim());
      setGithubNotice({ tone: 'ok', text: `Connected to ${result.github.account ?? 'GitHub'}.` });
      setGithubToken('');
      await load();
    } catch (error) {
      setGithubNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not connect GitHub.' });
    } finally {
      setGithubBusy(false);
    }
  };

  const disconnectGithubAccount = async () => {
    if (
      !window.confirm(
        'Disconnect GitHub? Repository and scan history is kept, but new scans cannot read manifests until you reconnect.',
      )
    ) {
      return;
    }
    setGithubNotice(null);
    try {
      await disconnectGitHub();
      setGithubNotice({ tone: 'ok', text: 'GitHub disconnected. History was preserved.' });
      await load();
    } catch (error) {
      setGithubNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not disconnect GitHub.' });
    }
  };

  const runScheduleNow = async () => {
    setScheduleNotice(null);
    try {
      const result = await runScheduledScansNow();
      setScheduleNotice({
        tone: 'ok',
        text: `Queued ${result.queued.length} scan(s) across ${new Set(result.queued.map((item) => item.repository)).size} repositories.`,
      });
    } catch (error) {
      setScheduleNotice({ tone: 'bad', text: error instanceof Error ? error.message : 'Could not run scheduled scans.' });
    }
  };

  if (loading) return <Loading label="Loading settings" />;
  if (loadError) return <ErrorState message={loadError} onRetry={() => void load()} />;
  if (!payload || !workspace || !user) return null;

  const active = sections.find((item) => item.key === section) ?? sections[0];
  const needle = query.trim().toLowerCase();
  const visibleSections = needle
    ? sections.filter((item) => `${item.label} ${item.hint}`.toLowerCase().includes(needle))
    : sections;

  const notifications = user.notifications;
  const isAdmin = payload.account.role === 'owner' || payload.account.role === 'admin';
  const scan = workspace.scan;

  const updateNotificationEvents = (key: string, value: boolean) =>
    updatePrefs({ notifications: { ...notifications, events: { ...notifications.events, [key]: value } } });

  return (
    <div className="settings-page">
      <div className="settings-shell">
        <aside className="settings-rail">
          <h2 className="settings-rail-title">Settings</h2>

          <label className="search">
            <Search size={16} aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search settings"
              aria-label="Search settings sections"
            />
          </label>

          <nav className="settings-nav" aria-label="Settings sections">
            {visibleSections.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                type="button"
                aria-current={section === key ? 'true' : undefined}
                onClick={() => setSection(key)}
              >
                <Icon size={16} aria-hidden="true" />
                <span>{label}</span>
              </button>
            ))}
          </nav>
        </aside>

        <div className="settings-body">
          <header className="settings-body-head">
            <div>
              <h2>{active.label}</h2>
              <p>{active.hint}</p>
            </div>
            <StatusChip
              status={section === 'scan' ? scanStatus : prefsStatus}
              message={section === 'scan' ? scanError : prefsError}
              onRetry={section === 'scan' ? retryScan : retryPrefs}
            />
          </header>

          {section === 'general' && (
            <>
              <section className="settings-section" aria-label="Workspace">
                <h3 className="settings-section-title">Workspace</h3>
                <form className="settings-inline" onSubmit={saveName}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="workspace-name">
                      Workspace name
                    </label>
                    <input
                      id="workspace-name"
                      className="form-input"
                      value={nameDraft}
                      maxLength={64}
                      disabled={!isAdmin}
                      onChange={(event) => {
                        setNameDraft(event.target.value);
                        setNameStatus('idle');
                      }}
                    />
                  </div>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={!isAdmin || nameStatus === 'saving' || nameDraft.trim() === workspace.name}
                  >
                    {nameStatus === 'saving' ? 'Saving…' : 'Save name'}
                  </button>
                  <StatusChip status={nameStatus} message={nameError} />
                </form>
                <p className="settings-section-note">
                  Workspace-wide. Displayed in the sidebar and header, and recorded in the audit trail when it changes.
                </p>
                {!isAdmin && (
                  <p className="settings-notice">
                    <TriangleAlert size={14} aria-hidden="true" />
                    Only Owners and Admins can rename the workspace.
                  </p>
                )}
              </section>

              <section className="settings-section" aria-label="Locale and formats">
                <h3 className="settings-section-title">Locale &amp; formats</h3>
                <div className="settings-rows">
                  <Row
                    label="Language"
                    help="Additional languages will appear here as they are translated."
                    control={
                      <Select
                        ariaLabel="Interface language"
                        value={user.language}
                        onChange={(value) => updatePrefs({ language: value })}
                        options={[{ value: 'en', label: 'English' }]}
                      />
                    }
                  />
                  <Row
                    label="Date format"
                    help="Applies to scan timestamps and the audit trail."
                    control={
                      <Select
                        ariaLabel="Date format"
                        value={user.date_format}
                        onChange={(value) => updatePrefs({ date_format: value as UserPreferences['date_format'] })}
                        options={[
                          { value: 'YYYY-MM-DD', label: 'YYYY-MM-DD' },
                          { value: 'DD/MM/YYYY', label: 'DD/MM/YYYY' },
                          { value: 'MM/DD/YYYY', label: 'MM/DD/YYYY' },
                        ]}
                      />
                    }
                  />
                  <Row
                    label="Time format"
                    help="Timestamps are stored in UTC and formatted for your time zone."
                    control={
                      <Select
                        ariaLabel="Time format"
                        value={user.time_format}
                        onChange={(value) => updatePrefs({ time_format: value as UserPreferences['time_format'] })}
                        options={[
                          { value: '24h', label: '24-hour (14:30)' },
                          { value: '12h', label: '12-hour (2:30 PM)' },
                        ]}
                      />
                    }
                  />
                  <Row
                    label="Time zone"
                    help={`Currently showing: ${formatDateTime(new Date().toISOString())}, ${user.timezone}`}
                    control={
                      <select
                        className="form-input settings-control-wide"
                        aria-label="Time zone"
                        value={user.timezone}
                        onChange={(event) => updatePrefs({ timezone: event.target.value })}
                      >
                        {(TIME_ZONES.includes(user.timezone) ? TIME_ZONES : [user.timezone, ...TIME_ZONES]).map(
                          (zone) => (
                            <option key={zone} value={zone}>
                              {zone}
                            </option>
                          ),
                        )}
                      </select>
                    }
                  />
                </div>
              </section>

              <section className="settings-section" aria-label="Application behaviour">
                <h3 className="settings-section-title">Application behaviour</h3>
                <div className="settings-rows">
                  <Row
                    label="Default landing page"
                    help="The first page shown after you sign in."
                    control={
                      <Select
                        ariaLabel="Default landing page"
                        value={user.landing_page}
                        onChange={(value) => updatePrefs({ landing_page: value as UserPreferences['landing_page'] })}
                        options={[
                          { value: 'dashboard', label: 'Dashboard' },
                          { value: 'repositories', label: 'Repositories' },
                          { value: 'scans', label: 'Scans' },
                          { value: 'findings', label: 'Findings' },
                        ]}
                      />
                    }
                  />
                  <Row
                    label="Dashboard auto-refresh"
                    help="Refreshes the dashboard silently in the background."
                    control={
                      <Toggle
                        label="Dashboard auto-refresh"
                        checked={user.auto_refresh}
                        onChange={(value) => updatePrefs({ auto_refresh: value })}
                      />
                    }
                  />
                  <Row
                    label="Refresh interval"
                    help="How often the dashboard re-reads its figures."
                    control={
                      <Select
                        ariaLabel="Auto-refresh interval"
                        value={String(user.refresh_interval)}
                        disabled={!user.auto_refresh}
                        onChange={(value) => updatePrefs({ refresh_interval: Number(value) })}
                        options={[
                          { value: '15', label: 'Every 15 seconds' },
                          { value: '30', label: 'Every 30 seconds' },
                          { value: '60', label: 'Every minute' },
                          { value: '300', label: 'Every 5 minutes' },
                        ]}
                      />
                    }
                  />
                  <Row
                    label="Default table page size"
                    help="Rows loaded for the findings and audit tables."
                    control={
                      <Select
                        ariaLabel="Default table page size"
                        value={String(user.page_size)}
                        onChange={(value) => updatePrefs({ page_size: Number(value) })}
                        options={[
                          { value: '10', label: '10 rows' },
                          { value: '25', label: '25 rows' },
                          { value: '50', label: '50 rows' },
                          { value: '100', label: '100 rows' },
                        ]}
                      />
                    }
                  />
                </div>
              </section>
            </>
          )}

          {section === 'account' && (
            <>
              <section className="settings-section" aria-label="Profile">
                <h3 className="settings-section-title">Profile</h3>
                <div className="settings-inline">
                  <div className="form-field">
                    <label className="form-label" htmlFor="display-name">
                      Display name
                    </label>
                    <input
                      id="display-name"
                      className="form-input"
                      value={user.display_name}
                      maxLength={64}
                      placeholder={payload.account.username}
                      onChange={(event) => updatePrefs({ display_name: event.target.value })}
                    />
                  </div>
                </div>
                <dl className="settings-kv">
                  <div>
                    <dt>Username</dt>
                    <dd>{payload.account.username}</dd>
                  </div>
                  <div>
                    <dt>Email</dt>
                    <dd>
                      {payload.account.email} <span className="badge badge-queued">Primary sign-in</span>
                    </dd>
                  </div>
                  <div>
                    <dt>Workspace role</dt>
                    <dd>{roleLabels[payload.account.role] ?? payload.account.role}</dd>
                  </div>
                  <div>
                    <dt>Member since</dt>
                    <dd>{formatDateTime(payload.account.member_since)}</dd>
                  </div>
                </dl>
                <p className="settings-section-note">
                  This deployment signs in with username or email and a password, and does not send verification
                  mail, so changing your email address is not available here yet.
                </p>
              </section>

              <section className="settings-section" aria-label="Change password">
                <h3 className="settings-section-title">Change password</h3>
                <form className="settings-fields" onSubmit={submitPassword}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="current-password">
                      Current password
                    </label>
                    <input
                      id="current-password"
                      className="form-input"
                      type="password"
                      autoComplete="current-password"
                      value={pwCurrent}
                      onChange={(event) => setPwCurrent(event.target.value)}
                      required
                    />
                  </div>
                  <div className="settings-inline">
                    <div className="form-field">
                      <label className="form-label" htmlFor="new-password">
                        New password
                      </label>
                      <input
                        id="new-password"
                        className="form-input"
                        type="password"
                        autoComplete="new-password"
                        minLength={8}
                        value={pwNew}
                        onChange={(event) => setPwNew(event.target.value)}
                        required
                      />
                    </div>
                    <div className="form-field">
                      <label className="form-label" htmlFor="confirm-password">
                        Confirm new password
                      </label>
                      <input
                        id="confirm-password"
                        className="form-input"
                        type="password"
                        autoComplete="new-password"
                        minLength={8}
                        value={pwConfirm}
                        onChange={(event) => setPwConfirm(event.target.value)}
                        required
                      />
                    </div>
                  </div>
                  <div className="settings-actions">
                    <button type="submit" className="btn btn-primary" disabled={pwState.status === 'saving'}>
                      {pwState.status === 'saving' ? 'Updating…' : 'Update password'}
                    </button>
                    <StatusChip status={pwState.status} message={pwState.message} />
                  </div>
                  {pwState.status === 'saved' && (
                    <p className="settings-notice settings-notice-ok" role="status">
                      <Check size={14} aria-hidden="true" /> {pwState.message}
                    </p>
                  )}
                </form>
                <p className="settings-section-note">
                  Passwords are hashed with bcrypt on the server. At least 8 characters are required.
                </p>
              </section>

              <section className="settings-section" aria-label="Active session">
                <h3 className="settings-section-title">Active session</h3>
                <dl className="settings-kv">
                  <div>
                    <dt>Device</dt>
                    <dd>{browser} on this computer</dd>
                  </div>
                  <div>
                    <dt>Signed in as</dt>
                    <dd>{payload.account.email}</dd>
                  </div>
                  <div>
                    <dt>Session type</dt>
                    <dd>{remember ? 'Kept after the browser closes' : 'Ends with this browser session'}</dd>
                  </div>
                </dl>
                <div className="settings-rows">
                  <Row
                    label="Keep me signed in"
                    help="Stores the session token on this device instead of only this tab."
                    control={
                      <Toggle
                        label="Keep me signed in"
                        checked={remember}
                        onChange={(value) => setRemember(value)}
                      />
                    }
                  />
                </div>
                <p className="settings-section-note">
                  Every sign-in opens a server-side session. Revoking one signs that device out on its next request.
                </p>

                <div className="settings-table-wrap">
                  <table className="settings-table">
                    <thead>
                      <tr>
                        <th scope="col">Device</th>
                        <th scope="col">IP</th>
                        <th scope="col">Last active</th>
                        <th scope="col">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sessions.map((session) => (
                        <tr key={session.id}>
                          <td>
                            {(session.user_agent ?? 'Unknown device').slice(0, 58)}
                            {session.current && (
                              <span className="badge badge-primary" style={{ marginLeft: '0.45rem' }}>This device</span>
                            )}
                          </td>
                          <td className="muted">{session.ip_address ?? '—'}</td>
                          <td className="muted">{formatDateTime(session.last_seen_at)}</td>
                          <td>
                            <button
                              type="button"
                              className="btn btn-ghost"
                              onClick={() => void revokeOneSession(session.id, session.current ? 'this device' : (session.user_agent ?? 'that device'))}
                            >
                              Sign out
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="settings-actions">
                  <button type="button" className="btn" onClick={() => void revokeAllOtherSessions()}>
                    Sign out all other devices
                  </button>
                </div>

                {sessionNotice && (
                  <p className={`settings-notice ${sessionNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`} role="status">
                    {sessionNotice.text}
                  </p>
                )}
              </section>

              <section className="settings-section" aria-label="Two-factor authentication">
                <h3 className="settings-section-title">Two-factor authentication</h3>
                <div className="settings-rows">
                  <Row
                    label="Authenticator app"
                    help="Six-digit TOTP codes from any authenticator app, plus single-use recovery codes."
                    control={
                      <span className={`badge ${twoFactor?.enabled ? 'badge-ok' : 'badge-muted'}`}>
                        {twoFactor?.enabled ? 'Enabled' : 'Not enabled'}
                      </span>
                    }
                  />
                  {twoFactor?.enabled && (
                    <Row
                      label="Recovery codes"
                      help="Each code works once if you lose your authenticator."
                      control={<span className="badge badge-queued">{twoFactor.recovery} remaining</span>}
                    />
                  )}
                </div>

                {twoFactorNotice && (
                  <p
                    className={`settings-notice ${twoFactorNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`}
                    role="status"
                  >
                    {twoFactorNotice.text}
                  </p>
                )}

                {!twoFactor?.enabled && !twoFactorSetup && (
                  <div className="settings-actions">
                    <button type="button" className="btn btn-primary" onClick={() => void startTwoFactor()}>
                      Set up authenticator
                    </button>
                  </div>
                )}

                {twoFactorSetup && (
                  <>
                    <div className="settings-secret">
                      <strong>Add this secret to your authenticator app</strong>
                      <code>{twoFactorSetup.secret}</code>
                      <code>{twoFactorSetup.otpauth_uri}</code>
                      <div className="settings-secret-actions">
                        <button type="button" onClick={() => void copyValue(twoFactorSetup.secret)}>
                          {copied === twoFactorSetup.secret ? 'Copied' : 'Copy secret'}
                        </button>
                        <button type="button" onClick={() => setTwoFactorSetup(null)}>
                          Cancel
                        </button>
                      </div>
                    </div>
                    <div className="settings-inline">
                      <div className="form-field form-field-narrow">
                        <label className="form-label" htmlFor="totp-code">
                          6-digit code
                        </label>
                        <input
                          id="totp-code"
                          className="form-input"
                          inputMode="numeric"
                          value={twoFactorCode}
                          placeholder="6-digit code"
                          onChange={(event) => setTwoFactorCode(event.target.value)}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={twoFactorCode.trim().length < 6}
                        onClick={() => void confirmTwoFactor()}
                      >
                        Enable 2FA
                      </button>
                    </div>
                  </>
                )}

                {recoveryCodes && (
                  <div className="settings-secret">
                    <strong>Recovery codes — save these now, they are shown once</strong>
                    <code style={{ whiteSpace: 'pre-wrap' }}>{recoveryCodes.join('   ')}</code>
                    <div className="settings-secret-actions">
                      <button type="button" onClick={() => void copyValue(recoveryCodes.join('\n'))}>
                        {copied === recoveryCodes.join('\n') ? 'Copied' : 'Copy codes'}
                      </button>
                      <button type="button" onClick={() => setRecoveryCodes(null)}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                )}

                {twoFactor?.enabled && (
                  <div className="settings-inline">
                    <div className="form-field">
                      <label className="form-label" htmlFor="disable-2fa-password">
                        Password required to disable 2FA
                      </label>
                      <input
                        id="disable-2fa-password"
                        className="form-input"
                        type="password"
                        value={twoFactorPassword}
                        onChange={(event) => setTwoFactorPassword(event.target.value)}
                      />
                    </div>
                    <button
                      type="button"
                      className="danger-btn"
                      disabled={!twoFactorPassword}
                      onClick={() => void disable2fa()}
                    >
                      Disable 2FA
                    </button>
                  </div>
                )}
              </section>
            </>
          )}

          {section === 'github' && (
            <>
              <section className="settings-section" aria-label="GitHub connection">
                <h3 className="settings-section-title">Connection</h3>
                <dl className="settings-kv">
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <span className={`badge ${payload.integrations.github.connected ? 'badge-ok' : 'badge-warn'}`}>
                        {payload.integrations.github.connected ? 'Connected' : 'Token not configured'}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt>Account / organization</dt>
                    <dd>{payload.integrations.github.account ?? '—'}</dd>
                  </div>
                  <div>
                    <dt>Webhook signing secret</dt>
                    <dd>
                      {payload.integrations.github.webhook_secret_configured ? (
                        <span className="badge badge-ok">Configured</span>
                      ) : (
                        <span className="badge badge-warn">Not configured</span>
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Last webhook event</dt>
                    <dd>
                      {payload.integrations.github.last_event_at
                        ? `${payload.integrations.github.last_event_action} · ${formatDateTime(payload.integrations.github.last_event_at)}`
                        : 'No events received yet'}
                    </dd>
                  </div>
                </dl>
                <form className="settings-inline" onSubmit={connectGithubAccount}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="github-token">
                      Personal access token
                    </label>
                    <input
                      id="github-token"
                      className="form-input"
                      type="password"
                      autoComplete="off"
                      placeholder="GitHub token"
                      value={githubToken}
                      onChange={(event) => setGithubToken(event.target.value)}
                    />
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={githubBusy || !githubToken.trim()}>
                    {githubBusy ? 'Validating…' : 'Connect GitHub'}
                  </button>
                  {payload.integrations.github.source === 'settings' && (
                    <button type="button" className="danger-btn" onClick={() => void disconnectGithubAccount()}>
                      Disconnect
                    </button>
                  )}
                </form>

                {payload.integrations.github.oauth_authorize_url && (
                  <p className="settings-section-note">
                    An OAuth app is configured on this server. You can also{' '}
                    <a href={payload.integrations.github.oauth_authorize_url}>authorize through GitHub</a>.
                  </p>
                )}

                {githubNotice && (
                  <p className={`settings-notice ${githubNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`} role="status">
                    {githubNotice.text}
                  </p>
                )}

                <p className="settings-section-note">
                  The token is validated against the GitHub API, encrypted at rest, and used for manifest reads and
                  commit statuses. Disconnecting keeps repository and scan history.
                  {payload.integrations.github.source === 'environment' && (
                    <> Currently reading the token from the API environment.</>
                  )}
                </p>
              </section>

              <section className="settings-section" aria-label="Repository access">
                <h3 className="settings-section-title">Repository access</h3>
                {payload.integrations.github.repositories.length === 0 ? (
                  <div className="settings-empty">
                    No repositories are registered yet. Repositories appear here after their first scan.
                  </div>
                ) : (
                  <div className="settings-table-wrap">
                    <table className="settings-table">
                      <thead>
                        <tr>
                          <th scope="col">Repository</th>
                          <th scope="col">URL</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payload.integrations.github.repositories.map((repo) => (
                          <tr key={repo.id}>
                            <td>{repo.name}</td>
                            <td className="muted">{repo.url || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="settings-section-note">
                  A repository missing from this list has not been granted to BuildShield, or has never been
                  scanned. Repository operations live in the Repositories tab.
                </p>
              </section>

              <section className="settings-section" aria-label="Granted permissions">
                <h3 className="settings-section-title">Granted permissions</h3>
                <ul className="settings-list-plain">
                  {payload.integrations.github.permissions.map((permission) => (
                    <li key={permission}>{permission}</li>
                  ))}
                </ul>
                <p className="settings-section-note">
                  These are the permissions the backend actually uses. BuildShield does not request write access to
                  code.
                </p>
              </section>
            </>
          )}

          {section === 'scan' && (
            <>
              <section className="settings-section" aria-label="Automatic triggers">
                <h3 className="settings-section-title">Automatic scan triggers</h3>
                <div className="settings-rows">
                  {(
                    [
                      { key: 'pr_opened', label: 'Pull request opened' },
                      { key: 'pr_synchronize', label: 'Pull request updated with new commits' },
                      { key: 'pr_reopened', label: 'Pull request reopened' },
                      { key: 'push', label: 'Changes pushed to a selected branch' },
                    ] as const
                  ).map((trigger) => (
                    <Row
                      key={trigger.key}
                      label={trigger.label}
                      help="The GitHub webhook handler honours this switch before starting a scan."
                      control={
                        <Toggle
                          label={trigger.label}
                          checked={scan.triggers[trigger.key]}
                          onChange={(value) =>
                            updateScan({ triggers: { ...scan.triggers, [trigger.key]: value } })
                          }
                        />
                      }
                    />
                  ))}
                </div>
              </section>

              <section className="settings-section" aria-label="Scanner">
                <h3 className="settings-section-title">Default scanner</h3>
                <div className="settings-rows">
                  <Row
                    label={payload.server.scanner.name}
                    help={payload.server.scanner.description}
                    control={
                      <label className="settings-checkbox">
                        <input type="checkbox" checked readOnly disabled />
                        Installed
                      </label>
                    }
                  />
                </div>
                <p className="settings-section-note">
                  This is the only scanner engine available in this deployment, so it cannot be deselected.
                </p>
              </section>

              <section className="settings-section" aria-label="Scan limits">
                <h3 className="settings-section-title">Execution limits</h3>
                <div className="settings-rows">
                  <Row
                    label="Scan timeout"
                    help="A scan that runs longer fails instead of being reported clean. 30–3600 seconds."
                    control={
                      <input
                        className="form-input settings-control-wide"
                        type="number"
                        min={30}
                        max={3600}
                        step={30}
                        value={timeoutDraft}
                        aria-label="Scan timeout in seconds"
                        onChange={(event) => {
                          const value = event.target.value;
                          setTimeoutDraft(value);
                          const parsed = Number(value);
                          if (Number.isInteger(parsed) && parsed >= 30 && parsed <= 3600) {
                            updateScan({ timeout_seconds: parsed });
                          }
                        }}
                      />
                    }
                  />
                  <Row
                    label="Maximum concurrent scans"
                    help="Additional scans wait for a free slot instead of running in parallel."
                    control={
                      <Select
                        ariaLabel="Maximum concurrent scans"
                        value={String(scan.concurrency)}
                        onChange={(value) => updateScan({ concurrency: Number(value) })}
                        options={[1, 2, 3, 4, 5, 6, 8, 10].map((value) => ({
                          value: String(value),
                          label: String(value),
                        }))}
                      />
                    }
                  />
                </div>
              </section>

              <section className="settings-section" aria-label="Scheduled scans">
                <h3 className="settings-section-title">Scheduled scans</h3>
                <div className="settings-rows">
                  <Row
                    label="Enable scheduled scans"
                    help="The in-process scheduler checks every 20 seconds and runs when the next slot is due."
                    control={
                      <Toggle
                        label="Enable scheduled scans"
                        checked={scan.scheduled.enabled}
                        onChange={(value) =>
                          updateScan({ scheduled: { ...scan.scheduled, enabled: value } })
                        }
                      />
                    }
                  />
                  <Row
                    label="Frequency"
                    help="Weekly runs on Mondays."
                    control={
                      <Select
                        ariaLabel="Schedule frequency"
                        value={scan.scheduled.frequency}
                        onChange={(value) =>
                          updateScan({ scheduled: { ...scan.scheduled, frequency: value as 'daily' | 'weekly' } })
                        }
                        options={[
                          { value: 'daily', label: 'Daily' },
                          { value: 'weekly', label: 'Weekly' },
                        ]}
                      />
                    }
                  />
                  <Row
                    label="Run at (UTC)"
                    help="Scans start at this time in the server's UTC clock."
                    control={
                      <input
                        className="form-input settings-control-wide"
                        type="time"
                        aria-label="Scheduled scan time"
                        value={scan.scheduled.time}
                        onChange={(event) =>
                          updateScan({ scheduled: { ...scan.scheduled, time: event.target.value } })
                        }
                      />
                    }
                  />
                  <Row
                    label="Next run"
                    control={
                      <span className="settings-row-help">
                        {scan.scheduled.next_run ? formatDateTime(scan.scheduled.next_run) : 'Not scheduled'}
                      </span>
                    }
                  />
                  <Row
                    label="Last run"
                    control={
                      <span className="settings-row-help">
                        {scan.scheduled.last_run ? formatDateTime(scan.scheduled.last_run) : 'Never'}
                      </span>
                    }
                  />
                </div>

                <div className="settings-actions">
                  <button type="button" className="btn" onClick={() => void runScheduleNow()}>
                    Run scheduled scans now
                  </button>
                  {scheduleNotice && (
                    <span
                      className={`settings-notice ${scheduleNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`}
                      role="status"
                    >
                      {scheduleNotice.text}
                    </span>
                  )}
                </div>

                <p className="settings-section-note">
                  Scheduled runs scan each repository on every branch listed below and use the same scanner, timeout
                  and concurrency limits.
                </p>
              </section>

              <section className="settings-section" aria-label="Branches">
                <h3 className="settings-section-title">Default branches</h3>
                <div className="settings-inline">
                  <div className="form-field">
                    <label className="form-label" htmlFor="branches">
                      Branch names or patterns
                    </label>
                    <input
                      id="branches"
                      className="form-input"
                      value={branchesDraft}
                      placeholder="Comma-separated branch names"
                      onChange={(event) => setBranchesDraft(event.target.value)}
                    />
                  </div>
                  <button type="button" className="btn btn-primary" onClick={() => void saveBranches()}>
                    Save branches
                  </button>
                </div>
                <p className="settings-section-note">
                  Comma-separated. Applies to push-triggered scans across connected repositories.
                </p>
                <p className="settings-section-note">
                  Vulnerability blocking and enforcement live in the Policies tab, not here.
                </p>
              </section>
            </>
          )}

          {section === 'notifications' && (
            <>
              <section className="settings-section" aria-label="Notification events">
                <h3 className="settings-section-title">Event types</h3>
                <p className="settings-section-note">
                  These choose what you are told about. Severity and blocking behaviour are decided in the Policies
                  tab.
                </p>
                {notificationGroups.map((group) => (
                  <div key={group.title}>
                    <h4 className="settings-section-title" style={{ fontSize: '0.82rem', marginTop: '0.4rem' }}>
                      {group.title}
                    </h4>
                    <div className="settings-rows">
                      {group.events.map((event) => (
                        <Row
                          key={event.key}
                          label={event.label}
                          control={
                            <Toggle
                              label={event.label}
                              checked={Boolean(notifications.events[event.key])}
                              onChange={(value) => updateNotificationEvents(event.key, value)}
                            />
                          }
                        />
                      ))}
                    </div>
                  </div>
                ))}
              </section>

              <section className="settings-section" aria-label="Delivery channels">
                <h3 className="settings-section-title">Delivery channels</h3>
                <div className="settings-rows">
                  <Row
                    label="In-app notifications"
                    help="Shown inside BuildShield and recorded against your account."
                    control={
                      <Toggle
                        label="In-app notifications"
                        checked={notifications.channels.in_app}
                        onChange={(value) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              channels: { ...notifications.channels, in_app: value },
                            },
                          })
                        }
                      />
                    }
                  />
                  <Row
                    label="Email notifications"
                    help={`Delivered through ${payload.server.email.host ?? 'SMTP'} on port ${payload.server.email.port}.`}
                    control={
                      <Toggle
                        label="Email notifications"
                        checked={notifications.channels.email}
                        onChange={(value) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              channels: { ...notifications.channels, email: value },
                            },
                          })
                        }
                      />
                    }
                  />
                  <Row
                    label="Digest frequency"
                    help="Security and account alerts are always sent immediately."
                    control={
                      <Select
                        ariaLabel="Digest frequency"
                        value={notifications.digest}
                        onChange={(value) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              digest: value as typeof notifications.digest,
                            },
                          })
                        }
                        options={[
                          { value: 'immediate', label: 'Immediate' },
                          { value: 'daily', label: 'Daily summary' },
                          { value: 'weekly', label: 'Weekly summary' },
                        ]}
                      />
                    }
                  />
                </div>
                {payload.server.email_configured ? (
                  <p className="settings-notice settings-notice-ok">
                    <Check size={14} aria-hidden="true" />
                    Mail is delivered through {payload.server.email.host}:{payload.server.email.port} as{' '}
                    {payload.server.email.from_address}.
                  </p>
                ) : (
                  <p className="settings-notice">
                    <TriangleAlert size={14} aria-hidden="true" />
                    No SMTP transport is configured (SMTP_HOST, SMTP_PORT, SMTP_FROM), so email cannot be delivered.
                  </p>
                )}

                <h4 className="settings-section-title" style={{ fontSize: '0.82rem', marginTop: '0.4rem' }}>
                  Recent notifications
                </h4>
                {payload.notifications.length === 0 ? (
                  <div className="settings-empty">No notifications have been generated yet.</div>
                ) : (
                  <div className="settings-table-wrap">
                    <table className="settings-table">
                      <thead>
                        <tr>
                          <th scope="col">Event</th>
                          <th scope="col">Status</th>
                          <th scope="col">When</th>
                          <th scope="col">Detail</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payload.notifications.slice(0, 8).map((item) => (
                          <tr key={item.id}>
                            <td>{item.subject}</td>
                            <td>
                              <span className={`badge ${item.status === 'sent' || item.status === 'in_app' ? 'badge-ok' : item.status === 'queued' ? 'badge-warn' : 'badge-muted'}`}>
                                {item.status}
                              </span>
                            </td>
                            <td className="muted">{formatDateTime(item.sent_at ?? item.created_at)}</td>
                            <td className="muted">{item.detail ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section className="settings-section" aria-label="Quiet hours">
                <h3 className="settings-section-title">Quiet hours</h3>
                <div className="settings-rows">
                  <Row
                    label="Enable quiet hours"
                    help={`Applied in ${user.timezone}.`}
                    control={
                      <Toggle
                        label="Enable quiet hours"
                        checked={notifications.quiet_hours.enabled}
                        onChange={(value) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              quiet_hours: { ...notifications.quiet_hours, enabled: value },
                            },
                          })
                        }
                      />
                    }
                  />
                  <Row
                    label="From"
                    control={
                      <input
                        className="form-input settings-control-wide"
                        type="time"
                        aria-label="Quiet hours start"
                        value={notifications.quiet_hours.start}
                        disabled={!notifications.quiet_hours.enabled}
                        onChange={(event) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              quiet_hours: { ...notifications.quiet_hours, start: event.target.value },
                            },
                          })
                        }
                      />
                    }
                  />
                  <Row
                    label="Until"
                    control={
                      <input
                        className="form-input settings-control-wide"
                        type="time"
                        aria-label="Quiet hours end"
                        value={notifications.quiet_hours.end}
                        disabled={!notifications.quiet_hours.enabled}
                        onChange={(event) =>
                          updatePrefs({
                            notifications: {
                              ...notifications,
                              quiet_hours: { ...notifications.quiet_hours, end: event.target.value },
                            },
                          })
                        }
                      />
                    }
                  />
                </div>
                <p className="settings-section-note">
                  Critical findings and account-security notices are never held back by quiet hours.
                </p>
              </section>

              <section className="settings-section" aria-label="Test notification">
                <h3 className="settings-section-title">Test delivery</h3>
                <div className="settings-actions">
                  <button type="button" className="btn" onClick={() => void runTestNotification()}>
                    Send test notification
                  </button>
                  {testNotice && (
                    <span className={`settings-notice ${testNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`} role="status">
                      {testNotice.text}
                    </span>
                  )}
                </div>
              </section>
            </>
          )}

          {section === 'team' && (
            <>
              <section className="settings-section" aria-label="Members">
                <h3 className="settings-section-title">
                  Members ({payload.members.length})
                </h3>
                <div className="settings-table-wrap">
                  <table className="settings-table">
                    <thead>
                      <tr>
                        <th scope="col">Email</th>
                        <th scope="col">Role</th>
                        <th scope="col">Status</th>
                        <th scope="col">Added</th>
                        <th scope="col">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payload.members.map((member) => {
                        const isSelf = member.email === payload.account.email;
                        return (
                          <tr key={member.id}>
                            <td>
                              {member.email}
                              {isSelf && <span className="badge badge-primary" style={{ marginLeft: '0.45rem' }}>You</span>}
                            </td>
                            <td>
                              <select
                                aria-label={`Role for ${member.email}`}
                                value={member.role}
                                disabled={!isAdmin}
                                onChange={(event) => void changeMemberRole(member.id, event.target.value)}
                              >
                                {payload.roles.map((role) => (
                                  <option key={role.role} value={role.role}>
                                    {role.label}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <span className={`badge ${member.status === 'active' ? 'badge-ok' : 'badge-warn'}`}>
                                {member.status === 'active' ? 'Active' : 'Invited'}
                              </span>
                            </td>
                            <td className="muted">{formatDateTime(member.invited_at)}</td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-ghost"
                                disabled={isSelf || !isAdmin}
                                onClick={() => void removeMemberById(member.id, member.email)}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="settings-section" aria-label="Invite member">
                <h3 className="settings-section-title">Invite a member</h3>
                <form className="settings-inline" onSubmit={submitInvite}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="invite-email">
                      Email address
                    </label>
                    <input
                      id="invite-email"
                      className="form-input"
                      type="email"
                      value={memberEmail}
                      placeholder="Email address"
                      disabled={!isAdmin}
                      onChange={(event) => setMemberEmail(event.target.value)}
                      required
                    />
                  </div>
                  <div className="form-field form-field-narrow">
                    <label className="form-label" htmlFor="invite-role">
                      Role
                    </label>
                    <select
                      id="invite-role"
                      className="form-input"
                      value={memberRole}
                      disabled={!isAdmin}
                      onChange={(event) => setMemberRole(event.target.value)}
                    >
                      {payload.roles.map((role) => (
                        <option key={role.role} value={role.role}>
                          {role.label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={!isAdmin || memberBusy}>
                    <Plus size={15} aria-hidden="true" />
                    {memberBusy ? 'Inviting…' : 'Invite'}
                  </button>
                </form>
                {memberNotice && (
                  <p
                    className={`settings-notice ${memberNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`}
                    role="status"
                  >
                    {memberNotice.text}
                  </p>
                )}
                <p className="settings-section-note">
                  Invitations are recorded immediately. This deployment has no mail transport, so the invited
                  person is added as pending until they register with that email.
                </p>
              </section>

              <section className="settings-section" aria-label="Role permissions">
                <h3 className="settings-section-title">Role permissions</h3>
                <div className="settings-role-matrix">
                  {payload.roles.map((role) => (
                    <div key={role.role} className="settings-role">
                      <strong>{role.label}</strong>
                      <ul>
                        {role.capabilities.map((capability) => (
                          <li key={capability}>{capability}</li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
                <p className="settings-section-note">
                  The last Owner cannot be demoted or removed. Every membership change is written to the audit
                  trail.
                </p>
              </section>
            </>
          )}

          {section === 'appearance' && (
            <>
              <section className="settings-section" aria-label="Theme">
                <h3 className="settings-section-title">Theme</h3>
                <div className="segmented" role="group" aria-label="Colour theme">
                  {(
                    [
                      { key: 'light', label: 'Light' },
                      { key: 'dark', label: 'Dark' },
                      { key: 'system', label: 'System' },
                    ] as const
                  ).map(({ key, label }) => (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={theme === key}
                      onClick={() => changeTheme(key)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <p className="settings-section-note">
                  System follows your operating system. The theme is stored on this device so it also applies on
                  the sign-in screen.
                </p>
              </section>

              <section className="settings-section" aria-label="Density">
                <h3 className="settings-section-title">Density</h3>
                <div className="segmented" role="group" aria-label="Layout density">
                  {(
                    [
                      { key: 'comfortable', label: 'Comfortable' },
                      { key: 'compact', label: 'Compact' },
                    ] as const
                  ).map(({ key, label }) => (
                    <button
                      key={key}
                      type="button"
                      aria-pressed={user.density === key}
                      onClick={() => updatePrefs({ density: key })}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <p className="settings-section-note">Compact trims row spacing in tables and settings.</p>
              </section>

              <section className="settings-section" aria-label="Motion">
                <h3 className="settings-section-title">Motion</h3>
                <div className="settings-rows">
                  <Row
                    label="Reduce animation"
                    help="Turns off transitions and spinners across the dashboard."
                    control={
                      <Toggle
                        label="Reduce animation"
                        checked={user.reduce_motion}
                        onChange={(value) => updatePrefs({ reduce_motion: value })}
                      />
                    }
                  />
                </div>
              </section>
            </>
          )}

          {section === 'api' && (
            <>
              <section className="settings-section" aria-label="API tokens">
                <h3 className="settings-section-title">API tokens</h3>
                <form className="settings-inline" onSubmit={submitToken}>
                  <div className="form-field">
                    <label className="form-label" htmlFor="token-name">
                      Token name
                    </label>
                    <input
                      id="token-name"
                      className="form-input"
                      value={tokenName}
                      placeholder="What is this token for?"
                      maxLength={64}
                      onChange={(event) => setTokenName(event.target.value)}
                    />
                  </div>
                  <div className="form-field form-field-narrow">
                    <label className="form-label" htmlFor="token-expiry">
                      Expires
                    </label>
                    <select
                      id="token-expiry"
                      className="form-input"
                      value={tokenExpiry}
                      onChange={(event) => setTokenExpiry(event.target.value)}
                    >
                      <option value="30">In 30 days</option>
                      <option value="90">In 90 days</option>
                      <option value="365">In 1 year</option>
                      <option value="0">Never</option>
                    </select>
                  </div>
                  <div className="form-field form-field-narrow">
                    <label className="form-label" htmlFor="token-scopes">
                      Scope
                    </label>
                    <select
                      id="token-scopes"
                      className="form-input"
                      value={tokenScopes}
                      onChange={(event) => setTokenScopes(event.target.value)}
                    >
                      <option value="read,write">Read &amp; write</option>
                      <option value="read">Read only</option>
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary" disabled={tokenBusy}>
                    <Plus size={15} aria-hidden="true" />
                    {tokenBusy ? 'Creating…' : 'Create token'}
                  </button>
                </form>

                {tokenSecret && (
                  <div className="settings-secret" role="status">
                    <strong>Copy this token now — it cannot be shown again.</strong>
                    <code>{tokenSecret}</code>
                    <div className="settings-secret-actions">
                      <button type="button" onClick={() => void copyValue(tokenSecret)}>
                        {copied === tokenSecret ? 'Copied' : 'Copy token'}
                      </button>
                      <button type="button" onClick={() => setTokenSecret(null)}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                )}

                {tokenNotice && (
                  <p className={`settings-notice ${tokenNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`} role="status">
                    {tokenNotice.text}
                  </p>
                )}

                {payload.tokens.length === 0 ? (
                  <div className="settings-empty">No API tokens yet. Create one to call the API from CI.</div>
                ) : (
                  <div className="settings-table-wrap">
                    <table className="settings-table">
                      <thead>
                        <tr>
                          <th scope="col">Name</th>
                          <th scope="col">Prefix</th>
                          <th scope="col">Created</th>
                          <th scope="col">Last used</th>
                          <th scope="col">Expires</th>
                          <th scope="col">Scopes</th>
                          <th scope="col">Status</th>
                          <th scope="col">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payload.tokens.map((token) => (
                          <tr key={token.id}>
                            <td>{token.name}</td>
                            <td>
                              <code>{token.prefix}…</code>
                            </td>
                            <td className="muted">{formatDateTime(token.created_at)}</td>
                            <td className="muted">{token.last_used_at ? formatDateTime(token.last_used_at) : 'Never'}</td>
                            <td className="muted">{token.expires_at ? formatDateTime(token.expires_at) : 'Never'}</td>
                            <td className="muted">{token.scopes.join(' + ')}</td>
                            <td>
                              <span className={`badge ${token.revoked ? 'badge-muted' : 'badge-ok'}`}>
                                {token.revoked ? 'Revoked' : 'Active'}
                              </span>
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn btn-ghost"
                                disabled={token.revoked}
                                onClick={() => void revokeToken(token.id, token.name)}
                              >
                                Revoke
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <p className="settings-section-note">
                  Read-only tokens work for GET requests only; every write is rejected with 403. Only a hash is
                  stored, so the value shown at creation is the only copy.
                </p>
              </section>

              <section className="settings-section" aria-label="API reference">
                <h3 className="settings-section-title">API reference</h3>
                <div className="settings-code">
                  Base URL: {payload.server.api_base}
                  {'\n'}Version: {payload.server.api_version}
                  {'\n'}Auth header: Authorization: Bearer &lt;token&gt;
                  {'\n'}Docs: {payload.server.api_base}/docs
                </div>
              </section>

              <section className="settings-section" aria-label="Webhook endpoints">
                <h3 className="settings-section-title">Webhook endpoints</h3>
                <form className="settings-fields" onSubmit={submitWebhook}>
                  <div className="settings-inline">
                    <div className="form-field">
                      <label className="form-label" htmlFor="webhook-name">
                        Endpoint name
                      </label>
                      <input
                        id="webhook-name"
                        className="form-input"
                        value={webhookName}
                        placeholder="What is this endpoint for?"
                        maxLength={64}
                        onChange={(event) => setWebhookName(event.target.value)}
                      />
                    </div>
                    <div className="form-field">
                      <label className="form-label" htmlFor="webhook-url">
                        Destination URL
                      </label>
                      <input
                        id="webhook-url"
                        className="form-input"
                        type="url"
                        value={webhookUrl}
                        placeholder="Webhook destination URL"
                        onChange={(event) => setWebhookUrl(event.target.value)}
                      />
                    </div>
                  </div>

                  <div className="settings-checkbox-grid">
                    {payload.integrations.webhook_events.map((event) => (
                      <label key={event.id} className="settings-checkbox">
                        <input
                          type="checkbox"
                          checked={webhookEvents.includes(event.id)}
                          onChange={() => toggleWebhookEvent(event.id)}
                        />
                        {event.label}
                      </label>
                    ))}
                  </div>

                  <div className="settings-actions">
                    <button type="submit" className="btn btn-primary" disabled={webhookBusy}>
                      <Plus size={15} aria-hidden="true" />
                      {webhookBusy ? 'Creating…' : 'Add endpoint'}
                    </button>
                  </div>
                </form>

                {webhookSecret && (
                  <div className="settings-secret" role="status">
                    <strong>Signing secret — copy it now, it cannot be shown again.</strong>
                    <code>{webhookSecret}</code>
                    <div className="settings-secret-actions">
                      <button type="button" onClick={() => void copyValue(webhookSecret)}>
                        {copied === webhookSecret ? 'Copied' : 'Copy secret'}
                      </button>
                      <button type="button" onClick={() => setWebhookSecret(null)}>
                        Dismiss
                      </button>
                    </div>
                  </div>
                )}

                {webhookNotice && (
                  <p className={`settings-notice ${webhookNotice.tone === 'ok' ? 'settings-notice-ok' : 'settings-notice-bad'}`} role="status">
                    {webhookNotice.text}
                  </p>
                )}

                {payload.webhooks.length === 0 ? (
                  <div className="settings-empty">
                    No endpoints yet. Add one to receive scan and finding events.
                  </div>
                ) : (
                  <div className="settings-table-wrap">
                    <table className="settings-table">
                      <thead>
                        <tr>
                          <th scope="col">Name</th>
                          <th scope="col">URL</th>
                          <th scope="col">Events</th>
                          <th scope="col">Enabled</th>
                          <th scope="col">Last delivery</th>
                          <th scope="col">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {payload.webhooks.map((endpoint) => (
                          <tr key={endpoint.id}>
                            <td>{endpoint.name}</td>
                            <td className="muted">{endpoint.url}</td>
                            <td className="muted">{endpoint.events.length}</td>
                            <td>
                              <Toggle
                                label={`Enable ${endpoint.name}`}
                                checked={endpoint.enabled}
                                onChange={(value) => void toggleEndpoint(endpoint.id, value)}
                              />
                            </td>
                            <td className="muted">
                              {endpoint.last_delivery_at
                                ? `${endpoint.last_delivery_status} · ${formatDateTime(endpoint.last_delivery_at)}`
                                : 'Never'}
                            </td>
                            <td>
                              <div className="settings-actions">
                                <button
                                  type="button"
                                  className="btn btn-ghost"
                                  onClick={() => void sendTestEvent(endpoint.id)}
                                >
                                  <RefreshCw size={14} aria-hidden="true" /> Test
                                </button>
                                <button
                                  type="button"
                                  className="danger-btn"
                                  onClick={() => void removeEndpoint(endpoint.id, endpoint.name)}
                                >
                                  <Trash2 size={14} aria-hidden="true" /> Delete
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <p className="settings-section-note">
                  Requests are signed with <code>X-BuildShield-Signature: sha256=&lt;hmac&gt;</code> using the endpoint
                  secret. Test deliveries use the `webhook.test` event.
                </p>
              </section>
            </>
          )}

          {section === 'about' && (
            <>
              <section className="settings-section" aria-label="Version">
                <h3 className="settings-section-title">Version &amp; build</h3>
                <dl className="settings-kv">
                  <div>
                    <dt>BuildShield</dt>
                    <dd>{payload.server.version}</dd>
                  </div>
                  <div>
                    <dt>API</dt>
                    <dd>{payload.server.api_version} · {payload.server.api_base}</dd>
                  </div>
                  <div>
                    <dt>Scanner engine</dt>
                    <dd>{payload.server.scanner.name}</dd>
                  </div>
                  <div>
                    <dt>Workspace</dt>
                    <dd>{workspace.name}</dd>
                  </div>
                </dl>
                <p className="settings-section-note">{payload.server.scanner.description}</p>
              </section>

              <section className="settings-section" aria-label="System status">
                <h3 className="settings-section-title">System status</h3>
                <div className="settings-actions">
                  <button type="button" className="btn" onClick={() => void checkHealth()} disabled={health.state === 'checking'}>
                    {health.state === 'checking' ? 'Checking…' : 'Check API health'}
                  </button>
                  {health.state === 'ok' && (
                    <span className="settings-notice settings-notice-ok" role="status">
                      <Check size={14} aria-hidden="true" /> {health.detail}
                    </span>
                  )}
                  {health.state === 'error' && (
                    <span className="settings-notice settings-notice-bad" role="alert">
                      <TriangleAlert size={14} aria-hidden="true" /> {health.detail}
                    </span>
                  )}
                </div>
                <p className="settings-section-note">
                  This checks the live API and database connection. No status value is hard-coded.
                </p>
              </section>

              <section className="settings-section" aria-label="Support">
                <h3 className="settings-section-title">Support &amp; licenses</h3>
                <dl className="settings-kv">
                  <div>
                    <dt>Audit export</dt>
                    <dd>Available from the Audit Logs tab</dd>
                  </div>
                  <div>
                    <dt>Documentation</dt>
                    <dd>API reference at {payload.server.api_base}/docs</dd>
                  </div>
                  <div>
                    <dt>Licenses</dt>
                    <dd>React, Vite, FastAPI, SQLAlchemy, OSV.dev</dd>
                  </div>
                </dl>
                <p className="settings-section-note">
                  BuildShield does not link to an external status page or support desk because this deployment has
                  none configured.
                </p>
              </section>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
