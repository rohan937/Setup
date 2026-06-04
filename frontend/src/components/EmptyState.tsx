interface EmptyStateProps {
  title: string;
  description: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border bg-bg-800/60 px-6 py-16 text-center">
      {/* Restrained terminal cursor mark */}
      <div className="mb-5 flex items-center gap-1 font-mono text-xs text-text-muted">
        <span className="text-accent-500/80">$</span>
        <span className="opacity-40">_</span>
      </div>
      <p className="text-sm font-medium text-text-primary">{title}</p>
      <p className="mt-2 max-w-sm text-2xs leading-relaxed text-text-muted">
        {description}
      </p>
    </div>
  );
}
