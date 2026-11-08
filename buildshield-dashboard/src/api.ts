import type { Repository, Scan, Finding, DashboardData, PolicyData } from './types';

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

const repositories: Repository[] = [
  { id: 'r1', name: 'acme/payment-service', branch: 'main', manifests: ['requirements.txt', 'poetry.lock'], latestScanStatus: 'succeeded' },
  { id: 'r2', name: 'acme/web-dashboard',   branch: 'main', manifests: ['package-lock.json', 'yarn.lock'],   latestScanStatus: 'succeeded' },
  { id: 'r3', name: 'acme/auth-worker',     branch: 'main', manifests: ['requirements.txt', 'pipfile'],      latestScanStatus: 'timed_out' },
  { id: 'r4', name: 'acme/data-ingestor',   branch: 'main', manifests: ['poetry.lock', 'pyproject.toml'],    latestScanStatus: 'partial' },
];

const scans: Scan[] = [
  { id: '#1042', repoName: 'github.com/org/repo-a', prTitle: 'PR #142: Bump cryptography', baseSha: 'a1b2c3d', headSha: 'f9e8d7c', engine: 'osv-scanner v1.9.0', status: 'succeeded', highCount: 2, durationSeconds: 72 },
  { id: '#1041', repoName: 'github.com/org/repo-a', prTitle: 'PR #142: Bump cryptography', baseSha: 'e5f6g7h', headSha: 'i9j8k7l', engine: 'osv-scanner v1.9.0', status: 'running',   highCount: 0, durationSeconds: 45 },
  { id: '#1040', repoName: 'github.com/org/repo-b', prTitle: 'PR #89: Update PyJWT',       baseSha: 'e5f6g7h', headSha: 'i9j8k7l', engine: 'osv-scanner v1.9.0', status: 'timed_out', highCount: 0, durationSeconds: 303 },
  { id: '#1039', repoName: 'github.com/org/repo-b', prTitle: 'PR #89: Update PyJWT',       baseSha: 'e5f6g7h', headSha: 'i9j8k7l', engine: 'osv-scanner v1.9.0', status: 'partial',   highCount: 2, durationSeconds: 12 },
  { id: '#1038', repoName: 'github.com/org/repo-a', prTitle: 'PR #142: Bump cryptography', baseSha: 'a1b2c3d', headSha: 'f9e8d7c', engine: 'osv-scanner v1.9.0', status: 'succeeded', highCount: 0, durationSeconds: 12 },
];

const findings: Finding[] = [
  { id: 'f1', packageName: 'urllib3', currentVersion: '1.26.4', fixedVersion: '1.26.19', severity: 'high', change: 'new', reviewStatus: 'open', advisoryId: 'GHSA-34jh-p97f-mpxf', filePath: 'services/api/requirements.txt', priorityReason: 'High-severity advisory introduced in head commit; fixed version 1.26.19 available', scanner: 'osv-scanner', fingerprint: 'sha256:8f9d2a41c7' },
  { id: 'f2', packageName: 'pyjwt', currentVersion: '2.3.0', fixedVersion: '2.4.0', severity: 'high', change: 'new', reviewStatus: 'open', advisoryId: 'GHSA-ffqj-6fqr-9h24', filePath: 'services/auth/requirements.txt', priorityReason: 'High-severity advisory introduced in head commit; fixed version 2.4.0 available', scanner: 'osv-scanner', fingerprint: 'sha256:3c71be90d2' },
  { id: 'f3', packageName: 'requests', currentVersion: '2.25.0', fixedVersion: '2.31.0', severity: 'medium', change: 'existing', reviewStatus: 'open', advisoryId: 'GHSA-sample-0001', filePath: 'services/api/requirements.txt', priorityReason: 'Medium-severity advisory already present in the base branch; warn only', scanner: 'osv-scanner', fingerprint: 'sha256:a10b55e6f3' },
  { id: 'f4', packageName: 'django', currentVersion: '3.2.0', fixedVersion: '3.2.25', severity: 'critical', change: 'existing', reviewStatus: 'open', advisoryId: 'GHSA-sample-0002', filePath: 'services/web/requirements.txt', priorityReason: 'Critical advisory already present in the base branch; fixed version 3.2.25 available', scanner: 'osv-scanner', fingerprint: 'sha256:5d2e88a1b9' },
  { id: 'f5', packageName: 'jinja2', currentVersion: '2.11.0', fixedVersion: '3.1.3', severity: 'medium', change: 'existing', reviewStatus: 'dismissed', advisoryId: 'GHSA-sample-0003', filePath: 'services/web/requirements.txt', priorityReason: 'Medium-severity advisory already present in the base branch; warn only', scanner: 'osv-scanner', fingerprint: 'sha256:e7940c2d18' },
  { id: 'f6', packageName: 'pyyaml', currentVersion: '5.3', fixedVersion: null, severity: 'low', change: 'existing', reviewStatus: 'open', advisoryId: 'GHSA-sample-0004', filePath: 'services/worker/requirements.txt', priorityReason: 'Low-severity advisory already present in the base branch; no fixed version yet', scanner: 'osv-scanner', fingerprint: 'sha256:0b6a3f77c4' },
  { id: 'f7', packageName: 'flask', currentVersion: '1.0.0', fixedVersion: '2.2.5', severity: 'high', change: 'resolved', reviewStatus: 'open', advisoryId: 'GHSA-sample-0005', filePath: 'services/api/requirements.txt', priorityReason: 'High-severity advisory fixed by this pull request', scanner: 'osv-scanner', fingerprint: 'sha256:92c4d5e1a0' },
];

