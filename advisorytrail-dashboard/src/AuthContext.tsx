import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  clearStoredToken,
  getCurrentUser,
  getStoredToken,
  logoutSession,
  storeToken,
  TOKEN_KEY,
  UNAUTHORIZED_EVENT,
  type AuthUser,
} from './api';
import { stopLiveStream } from './live';

import { AuthContext } from './useAuth';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken());
  const [user, setUser] = useState<AuthUser | null>(null);
  const [initializing, setInitializing] = useState(() => Boolean(getStoredToken()));
  const [remember, setRememberState] = useState(() => Boolean(localStorage.getItem(TOKEN_KEY)));

  const logout = useCallback(() => {
    // Revoke the server-side session too, so the token cannot be replayed.
    logoutSession().catch(() => {
      // Already-expired tokens have nothing to revoke.
    });
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

    if (!token) return;

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

