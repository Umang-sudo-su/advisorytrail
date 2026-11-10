export default function StatusBadge({ status }: { status?: string }) {
  const safeStatus = (status || 'unknown').toLowerCase();

  const statusMap: Record<string, { label: string; className: string }> = {
    success: { label: 'Success', className: 'badge-ok' },
    completed: { label: 'Completed', className: 'badge-ok' },
    passed: { label: 'Passed', className: 'badge-ok' },
    failed: { label: 'Failed', className: 'badge-bad' },
    error: { label: 'Error', className: 'badge-bad' },
    timed_out: { label: 'Timed Out', className: 'badge-bad' },
    running: { label: 'Running', className: 'badge-warn' },
    pending: { label: 'Pending', className: 'badge-warn' },
    queued: { label: 'Queued', className: 'badge-warn' },
    unknown: { label: 'Unknown', className: 'badge-muted' },
  };

  const config = statusMap[safeStatus] || { label: status || 'Unknown', className: 'badge-muted' };

  return <span className={`badge ${config.className}`}>{config.label}</span>;
}
