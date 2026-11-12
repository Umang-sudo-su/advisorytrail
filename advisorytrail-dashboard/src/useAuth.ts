import { createContext, useContext } from 'react';
import type { AuthUser } from './api';

export interface AuthContextType {
  token: string | null;
  user: AuthUser | null;
  initializing: boolean;
  remember: boolean;
  login: (token: string, remember?: boolean) => void;
  setRemember: (remember: boolean) => void;
  logout: () => void;
}

/** Declared apart from the provider so the provider file only exports components. */
export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
