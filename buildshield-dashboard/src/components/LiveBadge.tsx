export default function LiveBadge({ label = 'Live' }: { label?: string }) {
  return (
    <span className="live-chip" title="This view refreshes automatically">
      <span className="live-dot" aria-hidden="true" />
      {label}
    </span>
  );
}
