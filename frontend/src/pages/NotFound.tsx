import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <p className="mono-num text-sm text-text-muted">404</p>
      <p className="mt-2 text-base font-medium text-text-primary">
        Page not found
      </p>
      <Link
        to="/"
        className="mt-4 text-sm text-accent-500 hover:text-accent-300"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
