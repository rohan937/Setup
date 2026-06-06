import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { verifyEmail, resendVerification } from "@/lib/api";

type VerifyState = "loading" | "success" | "error";

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const { isAuthenticated } = useAuth();

  const [state, setState] = useState<VerifyState>(token ? "loading" : "error");
  const [message, setMessage] = useState<string>(
    token ? "" : "This verification link is invalid or has expired.",
  );

  const [resending, setResending] = useState(false);
  const [resendResult, setResendResult] = useState<"sent" | "failed" | null>(null);

  // Guard against React 18 StrictMode double-invoking the effect on mount.
  const started = useRef(false);

  useEffect(() => {
    if (!token) return;
    if (started.current) return;
    started.current = true;

    verifyEmail(token)
      .then((res) => {
        setState("success");
        setMessage(res.message || "Your email has been verified.");
      })
      .catch((err) => {
        setState("error");
        setMessage(
          err instanceof Error && err.message
            ? err.message
            : "This verification link is invalid or has expired.",
        );
      });
  }, [token]);

  async function handleResend() {
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
          <h2 className="font-mono text-sm font-semibold text-text-primary mb-5">
            Email verification
          </h2>

          {state === "loading" && (
            <p className="font-mono text-xs text-text-muted">
              Verifying your email…
            </p>
          )}

          {state === "success" && (
            <>
              <div className="mb-4 rounded border border-green-700/40 bg-green-900/15 px-3 py-2">
                <p className="font-mono text-xs text-green-300">
                  <span className="mr-1">✓</span>
                  {message}
                </p>
              </div>
              <Link
                to="/"
                className="block w-full rounded bg-brand px-4 py-2 text-center font-mono text-sm font-semibold text-white hover:bg-brand/90 transition-colors"
              >
                Continue to dashboard
              </Link>
            </>
          )}

          {state === "error" && (
            <>
              <div className="mb-4 rounded border border-fidelity-low/40 bg-fidelity-low/10 px-3 py-2">
                <p className="font-mono text-xs text-fidelity-low">{message}</p>
              </div>

              {isAuthenticated && (
                <div className="mb-4">
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
                </div>
              )}

              <p className="text-center font-mono text-xs text-text-muted">
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
