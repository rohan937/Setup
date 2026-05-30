interface ScoreCardProps {
  label: string;
  description?: string;
}

export default function ScoreCard({ label, description }: ScoreCardProps) {
  return (
    <div className="rounded-card border border-border bg-bg-700 px-4 py-3">
      <p className="caption mb-2">{label}</p>
      <div className="flex items-baseline gap-2">
        <p className="mono-num text-2xl font-semibold text-text-muted">—</p>
        <p className="font-mono text-2xs text-text-muted">/100</p>
      </div>
      {/* Score bar */}
      <div className="my-2.5 h-px w-full bg-border" />
      <p className="font-mono text-2xs text-text-muted">
        {description ?? "No runs measured"}
      </p>
    </div>
  );
}
