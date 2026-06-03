import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register({ display_name: displayName, email, password });
      navigate("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bg-900 flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Branding */}
        <div className="mb-8 text-center">
          <h1 className="font-mono text-lg font-semibold text-text-primary tracking-tight">
            QuantFidelity
          </h1>
          <p className="mt-1 font-mono text-xs text-text-muted uppercase tracking-widest">
            Quant research reliability platform
          </p>
        </div>

        {/* Card */}
        <div className="rounded-lg border border-border bg-bg-800 p-6">
          <div className="mb-5">
            <h2 className="font-mono text-sm font-semibold text-text-primary">
              Create account
            </h2>
            <p className="mt-0.5 font-mono text-xs text-text-muted">
              Set up your local workspace credentials
            </p>
          </div>

          {error && (
            <div className="mb-4 rounded border border-fidelity-low/40 bg-fidelity-low/10 px-3 py-2">
              <p className="font-mono text-xs text-fidelity-low">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block font-mono text-xs text-text-muted uppercase tracking-widest mb-1.5">
                Display Name
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                autoComplete="name"
                placeholder="Jane Quant"
                className="w-full rounded border border-border bg-bg-700 px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>

            <div>
              <label className="block font-mono text-xs text-text-muted uppercase tracking-widest mb-1.5">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
                className="w-full rounded border border-border bg-bg-700 px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>

            <div>
              <label className="block font-mono text-xs text-text-muted uppercase tracking-widest mb-1.5">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="••••••••"
                className="w-full rounded border border-border bg-bg-700 px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded bg-brand px-4 py-2 font-mono text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>

          <p className="mt-4 text-center font-mono text-xs text-text-muted">
            Already have an account?{" "}
            <Link to="/login" className="text-brand hover:underline">
              Sign in
            </Link>
          </p>
        </div>

        {/* Footer note */}
        <p className="mt-4 text-center font-mono text-2xs text-text-muted">
          No verification email. Local development account.
        </p>
      </div>
    </div>
  );
}
