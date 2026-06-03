import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { getCurrentUser, loginUser, registerUser, logoutUser, setAuthToken, getAuthToken, clearAuthToken } from "../lib/api";
import type { User, CurrentUserWorkspaceMembership, PermissionSet, UserLoginRequest, UserRegisterRequest } from "../types";

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

  const applyUser = (data: { user: User; workspace_memberships: CurrentUserWorkspaceMembership[]; role?: string | null; organization_id?: string | null; permissions?: PermissionSet }) => {
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

  const refreshCurrentUser = async () => {
    if (!getAuthToken()) { setLoading(false); return; }
    try {
      const data = await getCurrentUser();
      applyUser(data);
    } catch {
      clearAuthToken(); setToken(null); resetAuth();
    } finally { setLoading(false); }
  };

  useEffect(() => { refreshCurrentUser(); }, []);

  const login = async (payload: UserLoginRequest) => {
    const data = await loginUser(payload);
    setAuthToken(data.access_token); setToken(data.access_token);
    setUser(data.user);
    await refreshCurrentUser();
  };

  const register = async (payload: UserRegisterRequest) => {
    const data = await registerUser(payload);
    setAuthToken(data.access_token); setToken(data.access_token);
    setUser(data.user);
    await refreshCurrentUser();
  };

  const logout = async () => {
    await logoutUser();
    setToken(null); resetAuth();
  };

  return (
    <AuthContext.Provider value={{ user, memberships, token, loading, isAuthenticated: !!user, role, organizationId, permissions, login, register, logout, refreshCurrentUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
