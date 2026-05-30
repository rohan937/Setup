interface PageHeaderProps {
  title: string;
  subtitle?: string;
}

export default function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
        {title}
      </h1>
      {subtitle ? (
        <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>
      ) : null}
    </div>
  );
}
