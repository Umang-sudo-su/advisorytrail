export type ScanStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'partial'
  | 'failed'
  | 'timed_out';

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export type ChangeType = 'new' | 'existing' | 'resolved' | 'unknown';

export type ReviewStatus = 'open' | 'dismissed' | 'false_positive';

export interface Repository {
  id: string;
  name: string;
  branch: string;
  private?: boolean;
  /** The API only reports manifests it actually found, so this can be absent. */
  manifests?: string[];
  latestScanStatus?: ScanStatus;
}

/** Raw `/api/v1/scans/` row, as serialized by the API. */
export interface ScanRow {
  id: number | string;
  repository_id?: number;
  repository?: { name?: string };
  repo_name?: string;
  pr_title?: string | null;
  title?: string | null;
  base_commit_hash?: string | null;
  commit_hash?: string | null;
  scanner_engine?: string;
  engine?: string;
  status: string;
  findings?: unknown[];
  findings_count?: number;
  duration_seconds?: number | null;
  created_at?: string | null;
}

/** Advisory detail JSON stored with each finding. */
export interface FindingDetails {
  summary?: string;
  fixed_version?: string | null;
  ecosystem?: string;
  [key: string]: unknown;
}

/** Raw `/api/v1/findings/` row, as serialized by the API. */
export interface FindingRow {
  id: number | string;
  osv_id?: string | null;
  package_name?: string | null;
  package_version?: string | null;
  severity?: string | null;
  status?: string | null;
  details?: FindingDetails | string | null;
}

/** Raw `/api/v1/stats/` payload. */
export interface DashboardResponse {
  active_pr_scans?: number;
  new_pr_vulnerabilities?: number;
  clean_prs?: number;
  vulnerable_repositories?: number;
  failed_incomplete_scans?: number;
  severity_breakdown?: Record<string, number>;
  queue?: QueueItem[];
  healthTrend?: TrendPoint[];
  recentRepos?: RepoHealth[];
}

export interface Scan {
  id: string;
  repoName: string;
  prTitle: string;
  baseSha: string;
  headSha: string;
  engine: string;
  status: ScanStatus;
  highCount: number;
  durationSeconds: number;
}

export interface Finding {
  id: string;
  packageName: string;
  currentVersion: string;
  fixedVersion: string | null;
  severity: Severity;
  change: ChangeType;
  reviewStatus: ReviewStatus;
  advisoryId: string;
  filePath: string;
  priorityReason: string;
  scanner: string;
  fingerprint: string;
}
export interface QueueItem {
  id: string;
  prNumber: number;
  title: string;
  repoName: string;
  sha: string;
  status: ScanStatus;
  progress: number;
}

export interface RepoHealth {
  name: string;
  score: number;
}

export interface TrendPoint {
  month: string;
  score: number;
}

export interface DashboardData {
  activeScans: number;
  newHighCritical: number;
  cleanPrs: number;
  failedScans: number;
  queue: QueueItem[];
  healthTrend: TrendPoint[];
  severity: Record<Severity, number>;
  recentRepos: RepoHealth[];
}
export type PolicyMode = 'report' | 'warn' | 'enforce';

export interface PolicyRule {
  id: string;
  text: string;
  enabled: boolean;
  locked: boolean;
}

export interface PolicyData {
  mode: PolicyMode;
  rules: PolicyRule[];
}

export type LandingPage = 'dashboard' | 'repositories' | 'scans' | 'findings';
export type Density = 'comfortable' | 'compact';
export type DateFormatKey = 'YYYY-MM-DD' | 'DD/MM/YYYY' | 'MM/DD/YYYY';
export type TimeFormatKey = '24h' | '12h';

export interface ScanTriggers {
  pr_opened: boolean;
  pr_synchronize: boolean;
  pr_reopened: boolean;
  push: boolean;
}

export interface ScanConfig {
  triggers: ScanTriggers;
  scanners: string[];
  timeout_seconds: number;
  concurrency: number;
  scheduled: {
    enabled: boolean;
    frequency: 'daily' | 'weekly';
    time: string;
    last_run?: string | null;
    last_reason?: string | null;
    next_run?: string | null;
  };
  branches: string[];
}

export interface WorkspaceSettings {
  name: string;
  scan: ScanConfig;
  updated_at: string | null;
}

export interface NotificationSettings {
  events: Record<string, boolean>;
  channels: { in_app: boolean; email: boolean };
  digest: 'immediate' | 'daily' | 'weekly';
  quiet_hours: { enabled: boolean; start: string; end: string };
}

export interface UserPreferences {
  display_name: string;
  landing_page: LandingPage;
  language: string;
  date_format: DateFormatKey;
  time_format: TimeFormatKey;
  timezone: string;
  auto_refresh: boolean;
  refresh_interval: number;
  page_size: number;
  density: Density;
  reduce_motion: boolean;
  notifications: NotificationSettings;
}

export interface WorkspaceMember {
  id: number;
  email: string;
  role: string;
  status: string;
  invited_at: string | null;
  created_at: string | null;
  is_registered: boolean;
}

export interface ApiTokenInfo {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string | null;
  last_used_at: string | null;
  expires_at: string | null;
  revoked: boolean;
  revoked_at: string | null;
}

export interface WebhookInfo {
  id: number;
  name: string;
  url: string;
  events: string[];
  enabled: boolean;
  created_at: string | null;
  last_delivery_at: string | null;
  last_delivery_status: string | null;
}

export interface RoleInfo {
  role: string;
  label: string;
  capabilities: string[];
}

export interface GitHubIntegration {
  connected: boolean;
  account: string | null;
  source: 'settings' | 'environment' | 'none';
  oauth_configured: boolean;
  oauth_authorize_url: string | null;
  permissions: string[];
  webhook_secret_configured: boolean;
  last_event_at: string | null;
  last_event_action: string | null;
  last_event_resource: string | null;
  repositories: { id: number; name: string; url: string }[];
}

export interface SettingsPayload {
  workspace: WorkspaceSettings;
  user: UserPreferences;
  account: {
    id: number;
    username: string;
    email: string;
    role: string;
    member_since: string | null;
  };
  members: WorkspaceMember[];
  tokens: ApiTokenInfo[];
  webhooks: WebhookInfo[];
  notifications: NotificationRecord[];
  roles: RoleInfo[];
  integrations: {
    github: GitHubIntegration;
    webhook_events: { id: string; label: string }[];
  };
  server: {
    version: string;
    api_version: string;
    scanner: { id: string; name: string; description: string };
    email: { configured: boolean; host: string | null; port: number; from_address: string; security: string };
    email_configured: boolean;
    two_factor_available: boolean;
    scheduled_scans_available: boolean;
    scheduler_tick_seconds: number;
    api_base: string;
  };
}

export interface NotificationRecord {
  id: number;
  event: string;
  subject: string;
  status: string;
  detail: string | null;
  created_at: string | null;
  sent_at: string | null;
  scheduled_for: string | null;
}