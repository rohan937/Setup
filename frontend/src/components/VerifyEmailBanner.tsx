import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { resendVerification } from "@/lib/api";

/**
 * Slim amber banner shown to authenticated users whose email is not yet
 * verified. Renders nothing otherwise.
 */
export default function VerifyEmailBanner() {
  const { isAuthenticated, user } = useAuth();
  const [resending, setResending] = useState(false);
  const [result, setResult] = useState<"sent" | "failed" | null>(null);

  if (!isAuthenticated || !user || user.email_verified !== false) {
    return null;
  }

  async function handleResend() {
    setResending(true);
    setResult(null);
    try {
      await resendVerification();
      setResult("sent");
    } catch {
      setResult("failed");
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="border-b border-amber-700/40 bg-amber-900/15 px-6 py-2">
      <div className="mx-auto flex w-full max-w-content items-center justify-between gap-3">
        <p className="font-mono text-2xs text-amber-300">
          Please verify your email to unlock all features.
        </p>
        <div className="flex items-center gap-2">
          {result === "sent" && (
            <span className="font-mono text-2xs text-green-400">Sent ✓</span>
          )}
          {result === "failed" && (
            <span className="font-mono text-2xs text-fidelity-low">Failed</span>
          )}
          <button
            type="button"
            onClick={() => void handleResend()}
            disabled={resending}
            className="rounded border border-amber-700/50 px-2 py-0.5 font-mono text-2xs text-amber-300 hover:border-amber-500 hover:text-amber-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {resending ? "Sending…" : "Resend"}
          </button>
        </div>
      </div>
    </div>
  );
}
