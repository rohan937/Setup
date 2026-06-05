import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import {
  getCurrentUser,
  loginUser,
  registerUser,
  logoutUser,
  setAuthToken,
  getAuthToken,
  clearAuthToken,
  HttpError,
} from "../lib/api";
import type {
  User,
  CurrentUserWorkspaceMembership,
  PermissionSet,
  UserLoginRequest,
  UserRegisterRequest,
} from "../types";

const EMPTY_PERMISSIONS: PermissionSet = {
  can_read_research: false,
  can_write_research: false,
  can_manage_workspace: false,
  can_manage_members: false,
  can_manage_api_keys: false,
  can_seed_demo: false,
};

interface AuthContextType {
  user: User | null;
  memberships: CurrentUserWorkspaceMembership[];
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  // M69 — RBAC role + permissions for permission-aware UI.
  role: string | null;
  organizationId: string | null;
  permissions: PermissionSet;
  /**
   * Non-null when the user was signed out due to a confirmed auth failure
   * (token expired / revoked). The Login page reads and displays this message,
   * then clears it. It is NOT set for transient connectivity failures — in
   * those cases the existing session is preserved.
   */
  authMessage: string | null;
  clearAuthMessage: () => void;
  login: (payload: UserLoginRequest) => Promise<void>;
  register: (payload: UserRegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshCurrentUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [memberships, setMemberships] = useState<CurrentUserWorkspaceMembership[]>([]);
  const [role, setRole] = useState<string | null>(null);
  const [organizationId, setOrganizationId] = useState<string | null>(null);
  const [permissions, setPermissions] = useState<PermissionSet>(EMPTY_PERMISSIONS);
  const [token, setToken] = useState<string | null>(getAuthToken);
  const [loading, setLoading] = useState(true);
  /**
   * Shown on the Login page when the user was signed out due to an expired or
   * revoked token (HTTP 401). Empty string for non-auth errors — we keep the
   * session alive on transient failures so a Render cold-start or a brief 500
   * doesn't permanently log the user out.
   */
  const [authMessage, setAuthMessage] = useState<string | null>(null);

  const applyUser = (data: {
    user: User;
    workspace_memberships: CurrentUserWorkspaceMembership[];
    role?: string | null;
    organization_id?: string | null;
    permissions?: PermissionSet;
  }) => {
    setUser(data.user);
    setMemberships(data.workspace_memberships);
    setRole(data.role ?? null);
    setOrganizationId(data.organization_id ?? null);
    setPermissions(data.permissions ?? EMPTY_PERMISSIONS);
  };

  const resetAuth = () => {
    setUser(null);
    setMemberships([]);
    setRole(null);
    setOrganizationId(null);
    setPermissions(EMPTY_PERMISSIONS);
  };

  /**
   * Restore the session from the stored token.
   *
   * Previous behaviour (bug): caught ANY error from GET /api/auth/me and
   * cleared the stored token — permanently signing out the user whenever the
   * backend returned a 5xx or a network error (e.g. Render free-tier cold start
   * where the first request gets a timeout before the dyno wakes up).
   *
   * Fixed behaviour:
   * - HTTP 401 → token is genuinely expired or revoked; clear it and set
   *   `authMessage` so the Login page can say "Session expired, please sign in".
   * - Any other error (5xx, network failure, timeout) → keep the stored token;
   *   the user may just be experiencing a momentary connectivity issue and
   *   should not be forced to re-enter their password for that.
   */
  const refreshCurrentUser = async () => {
    if (!getAuthToken()) {
      setLoading(false);
      return;
    }
    try {
      const data = await getCurrentUser();
      applyUser(data);
      setAuthMessage(null); // clear any leftover session-expired message
    } catch (err) {
      if (err instanceof HttpError && err.status === 401) {
        // Token is genuinely expired or revoked — sign out and explain.
        clearAuthToken();
        setToken(null);
        resetAuth();
        setAuthMessage("Your session has expired. Please sign in again.");
      }
      // For all other failures (5xx, network error, TypeError, etc.):
      // preserve the stored token. The user will appear as not-yet-loaded
      // (user === null, loading === false) until the next successful /me call.
      // They are NOT signed out — their token remains valid.
    } finally {
      setLoading(false);
    }
  };

  // Restore session on mount.
  useEffect(() => {
    refreshCurrentUser();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (payload: UserLoginRequest) => {
    const data = await loginUser(payload);
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    setAuthMessage(null);
    await refreshCurrentUser();
  };

  const register = async (payload: UserRegisterRequest) => {
    const data = await registerUser(payload);
    setAuthToken(data.access_token);
    setToken(data.access_token);
    setUser(data.user);
    setAuthMessage(null);
    await refreshCurrentUser();
  };

  const logout = async () => {
    // logoutUser() calls clearAuthToken() internally (and POSTs to the
    // backend's stateless logout endpoint). We still set token state to null
    // and reset user data so the UI responds immediately.
    try {
      await logoutUser();
    } catch {
      // Backend logout is stateless — even if the request fails, the local
      // token must be cleared so the user is signed out in the browser.
      clearAuthToken();
    }
    setToken(null);
    resetAuth();
    setAuthMessage(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        memberships,
        token,
        loading,
        isAuthenticated: !!user,
        role,
        organizationId,
        permissions,
        authMessage,
        clearAuthMessage: () => setAuthMessage(null),
        login,
        register,
        logout,
        refreshCurrentUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
