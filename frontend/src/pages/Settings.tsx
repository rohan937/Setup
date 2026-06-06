import { useEffect, useState } from "react";
import PageHeader from "@/components/PageHeader";
import Card from "@/components/Card";
import {
  createApiKey,
  getApiKeys,
  revokeApiKey,
  resendVerification,
  changePassword,
} from "@/lib/api";
import type { ApiKey, ApiKeyCreateResponse } from "@/types";
import { useAuth } from "@/context/AuthContext";
import { canManageApiKeys, roleBadgeClasses } from "@/lib/permissions";

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      onClick={handleCopy}
      className="ml-2 rounded border border-border px-2 py-0.5 font-mono text-2xs text-text-secondary hover:border-accent hover:text-accent"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function projectScopeLabel(k: ApiKey): string {
  if (!k.project_id) return "All projects (organization-wide)";
  const shortId = k.project_id.slice(0, 8);
  return k.project_name ? `Project ${shortId} — ${k.project_name}` : `Project ${shortId}`;
}

function AccountSecuritySection() {
  const { user } = useAuth();

  const [resending, setResending] = useState(false);
  const [resendResult, setResendResult] = useState<"sent" | "failed" | null>(null);

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changing, setChanging] = useState(false);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [changeSuccess, setChangeSuccess] = useState(false);

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

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setChangeError(null);
    setChangeSuccess(false);

    if (newPassword.length < 8) {
      setChangeError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setChangeError("New passwords do not match.");
      return;
    }

    setChanging(true);
    try {
      await changePassword(currentPassword, newPassword);
      setChangeSuccess(true);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setChangeError(
        err instanceof Error && err.message
          ? err.message
          : "Could not change password.",
      );
    } finally {
      setChanging(false);
    }
  }

  return (
    <div className="mb-6 space-y-4">
      <h2 className="font-mono text-xs font-semibold uppercase tracking-widest text-text-muted">
        Account Security
      </h2>

      {/* Email verification status */}
      <Card label="Email Verification">
        {user?.email_verified ? (
          <p className="font-mono text-xs text-green-400">Email verified ✓</p>
        ) : (
          <div className="flex items-center justify-between gap-3">
            <p className="font-mono text-xs text-amber-300">Email not verified</p>
            <div className="flex items-center gap-2">
              {resendResult === "sent" && (
                <span className="font-mono text-2xs text-green-400">Sent ✓</span>
              )}
              {resendResult === "failed" && (
                <span className="font-mono text-2xs text-red-400">Failed</span>
              )}
              <button
                type="button"
                onClick={() => void handleResend()}
                disabled={resending}
                className="rounded border border-border px-3 py-1 font-mono text-xs text-text-secondary hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
              >
                {resending ? "sending…" : "Resend"}
              </button>
            </div>
          </div>
        )}
      </Card>

      {/* Change password */}
      <Card label="Change Password">
        <form onSubmit={handleChangePassword} className="space-y-3">
          <div>
            <label className="mb-1 block font-mono text-2xs uppercase tracking-widest text-text-muted">
              Current Password
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block font-mono text-2xs uppercase tracking-widest text-text-muted">
              New Password
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="••••••••"
              className="w-full rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
            <p className="mt-1 font-mono text-2xs text-text-muted">
              Must be at least 8 characters.
            </p>
          </div>
          <div>
            <label className="mb-1 block font-mono text-2xs uppercase tracking-widest text-text-muted">
              Confirm New Password
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="••••••••"
              className="w-full rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
          </div>

          {changeError && (
            <p className="font-mono text-2xs text-red-400">{changeError}</p>
          )}
          {changeSuccess && (
            <p className="font-mono text-2xs text-green-400">
              Password changed successfully.
            </p>
          )}

          <button
            type="submit"
            disabled={changing}
            className="rounded border border-border px-3 py-1 font-mono text-xs text-text-secondary hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
          >
            {changing ? "changing…" : "Change Password"}
          </button>
        </form>
      </Card>
    </div>
  );
}

