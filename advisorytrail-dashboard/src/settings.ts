export type ThemeMode = 'light' | 'dark' | 'system';

export interface AppSettings {
  theme: ThemeMode;
  apiBaseUrl: string;
  defaultCommitRef: string;
}

export const SETTINGS_KEY = 'advisorytrail_settings';

export const DEFAULT_API_BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');
export const DEFAULT_COMMIT_REF = 'HEAD';

export function defaultSettings(): AppSettings {
  return {
    theme: 'system',
    apiBaseUrl: DEFAULT_API_BASE,
    defaultCommitRef: DEFAULT_COMMIT_REF,
  };
}

export function loadSettings(): AppSettings {
  const defaults = defaultSettings();

  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (!raw) return defaults;

    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    const theme: ThemeMode =
      parsed.theme === 'light' || parsed.theme === 'dark' || parsed.theme === 'system'
        ? parsed.theme
        : defaults.theme;

    return {
      theme,
      apiBaseUrl:
        typeof parsed.apiBaseUrl === 'string' && parsed.apiBaseUrl.trim()
          ? parsed.apiBaseUrl.trim().replace(/\/$/, '')
          : defaults.apiBaseUrl,
      defaultCommitRef:
        typeof parsed.defaultCommitRef === 'string' && parsed.defaultCommitRef.trim()
          ? parsed.defaultCommitRef.trim()
          : defaults.defaultCommitRef,
    };
  } catch {
    return defaults;
  }
}

export function saveSettings(next: AppSettings) {
  localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
}

export function getApiBase(): string {
  return loadSettings().apiBaseUrl;
}

export function getDefaultCommitRef(): string {
  return loadSettings().defaultCommitRef;
}

export function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  if (mode === 'system') {
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return mode;
}

export function applyTheme(mode: ThemeMode) {
  const resolved = resolveTheme(mode);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function applyStoredTheme() {
  applyTheme(loadSettings().theme);
}

/** Keeps the UI in sync while the theme is set to "system". */
export function watchSystemTheme(mode: ThemeMode): () => void {
  if (mode !== 'system' || typeof window.matchMedia !== 'function') return () => {};

  const query = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = () => applyTheme('system');
  query.addEventListener('change', handler);
  return () => query.removeEventListener('change', handler);
}
