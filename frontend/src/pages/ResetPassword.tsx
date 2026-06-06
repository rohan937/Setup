import { useState, FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { resetPassword } from "@/lib/api";

export default function ResetPassword() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [message, setMessage] = useState<string>("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (!token) {
      setError("This password reset link is invalid or has expired.");
      return;
    }

    setLoading(true);
    try {
      const res = await resetPassword(token, newPassword);
      setSuccess(true);
      setMessage(res.message || "Your password has been reset.");
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : "This password reset link is invalid or has expired.",
      );
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
          <h2 className="font-mono text-sm font-semibold text-text-primary mb-5">
            Set a new password
          </h2>

          {!token ? (
            <>
              <div className="mb-4 rounded border border-fidelity-low/40 bg-fidelity-low/10 px-3 py-2">
                <p className="font-mono text-xs text-fidelity-low">
                  This password reset link is invalid or has expired.
                </p>
              </div>
              <p className="text-center font-mono text-xs text-text-muted">
                <Link to="/forgot-password" className="text-brand hover:underline">
                  Request a new reset link
                </Link>
              </p>
            </>
          ) : success ? (
            <>
              <div className="mb-4 rounded border border-green-700/40 bg-green-900/15 px-3 py-2">
                <p className="font-mono text-xs text-green-300">
                  <span className="mr-1">✓</span>
                  {message}
                </p>
              </div>
              <Link
                to="/login"
                className="block w-full rounded bg-brand px-4 py-2 text-center font-mono text-sm font-semibold text-white hover:bg-brand/90 transition-colors"
              >
                Continue to sign in
              </Link>
            </>
          ) : (
            <>
              {error && (
                <div className="mb-4 rounded border border-fidelity-low/40 bg-fidelity-low/10 px-3 py-2">
                  <p className="font-mono text-xs text-fidelity-low">{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block font-mono text-xs text-text-muted uppercase tracking-widest mb-1.5">
                    New Password
                  </label>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                    autoComplete="new-password"
                    placeholder="••••••••"
                    className="w-full rounded border border-border bg-bg-700 px-3 py-2 font-mono text-sm text-text-primary placeholder-text-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                  />
                  <p className="mt-1 font-mono text-2xs text-text-muted">
                    Must be at least 8 characters.
                  </p>
                </div>

                <div>
                  <label className="block font-mono text-xs text-text-muted uppercase tracking-widest mb-1.5">
                    Confirm New Password
                  </label>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
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
                  {loading ? "Resetting…" : "Reset password"}
                </button>
              </form>

              <p className="mt-4 text-center font-mono text-xs text-text-muted">
                <Link to="/login" className="text-brand hover:underline">
                  Back to sign in
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
