// M102 skeleton primitives — visual-only shimmer placeholders.
// Respect prefers-reduced-motion via the global guard in index.css.

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

export function SkeletonText({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-3" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function SkeletonCard({ className = "" }: { className?: string }) {
  return (
    <div className={`rounded-card border border-border bg-bg-700 p-6 ${className}`} aria-hidden="true">
      <div className="skeleton mb-3 h-3 w-1/3" />
      <div className="skeleton mb-4 h-9 w-1/2" />
      <div className="skeleton h-3 w-full" />
    </div>
  );
}

export default Skeleton;
