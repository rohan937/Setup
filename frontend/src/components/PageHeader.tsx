import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  tag?: string;        // optional monospace category tag, e.g. "RESEARCH"
  children?: ReactNode;
}

export default function PageHeader({ title, subtitle, tag, children }: PageHeaderProps) {
  return (
    <div className="mb-7 flex items-start justify-between gap-4">
      <div>
        {tag && <p className="caption mb-1.5">{tag}</p>}
        <h1 className="text-xl font-semibold tracking-tight text-text-primary">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-text-secondary">{subtitle}</p>
        ) : null}
      </div>
      {children ? <div className="shrink-0 pt-0.5">{children}</div> : null}
    </div>
  );
}
