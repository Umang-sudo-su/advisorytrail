import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  clearStoredToken,
  getCurrentUser,
  getStoredToken,
  storeToken,
  TOKEN_KEY,
  UNAUTHORIZED_EVENT,
  type AuthUser,
} from './api';
import { stopLiveStream } from './live';

interface AuthContextType {
  token: string | null;
  user: AuthUser | null;
  initializing: boolean;
  remember: boolean;
  login: (token: string, remember?: boolean) => void;
  setRemember: (remember: boolean) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initializing, setInitializing] = useState(() => Boolean(getStoredToken()));
  const [remember, setRememberState] = useState(() => Boolean(localStorage.getItem(TOKEN_KEY)));

  const logout = useCallback(() => {
    stopLiveStream();
    clearStoredToken();
    setUser(null);
    setToken(null);
    setRememberState(false);
    setInitializing(false);
  }, []);

  // Moves the live token between sessionStorage and localStorage without re-authenticating.
  const setRemember = useCallback((value: boolean) => {
    const current = getStoredToken();
    if (current) storeToken(current, value);
    setRememberState(value);
  }, []);

  // Any rejected token coming back from the API layer ends the session at once.
  useEffect(() => {
    const handleUnauthorized = () => logout();
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [logout]);

  // Validate the stored token before showing the app so a stale session never renders the shell.
  useEffect(() => {
    let cancelled = false;

    if (!token) {
      setInitializing(false);
      return;
    }

    getCurrentUser()
      .then((profile) => {
        if (cancelled) return;
        setUser(profile);
        setInitializing(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        // Network/backend-down errors keep the session; an expired token does not.
        if (error instanceof Error && error.message === 'Unauthorized') {
          setUser(null);
          setToken(null);
        }
        setInitializing(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  const login = useCallback((newToken: string, keepSignedIn = false) => {
    storeToken(newToken, keepSignedIn);
    setRememberState(keepSignedIn);
    setToken(newToken);
  }, []);

  return (
    <AuthContext.Provider value={{ token, user, initializing, remember, login, setRemember, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
