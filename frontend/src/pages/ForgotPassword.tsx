import { useState, FormEvent } from "react";
import { Link } from "react-router-dom";
import { forgotPassword } from "@/lib/api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [message, setMessage] = useState<string>("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await forgotPassword(email);
      setMessage(
        res.message ||
          "If an account exists for that email, a reset link has been sent.",
      );
    } catch {
      // The endpoint is generic and should not reveal account existence. Even on
      // an unexpected error we show the same generic message.
      setMessage(
        "If an account exists for that email, a reset link has been sent.",
      );
    } finally {
      setSubmitted(true);
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
            Reset your password
          </h2>

          {submitted ? (
            <div className="mb-4 rounded border border-green-700/40 bg-green-900/15 px-3 py-2">
              <p className="font-mono text-xs text-green-300">{message}</p>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <p className="font-mono text-xs text-text-muted">
                Enter your account email and we&apos;ll send a link to reset your
                password.
              </p>
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

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded bg-brand px-4 py-2 font-mono text-sm font-semibold text-white hover:bg-brand/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {loading ? "Sending…" : "Send reset link"}
              </button>
            </form>
          )}

          <p className="mt-4 text-center font-mono text-xs text-text-muted">
            <Link to="/login" className="text-brand hover:underline">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
