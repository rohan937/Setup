interface ScoreCardProps {
  label: string;
}

// M1 placeholder: scores are not computed yet, so the value renders as a muted
// em-dash rather than fabricated data. The score bar is shown empty.
export default function ScoreCard({ label }: ScoreCardProps) {
  return (
    <div className="rounded-card border border-border bg-bg-700 p-5">
      <p className="caption mb-3">{label}</p>
      <p className="mono-num text-3xl font-semibold text-text-muted">—</p>
      <div className="mt-4 h-1.5 w-full overflow-hidden rounded-full bg-bg-600">
        <div className="h-full w-0 bg-border-strong" />
      </div>
      <p className="mt-2 text-xs text-text-muted">No data yet</p>
    </div>
  );
}
