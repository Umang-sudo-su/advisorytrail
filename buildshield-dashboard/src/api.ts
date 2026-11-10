import type { Repository, Scan, Finding, DashboardData, PolicyData } from './types';
import { getApiBase, getDefaultCommitRef } from './settings';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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

const policies: PolicyData = {
  mode: 'enforce',
  rules: [
    { id: 'block-new', text: 'Rule 1: New Critical/High Vulnerability with Fixed Version -> BLOCK PR Check Run', enabled: true, locked: false },
    { id: 'warn-existing', text: 'Rule 2: Pre-existing Vulnerability in Baseline -> WARN ONLY', enabled: true, locked: false },
    { id: 'incomplete', text: 'Rule 3: Failed or Timed-Out Scan -> INCOMPLETE CHECK (Never mark clean)', enabled: true, locked: true },
  ],
};

export async function getPolicies(): Promise<PolicyData> {
  await wait(600);
  return policies;
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

export async function loginUser(identifier: string, password: string): Promise<string> {
    const formData = new URLSearchParams();
    formData.append('username', identifier); // FastAPI OAuth2 form field (username or email)
    formData.append('password', password);

    const response = await postAuthRequest('/api/v1/auth/login', formData, 'application/x-www-form-urlencoded');
    const data = await response.json();

    if (!data?.access_token) {
        throw new Error('The API did not return an access token.');
    }

    return data.access_token as string;
}

export async function registerUser(payload: { username: string; email: string; password: string }): Promise<AuthUser> {
    const response = await postAuthRequest('/api/v1/auth/register', JSON.stringify(payload), 'application/json');
    return await response.json();
}

export async function getCurrentUser(): Promise<AuthUser> {
    return await fetchFromAPI('/api/v1/auth/me');
}

export async function addRepository(data: { name: string; url: string; branch: string }) {
    return await fetchFromAPI('/api/v1/repositories/', {
        method: 'POST',
        body: JSON.stringify(data),
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