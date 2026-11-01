import type { Repository, Scan, Finding } from './types';

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
  { id: 'f1', packageName: 'urllib3', currentVersion: '1.26.4', fixedVersion: '1.26.19', severity: 'high', change: 'new', reviewStatus: 'open', advisoryId: 'GHSA-34jh-p97f-mpxf', filePath: 'services/api/requirements.txt', priorityReason: 'High-severity advisory introduced in head commit; fixed version 1.26.19 available' },
  { id: 'f2', packageName: 'pyjwt',   currentVersion: '2.3.0', fixedVersion: '2.4.0',  severity: 'high', change: 'new', reviewStatus: 'open', advisoryId: 'GHSA-ffqj-6fqr-9h24', filePath: 'services/auth/requirements.txt', priorityReason: 'High-severity advisory introduced in head commit; fixed version 2.4.0 available' },
];

export async function getRepositories(): Promise<Repository[]> {
  await wait(600);
  return repositories;
}

export async function getScans(): Promise<Scan[]> {
  await wait(600);
  return scans;
}

export async function getFindings(): Promise<Finding[]> {
  await wait(600);
  return findings;
}