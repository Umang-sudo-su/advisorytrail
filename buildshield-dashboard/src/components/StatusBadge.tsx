import { Clock, LoaderCircle, CircleCheck, TriangleAlert, CircleX } from 'lucide-react';
import type { ScanStatus } from '../types';

const config = {
  queued:    { label: 'Queued',           className: 'badge-queued',  icon: Clock },
  running:   { label: 'Running',          className: 'badge-running', icon: LoaderCircle },
  succeeded: { label: 'Succeeded',        className: 'badge-ok',      icon: CircleCheck },
  partial:   { label: 'Partial',          className: 'badge-warn',    icon: TriangleAlert },
  failed:    { label: 'Failed',           className: 'badge-bad',     icon: CircleX },
  timed_out: { label: 'Failed - Timeout', className: 'badge-bad',     icon: CircleX },
};

export default function StatusBadge({ status }: { status: ScanStatus }) {
  const { label, className, icon: Icon } = config[status];

  return (
    <span className={`badge ${className}`}>
      <Icon
        size={16}
        aria-hidden="true"
        className={status === 'running' ? 'spin' : undefined}
      />
      {label}
    </span>
  );
}