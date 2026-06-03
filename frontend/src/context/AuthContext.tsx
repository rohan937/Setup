import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { getCurrentUser, loginUser, registerUser, logoutUser, setAuthToken, getAuthToken, clearAuthToken } from "../lib/api";
import type { User, CurrentUserWorkspaceMembership, UserLoginRequest, UserRegisterRequest } from "../types";

interface AuthContextType {
  user: User | null;
  memberships: CurrentUserWorkspaceMembership[];
  token: string | null;
  loading: boolean;
  isAuthenticated: boolean;
  login: (payload: UserLoginRequest) => Promise<void>;
  register: (payload: UserRegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshCurrentUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [memberships, setMemberships] = useState<CurrentUserWorkspaceMembership[]>([]);
  const [token, setToken] = useState<string | null>(getAuthToken);
  const [loading, setLoading] = useState(true);

  const refreshCurrentUser = async () => {
    if (!getAuthToken()) { setLoading(false); return; }
    try {
      const data = await getCurrentUser();
      setUser(data.user);
      setMemberships(data.workspace_memberships);
    } catch {
      clearAuthToken(); setToken(null); setUser(null); setMemberships([]);
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
    setUser(null); setMemberships([]); setToken(null);
  };

  return (
    <AuthContext.Provider value={{ user, memberships, token, loading, isAuthenticated: !!user, login, register, logout, refreshCurrentUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
