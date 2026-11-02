export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <p className="state" role="status">
      {label}...
    </p>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="state state-error" role="alert">
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
      <p className="state-title">{title}</p>
      {hint && <p>{hint}</p>}
    </div>
  );
}