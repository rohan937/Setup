import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  tag?: string;        // optional monospace category tag, e.g. "RESEARCH"
  children?: ReactNode;
}

export default function PageHeader({ title, subtitle, tag, children }: PageHeaderProps) {
  return (
    <div className="mb-8 flex items-start justify-between gap-4">
      <div>
        {tag && <p className="caption mb-2">{tag}</p>}
        <h1 className="page-title">{title}</h1>
        {subtitle ? (
          <p className="mt-2 max-w-2xl text-base leading-relaxed text-text-secondary">{subtitle}</p>
        ) : null}
      </div>
      {children ? <div className="shrink-0 pt-1">{children}</div> : null}
    </div>
  );
}
