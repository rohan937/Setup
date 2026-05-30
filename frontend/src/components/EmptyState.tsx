interface EmptyStateProps {
  title: string;
  description: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border bg-bg-800 px-6 py-14 text-center">
      {/* Terminal cursor placeholder */}
      <div className="mb-5 flex items-center gap-1 font-mono text-xs text-text-muted">
        <span className="text-accent-500">$</span>
        <span className="opacity-50">_</span>
      </div>
      <p className="text-sm font-medium text-text-secondary">{title}</p>
      <p className="mt-1.5 max-w-sm font-mono text-2xs leading-relaxed text-text-muted">
        {description}
      </p>
    </div>
  );
}
