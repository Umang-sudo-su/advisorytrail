import type {
  Repository,
  Scan,
  Finding,
  DashboardData,
  PolicyData,
  SettingsPayload,
  UserPreferences,
  WorkspaceSettings,
  ScanConfig,
  WorkspaceMember,
  ApiTokenInfo,
  WebhookInfo,
} from './types';
import { getApiBase, getDefaultCommitRef } from './settings';

export async function getRepositories(): Promise<Repository[]> {
  return await fetchFromAPI('/api/v1/repositories/');
}
export async function getScans(): Promise<Scan[]> {
  return await fetchFromAPI('/api/v1/scans/');
}
export async function getFindings(): Promise<Finding[]> {
  return await fetchFromAPI('/api/v1/findings/');
}

export async function getDashboard(): Promise<DashboardData> {
  // Your backend calls this 'stats' instead of 'dashboard'
  return await fetchFromAPI('/api/v1/stats/'); 
}

export async function getPolicies(): Promise<PolicyData> {
  return await fetchFromAPI('/api/v1/policies/');
}

/** Persists the Policies page settings; the server records the change in the audit trail. */
export async function savePolicies(policy: PolicyData): Promise<PolicyData> {
  return await fetchFromAPI('/api/v1/policies/', {
    method: 'PUT',
    body: JSON.stringify({
      mode: policy.mode,
      rules: policy.rules.map(({ id, enabled }) => ({ id, enabled })),
    }),
  });
}

export async function getSettings(): Promise<SettingsPayload> {
  return await fetchFromAPI('/api/v1/settings/');
}