export default function Settings() {
  const auth = useAuth();
  const canManageKeys = canManageApiKeys(auth);
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState<ApiKeyCreateResponse | null>(null);

  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [keysLoading, setKeysLoading] = useState(true);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  async function loadKeys() {
    setKeysLoading(true);
    setKeysError(null);
    try {
      const res = await getApiKeys();
      setKeys(res.items);
    } catch (e: unknown) {
      setKeysError(e instanceof Error ? e.message : "Failed to load API keys.");
    } finally {
      setKeysLoading(false);
    }
  }

  useEffect(() => {
    void loadKeys();
  }, []);

  async function handleCreate() {
    if (!name.trim()) return;
    setCreating(true);
    setCreateError(null);
    setRevealed(null);
    try {
      const res = await createApiKey({ name: name.trim(), scopes: ["evidence:write"] });
      setRevealed(res);
      setName("");
      void loadKeys();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Failed to create API key.");
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(id: string) {
    setRevokingId(id);
    try {
      await revokeApiKey(id);
      void loadKeys();
    } catch {
      /* ignore — user can retry */
    } finally {
      setRevokingId(null);
    }
  }

  return (
    <>
      <PageHeader
        tag="Config"
        title="Settings"
        subtitle="Manage API keys and workspace configuration."
      />

      {/* API Keys section */}
      <div className="mb-6 space-y-4">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-widest text-text-muted">
          API Keys
        </h2>

        {/* Note */}
        <p className="font-mono text-2xs text-text-muted">
          API keys are local QuantFidelity keys. They are not third-party market data keys.
        </p>

        {/* RBAC note */}
        <div className="flex items-center justify-between rounded border border-border bg-bg-800 px-3 py-2">
          <p className="font-mono text-2xs text-text-muted">
            Creating and revoking API keys is <span className="text-text-secondary">Owner/Admin only</span> (RBAC foundation).
          </p>
          {auth.isAuthenticated && (
            <span className={`rounded border px-1.5 py-0.5 font-mono text-2xs font-semibold ${roleBadgeClasses(auth.role)}`}>
              {auth.role ?? "—"}
            </span>
          )}
        </div>

        {/* Create Key (Owner/Admin only) */}
        {canManageKeys && (
        <Card label="Create API Key">
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Key name (e.g. ci-runner)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void handleCreate()}
              className="flex-1 rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-xs text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none"
            />
            <span className="rounded bg-bg-tertiary px-2 py-1 font-mono text-2xs text-text-muted">
              evidence:write
            </span>
            <button
              onClick={() => void handleCreate()}
              disabled={creating || !name.trim()}
              className="rounded border border-border px-3 py-1 font-mono text-xs text-text-secondary hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              {creating ? "creating…" : "Create Key"}
            </button>
          </div>

          <p className="mt-1.5 font-mono text-2xs text-text-muted">
            Leave scope as <code className="rounded bg-bg-secondary px-1 py-0.5 text-accent">evidence:write</code> for evidence bundle ingestion (SDK default).
          </p>

          {createError && (
            <p className="mt-2 font-mono text-2xs text-red-400">{createError}</p>
          )}

          {revealed && (
            <div className="mt-3 rounded border border-yellow-600/40 bg-yellow-900/10 p-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-mono text-2xs font-semibold text-yellow-400">
                  Store this key now. It will not be shown again.
                </span>
                <button
                  onClick={() => setRevealed(null)}
                  className="font-mono text-2xs text-text-muted hover:text-text-secondary"
                >
                  dismiss
                </button>
              </div>
              <div className="flex items-center gap-1">
                <code className="break-all rounded bg-bg-secondary px-2 py-1 font-mono text-xs text-green-400">
                  {revealed.raw_key}
                </code>
                <CopyButton text={revealed.raw_key} />
              </div>
              <p className="mt-1 font-mono text-2xs text-text-muted">
                Name: {revealed.api_key.name} · Prefix: {revealed.api_key.key_prefix}
              </p>
              <p className="mt-2 font-mono text-2xs text-text-muted">
                Use this key with the QuantFidelity SDK:
              </p>
              <pre className="mt-1 overflow-x-auto rounded bg-bg-secondary px-3 py-2 font-mono text-2xs text-text-secondary">
{`from quantfidelity import QuantFidelityClient
client = QuantFidelityClient(
    base_url="http://localhost:8000",
    api_key="${revealed.raw_key}",
)`}
              </pre>
            </div>
          )}
        </Card>
        )}

        {/* Active Keys list */}
        <Card label="Active Keys">
          {keysLoading && (
            <p className="font-mono text-2xs text-text-muted">Loading…</p>
          )}
          {keysError && (
            <p className="font-mono text-2xs text-red-400">{keysError}</p>
          )}
          {!keysLoading && !keysError && keys.length === 0 && (
            <p className="font-mono text-2xs text-text-muted">No API keys yet.</p>
          )}
          {!keysLoading && keys.length > 0 && (
            <>
              <table className="w-full border-collapse font-mono text-2xs">
                <thead>
                  <tr className="border-b border-border text-left text-text-muted">
                    <th className="pb-1 pr-4 font-normal">Name</th>
                    <th className="pb-1 pr-4 font-normal">Prefix</th>
                    <th className="pb-1 pr-4 font-normal">Scopes</th>
                    <th className="pb-1 pr-4 font-normal">Scope</th>
                    <th className="pb-1 pr-4 font-normal">Created</th>
                    <th className="pb-1 pr-4 font-normal">Last used</th>
                    <th className="pb-1 pr-4 font-normal">Status</th>
                    <th className="pb-1 font-normal"></th>
                  </tr>
                </thead>
                <tbody>
                  {keys.map((k) => {
                    const scopesDisplay = k.scopes_json?.length
                      ? k.scopes_json.join(", ")
                      : "evidence:write (default)";
                    return (
                      <tr
                        key={k.id}
                        className={`border-b border-border/50 ${k.status === "revoked" ? "opacity-40" : ""}`}
                      >
                        <td className="py-1 pr-4 text-text-primary">{k.name}</td>
                        <td className="py-1 pr-4 text-text-secondary">{k.key_prefix}…</td>
                        <td className="py-1 pr-4 text-text-muted">{scopesDisplay}</td>
                        <td className="py-1 pr-4 text-text-muted">{projectScopeLabel(k)}</td>
                        <td className="py-1 pr-4 text-text-muted">{fmt(k.created_at)}</td>
                        <td className="py-1 pr-4 text-text-muted">{fmt(k.last_used_at)}</td>
                        <td className="py-1 pr-4">
                          {k.status === "active" ? (
                            <span className="text-green-400">active</span>
                          ) : (
                            <span className="text-text-muted">
                              revoked {fmt(k.revoked_at)}
                            </span>
                          )}
                        </td>
                        <td className="py-1">
                          {k.status === "active" && canManageKeys && (
                            <button
                              onClick={() => void handleRevoke(k.id)}
                              disabled={revokingId === k.id}
                              className="rounded border border-border px-2 py-0.5 text-text-muted hover:border-red-500 hover:text-red-400 disabled:opacity-40"
                            >
                              {revokingId === k.id ? "revoking…" : "revoke"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              <div className="mt-3 rounded border border-border bg-bg-800 px-3 py-2">
                <p className="font-mono text-2xs text-text-muted">
                  <span className="font-medium text-text-secondary">Project-scoped keys</span>{" "}
                  can only ingest evidence for strategies in that project. Organization-wide keys
                  (no project scope) can ingest for any strategy in the organization.
                </p>
                <p className="mt-1 font-mono text-2xs text-text-muted">
                  Keys require <code className="rounded bg-bg-secondary px-1 py-0.5 text-accent">evidence:write</code> scope for SDK ingestion
                  when <code className="rounded bg-bg-secondary px-1 py-0.5 text-text-muted">QF_REQUIRE_API_KEY_FOR_INGESTION=true</code> is set.
                </p>
              </div>
            </>
          )}
        </Card>

        {/* SDK usage hint */}
        <Card label="SDK Usage">
          <p className="mb-2 font-mono text-2xs text-text-muted">
            Use your key with the QuantFidelity Python SDK:
          </p>
          <pre className="overflow-x-auto rounded bg-bg-secondary px-3 py-2 font-mono text-2xs text-text-secondary">
{`from quantfidelity import QuantFidelityClient
client = QuantFidelityClient(
    base_url="http://localhost:8000",
    api_key="<your-key>",
)`}
          </pre>
        </Card>
      </div>

      {/* Account Security section */}
      <AccountSecuritySection />

      {/* Local Configuration section */}
      <div className="space-y-4">
        <h2 className="font-mono text-xs font-semibold uppercase tracking-widest text-text-muted">
          Local Configuration
        </h2>

        <Card label="Environment">
          <p className="font-mono text-2xs text-text-secondary">
            Set{" "}
            <code className="rounded bg-bg-secondary px-1 py-0.5 text-accent">
              QF_REQUIRE_API_KEY_FOR_INGESTION=true
            </code>{" "}
            in{" "}
            <code className="rounded bg-bg-secondary px-1 py-0.5 text-text-muted">
              backend/.env
            </code>{" "}
            to require API keys for the SDK evidence bundle endpoint.
          </p>
          <p className="mt-2 font-mono text-2xs text-text-muted">
            Without this flag the ingestion endpoint is unauthenticated (local dev default).
          </p>
        </Card>

        <Card label="Workspace">
          <p className="text-sm text-text-secondary">Local Workspace</p>
          <p className="mt-1 font-mono text-2xs text-text-muted">
            Single local organization. Team and org management arrive later.
          </p>
        </Card>
      </div>
    </>
  );
}