export async function getRepositories(): Promise<Repository[]> {
  return await fetchFromAPI('/api/v1/repositories/');
}
export async function getScans(): Promise<Scan[]> {
  return await fetchFromAPI('/api/v1/scans/');
}
export async function getFindings(): Promise<Finding[]> {
  return await fetchFromAPI('/api/v1/findings/');
}

const dashboard: DashboardData = {
  activeScans: 4,
  newHighCritical: 7,
  cleanPrs: 142,
  failedScans: 2,
  queue: [
    { id: 'q1', prNumber: 142, title: 'Bump cryptography', repoName: 'acme/payment-service', sha: 'sha-a9b1c', status: 'running', progress: 20 },
    { id: 'q2', prNumber: 89, title: 'Update PyJWT', repoName: 'acme/auth-service', sha: 'sha-a9b1c', status: 'running', progress: 35 },
    { id: 'q3', prNumber: 204, title: 'Upgrade urllib3', repoName: 'acme/web-client', sha: 'sha-a9b1c', status: 'succeeded', progress: 100 },
    { id: 'q4', prNumber: 12, title: 'Fix dependencies', repoName: 'acme/payment-service', sha: 'sha-a9b1c', status: 'timed_out', progress: 62 },
    { id: 'q5', prNumber: 54, title: 'Update Django', repoName: 'acme/web-client', sha: 'sha-a9b1c', status: 'succeeded', progress: 100 },
    { id: 'q6', prNumber: 33, title: 'Add validation', repoName: 'acme/auth-service', sha: 'sha-a9b1c', status: 'succeeded', progress: 100 },
  ],
  healthTrend: [
    { month: 'Jan', score: 82 },
    { month: 'Feb', score: 79 },
    { month: 'Mar', score: 85 },
    { month: 'Apr', score: 83 },
    { month: 'May', score: 88 },
  ],
  severity: { critical: 1, high: 6, medium: 9, low: 4 },
  recentRepos: [
    { name: 'acme/payment-service', score: 75 },
    { name: 'acme/auth-service', score: 96 },
    { name: 'acme/web-client', score: 85.5 },
    { name: 'acme/data-ingestor', score: 93 },
  ],
};

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

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export async function fetchFromAPI(endpoint: string, options: RequestInit = {}) {
    const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
    const url = `${API_BASE}${path}`;
    
    const token = localStorage.getItem('buildshield_token');
    
    // Set up headers, merging any custom headers passed in
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> || {}),
    };

    // If we have a token, attach it
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(url, {
            ...options,
            headers,
        });

        if (response.status === 401) {
            // Token expired or invalid
            localStorage.removeItem('buildshield_token');
            window.location.href = '/login'; 
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error("Failed to fetch from API:", error);
        throw error;
    }
}

export async function loginUser(email: string, password: string) {
    const formData = new URLSearchParams();
    formData.append('username', email); // FastAPI OAuth2 expects the key to be 'username'
    formData.append('password', password);

    const response = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
    });

    if (!response.ok) {
        throw new Error('Invalid credentials');
    }

    const data = await response.json();
    // Save the access token to the browser
    localStorage.setItem('buildshield_token', data.access_token);
    return data;
}

export function logoutUser() {
    localStorage.removeItem('buildshield_token');
    window.location.href = '/login';
}

export async function addRepository(data: { name: string; url: string; branch: string }) {
    return await fetchFromAPI('/api/v1/repositories/', {
        method: 'POST',
        body: JSON.stringify(data),
    });
}

export async function triggerScan(repositoryId: string | number) {
    return await fetchFromAPI('/api/v1/scans/', {
        method: 'POST',
        body: JSON.stringify({ 
            repository_id: repositoryId,
            commit_hash: "HEAD" 
        }),
    });
}