export async function saveWorkspaceSettings(payload: {
  name?: string;
  scan?: Partial<ScanConfig>;
}): Promise<{ workspace: WorkspaceSettings }> {
  return await fetchFromAPI('/api/v1/settings/workspace', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function saveUserPreferences(
  patch: Partial<UserPreferences>,
): Promise<{ user: UserPreferences }> {
  return await fetchFromAPI('/api/v1/settings/user', {
    method: 'PUT',
    body: JSON.stringify(patch),
  });
}

export async function sendTestNotification(): Promise<{ delivered: boolean; detail: string }> {
  return await fetchFromAPI('/api/v1/settings/notifications/test', { method: 'POST' });
}

export async function inviteMember(
  email: string,
  role: string,
): Promise<{ member: WorkspaceMember; email_sent: boolean; note: string }> {
  return await fetchFromAPI('/api/v1/settings/members', {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
}

export async function updateMemberRole(
  memberId: number,
  role: string,
): Promise<{ member: WorkspaceMember }> {
  return await fetchFromAPI(`/api/v1/settings/members/${memberId}`, {
    method: 'PATCH',
    body: JSON.stringify({ role }),
  });
}

export async function removeMember(memberId: number): Promise<void> {
  await fetchFromAPI(`/api/v1/settings/members/${memberId}`, { method: 'DELETE' });
}

export async function createApiToken(
  name: string,
  expiresInDays: number | null,
  scopes: string[] = ['read', 'write'],
): Promise<{ token: ApiTokenInfo; secret: string; note: string }> {
  return await fetchFromAPI('/api/v1/settings/tokens', {
    method: 'POST',
    body: JSON.stringify({ name, expires_in_days: expiresInDays, scopes }),
  });
}

export async function revokeApiToken(tokenId: number): Promise<void> {
  await fetchFromAPI(`/api/v1/settings/tokens/${tokenId}`, { method: 'DELETE' });
}

export async function createWebhook(
  name: string,
  url: string,
  events: string[],
): Promise<{ webhook: WebhookInfo; secret: string; note: string }> {
  return await fetchFromAPI('/api/v1/settings/webhooks', {
    method: 'POST',
    body: JSON.stringify({ name, url, events }),
  });
}

export async function updateWebhook(
  webhookId: number,
  patch: { name?: string; url?: string; events?: string[]; enabled?: boolean },
): Promise<{ webhook: WebhookInfo }> {
  return await fetchFromAPI(`/api/v1/settings/webhooks/${webhookId}`, {
    method: 'PATCH',
    body: JSON.stringify(patch),
  });
}

export async function deleteWebhook(webhookId: number): Promise<void> {
  await fetchFromAPI(`/api/v1/settings/webhooks/${webhookId}`, { method: 'DELETE' });
}

export async function testWebhook(
  webhookId: number,
): Promise<{ delivered: boolean; detail: string; webhook: WebhookInfo }> {
  return await fetchFromAPI(`/api/v1/settings/webhooks/${webhookId}/test`, { method: 'POST' });
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  await fetchFromAPI('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export const TOKEN_KEY = 'buildshield_token';
export const UNAUTHORIZED_EVENT = 'buildshield:unauthorized';

/**
 * Session tokens live in sessionStorage, so signing in once lasts for the whole
 * browser session. "Keep me signed in" upgrades the token to localStorage.
 */
export function getStoredToken(): string | null {
    return sessionStorage.getItem(TOKEN_KEY) ?? localStorage.getItem(TOKEN_KEY);
}

export function storeToken(token: string, remember = false) {
    clearStoredToken();
    const storage = remember ? localStorage : sessionStorage;
    storage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken() {
    sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
}

async function readErrorMessage(response: Response): Promise<string> {
    try {
        const data = await response.json();
        if (typeof data?.detail === 'string') return data.detail;
        if (Array.isArray(data?.detail)) {
            const messages = data.detail
                .map((item: { msg?: string }) => item?.msg)
                .filter(Boolean);
            if (messages.length > 0) return messages.join(', ');
        }
    } catch {
        // Response body was not JSON; fall through to the generic message.
    }
    return `Request failed (${response.status})`;
}

export async function fetchFromAPI(endpoint: string, options: RequestInit = {}) {
    const base = getApiBase();
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${base}${path}`;

    const token = getStoredToken();

    // Set up headers, merging any custom headers passed in
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> || {}),
    };

    // If we have a token, attach it
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    let response: Response;
    try {
        response = await fetch(url, {
            ...options,
            headers,
        });
    } catch {
        throw new Error(`Cannot reach the BuildShield API at ${base}. Check that the backend is running.`);
    }

    if (response.status === 401) {
        // Token expired or invalid: drop it and let AuthContext show the login page again.
        clearStoredToken();
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
        throw new Error('Unauthorized');
    }

    if (!response.ok) {
        throw new Error(await readErrorMessage(response));
    }

    if (response.status === 204) return null;
    return await response.json();
}

export interface AuthUser {
    id: number;
    username: string;
    email: string;
    is_active: boolean;
}

async function postAuthRequest(path: string, body: BodyInit, contentType: string): Promise<Response> {
    const base = getApiBase();
    let response: Response;
    try {
        response = await fetch(`${base}${path}`, {
            method: 'POST',
            headers: { 'Content-Type': contentType },
            body,
        });
    } catch {
        throw new Error(`Cannot reach the BuildShield API at ${base}. Check that the backend is running.`);
    }

    if (!response.ok) {
        throw new Error(await readErrorMessage(response));
    }

    return response;
}

export type LoginResult =
    | { kind: 'session'; token: string }
    | { kind: '2fa'; challengeToken: string };

export async function loginUser(identifier: string, password: string): Promise<LoginResult> {
    const formData = new URLSearchParams();
    formData.append('username', identifier); // FastAPI OAuth2 form field (username or email)
    formData.append('password', password);

    const response = await postAuthRequest('/api/v1/auth/login', formData, 'application/x-www-form-urlencoded');
    const data = await response.json();

    if (data?.requires_2fa && data?.challenge_token) {
        return { kind: '2fa', challengeToken: data.challenge_token as string };
    }

    if (!data?.access_token) {
        throw new Error('The API did not return an access token.');
    }

    return { kind: 'session', token: data.access_token as string };
}

export async function verifyTwoFactor(challengeToken: string, code: string): Promise<string> {
    const data = await fetchFromAPI('/api/v1/auth/2fa/verify', {
        method: 'POST',
        body: JSON.stringify({ challenge_token: challengeToken, code }),
    });
    if (!data?.access_token) throw new Error('The API did not return an access token.');
    return data.access_token as string;
}

export interface TwoFactorStatus {
    enabled: boolean;
    recovery_codes_remaining: number;
}

export async function getTwoFactorStatus(): Promise<TwoFactorStatus> {
    return await fetchFromAPI('/api/v1/auth/2fa/status');
}

export interface TwoFactorSetup {
    secret: string;
    otpauth_uri: string;
    digits: number;
    period: number;
}

export async function setupTwoFactor(): Promise<TwoFactorSetup> {
    return await fetchFromAPI('/api/v1/auth/2fa/setup', { method: 'POST' });
}

export async function enableTwoFactor(code: string): Promise<{ recovery_codes: string[] }> {
    return await fetchFromAPI('/api/v1/auth/2fa/enable', {
        method: 'POST',
        body: JSON.stringify({ code }),
    });
}

export async function disableTwoFactor(password: string): Promise<void> {
    await fetchFromAPI('/api/v1/auth/2fa/disable', {
        method: 'POST',
        body: JSON.stringify({ password }),
    });
}

export interface SessionInfo {
    id: number;
    jti: string;
    user_agent: string | null;
    ip_address: string | null;
    created_at: string | null;
    last_seen_at: string | null;
    revoked_at: string | null;
    current: boolean;
}

export async function getSessions(): Promise<SessionInfo[]> {
    return await fetchFromAPI('/api/v1/auth/sessions');
}

export async function revokeSession(sessionId: number): Promise<void> {
    await fetchFromAPI(`/api/v1/auth/sessions/${sessionId}`, { method: 'DELETE' });
}

export async function revokeOtherSessions(): Promise<{ revoked: number }> {
    return await fetchFromAPI('/api/v1/auth/sessions/revoke-others', { method: 'POST' });
}

export async function logoutSession(): Promise<void> {
    await fetchFromAPI('/api/v1/auth/logout', { method: 'POST' });
}

export async function connectGitHub(token: string): Promise<{ github: { account: string | null } }> {
    return await fetchFromAPI('/api/v1/settings/github/connect', {
        method: 'POST',
        body: JSON.stringify({ token }),
    });
}

export async function disconnectGitHub(): Promise<void> {
    await fetchFromAPI('/api/v1/settings/github/disconnect', { method: 'POST' });
}

export async function runScheduledScansNow(): Promise<{
    queued: { scan_id: number; repository: string; branch: string }[];
}> {
    return await fetchFromAPI('/api/v1/settings/scan/schedule/run', { method: 'POST' });
}

export interface NotificationInfo {
    id: number;
    event: string;
    subject: string;
    status: string;
    detail: string | null;
    created_at: string | null;
    sent_at: string | null;
    scheduled_for: string | null;
}

export async function getNotificationLog(): Promise<NotificationInfo[]> {
    return await fetchFromAPI('/api/v1/settings/notifications');
}

export async function registerUser(payload: { username: string; email: string; password: string }): Promise<AuthUser> {
    const response = await postAuthRequest('/api/v1/auth/register', JSON.stringify(payload), 'application/json');
    return await response.json();
}

export async function getCurrentUser(): Promise<AuthUser> {
    return await fetchFromAPI('/api/v1/auth/me');
}

export interface ConnectedRepository {
    id: number;
    name: string;
    url: string;
    branch: string;
    private: boolean;
    created_at: string;
}

export async function addRepository(data: { name: string; url: string; branch: string }): Promise<ConnectedRepository> {
    return await fetchFromAPI('/api/v1/repositories/', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export async function updateFindingStatus(
    findingId: string | number,
    status: 'OPEN' | 'DISMISSED' | 'FALSE_POSITIVE',
): Promise<{ id: number; status: string }> {
    return await fetchFromAPI(`/api/v1/findings/${findingId}`, {
        method: 'PATCH',
        body: JSON.stringify({ status }),
    });
}

export async function bulkUpdateFindingStatus(
    findingIds: Array<string | number>,
    status: 'OPEN' | 'DISMISSED' | 'FALSE_POSITIVE',
): Promise<{ updated: number; status: string; ids: number[] }> {
    return await fetchFromAPI('/api/v1/findings/bulk', {
        method: 'PATCH',
        body: JSON.stringify({ ids: findingIds, status }),
    });
}

export interface ScanStatusResult {
    id: number;
    repository_id: number;
    status: string;
    created_at: string;
    duration_seconds: number | null;
}

/** Polled by the repository cards while a scan is running. */
export async function getScan(scanId: number): Promise<ScanStatusResult> {
    return await fetchFromAPI(`/api/v1/scans/${scanId}`);
}

export async function triggerScan(repositoryId: string | number, commitRef: string = getDefaultCommitRef()) {
    return await fetchFromAPI('/api/v1/scans/', {
        method: 'POST',
        body: JSON.stringify({
            repository_id: repositoryId,
            commit_hash: commitRef,
        }),
    });
}

export interface AuditLogEntry {
    id: number;
    timestamp: string;
    actor: string;
    action: string;
    resource_id: string;
    justification: string | null;
    category: string;
}

export interface AuditMonitorStats {
    verified_signatures_percentage: string;
    deduplicated_delivery_ids: number;
}

export async function getAuditLogs(
    options: { category?: string; search?: string; limit?: number } = {},
): Promise<AuditLogEntry[]> {
    const params = new URLSearchParams();
    if (options.category && options.category !== 'All Events') {
        params.set('category', options.category);
    }
    if (options.search) {
        params.set('search', options.search);
    }
    params.set('limit', String(options.limit ?? 50));

    return await fetchFromAPI(`/api/v1/audit-logs/?${params.toString()}`);
}

export async function getAuditMonitorStats(): Promise<AuditMonitorStats> {
    return await fetchFromAPI('/api/v1/audit-logs/monitor-stats');
}

export interface HealthStatus {
    status: string;
    database?: string;
}

/** Unauthenticated liveness probe used by the Settings page. */
export async function getHealth(): Promise<HealthStatus> {
    const base = getApiBase();
    let response: Response;
    try {
        response = await fetch(`${base}/health`);
    } catch {
        throw new Error(`Cannot reach the BuildShield API at ${base}.`);
    }

    if (!response.ok) {
        throw new Error(await readErrorMessage(response));
    }

    return await response.json();
}

/** Downloads the audit trail from the API as a file. */
export async function exportAuditLogs(format: 'csv' | 'json'): Promise<{ blob: Blob; filename: string }> {
    const base = getApiBase();
    const token = getStoredToken();

    let response: Response;
    try {
        response = await fetch(`${base}/api/v1/audit-logs/export?format=${format}`, {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
    } catch {
        throw new Error(`Cannot reach the BuildShield API at ${base}.`);
    }

    if (response.status === 401) {
        clearStoredToken();
        window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
        throw new Error('Unauthorized');
    }

    if (!response.ok) {
        throw new Error(await readErrorMessage(response));
    }

    return {
        blob: await response.blob(),
        filename: `buildshield_audit_logs.${format}`,
    };
}