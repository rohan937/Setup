import { useState, FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { resendVerification } from "@/lib/api";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  const [resending, setResending] = useState(false);
  const [resendResult, setResendResult] = useState<"sent" | "failed" | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await register({ display_name: displayName, email, password });
      // M84: the user is now authenticated but their email is unverified.
      // Show a "check your email" view instead of navigating immediately.
      setRegistered(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setResendResult(null);
    try {
      await resendVerification();
      setResendResult("sent");
    } catch {
      setResendResult("failed");
    } finally {
      setResending(false);
    }
  };

  if (registered) {
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
            <h2 className="font-mono text-sm font-semibold text-text-primary mb-2">
              Check your email
            </h2>
            <p className="font-mono text-xs text-text-muted mb-5">
              We sent a verification link to{" "}
              <span className="text-text-secondary">{email}</span>. Click the link
              to verify your email and unlock all features.
            </p>

            <button
              type="button"
              onClick={() => void handleResend()}
              disabled={resending}
              className="w-full rounded border border-border bg-bg-700 px-4 py-2 font-mono text-sm text-text-primary hover:border-brand hover:text-brand disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {resending ? "Sending…" : "Resend verification email"}
            </button>
            {resendResult === "sent" && (
              <p className="mt-2 font-mono text-2xs text-green-400">
                Verification email sent ✓
              </p>
            )}
            {resendResult === "failed" && (
              <p className="mt-2 font-mono text-2xs text-fidelity-low">
                Could not send verification email. Please try again.
              </p>
            )}

            <button
              type="button"
              onClick={() => navigate("/")}
              className="mt-3 w-full rounded bg-brand px-4 py-2 font-mono text-sm font-semibold text-white hover:bg-brand/90 transition-colors"
            >
              Continue to dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

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
