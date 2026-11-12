import { CircleCheck, LoaderCircle, TriangleAlert } from 'lucide-react';

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="state" role="status">
      <LoaderCircle size={22} className="spin" aria-hidden="true" />
      <p>{label}…</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state state-error" role="alert">
      <TriangleAlert size={22} aria-hidden="true" />
      <p>{message}</p>
      <button type="button" className="btn" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="state">
      <CircleCheck size={22} aria-hidden="true" />
      <p className="state-title">{title}</p>
      {hint && <p>{hint}</p>}
    </div>
  );
}
