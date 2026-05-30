interface EmptyStateProps {
  title: string;
  description: string;
}

export default function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-card border border-dashed border-border bg-bg-800 px-6 py-16 text-center">
      <div className="mb-4 h-8 w-8 rounded-control border border-border-strong" />
      <p className="text-sm font-medium text-text-primary">{title}</p>
      <p className="mt-1 max-w-md text-sm text-text-secondary">{description}</p>
    </div>
  );
}
