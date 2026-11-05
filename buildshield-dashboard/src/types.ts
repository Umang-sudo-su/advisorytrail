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
  manifests: string[];
  latestScanStatus: ScanStatus;
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