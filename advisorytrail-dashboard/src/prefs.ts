import type { DateFormatKey, Density, LandingPage, TimeFormatKey, UserPreferences } from './types';

/**
 * Personal preferences are cached locally so formatters, the landing page and
 * auto-refresh use the last known values before the Settings payload arrives.
 * The server remains the source of truth.
 */
export const PREFS_CACHE_KEY = 'advisorytrail_prefs';

export const DEFAULT_PREFS: UserPreferences = {
  display_name: '',
  landing_page: 'dashboard',
  language: 'en',
  date_format: 'YYYY-MM-DD',
  time_format: '24h',
  timezone: 'UTC',
  auto_refresh: true,
  refresh_interval: 30,
  page_size: 25,
  density: 'comfortable',
  reduce_motion: false,
  notifications: {
    events: {
      new_findings_critical: true,
      new_findings_high: true,
      new_findings_medium: false,
      new_findings_low: false,
      scan_completed: true,
      scan_failed: true,
      scan_partial: true,
      scan_queued: false,
      pr_scan_completed: true,
      pr_result_changed: true,
      check_run_updated: false,
      github_attention: true,
      webhook_unhealthy: true,
      repo_access_changed: true,
      invite_received: true,
      member_changed: true,
      account_security: true,
    },
    channels: { in_app: true, email: false },
    digest: 'immediate',
    quiet_hours: { enabled: false, start: '22:00', end: '07:00' },
  },
};

let cache: UserPreferences | null = null;

export function cachedPrefs(): UserPreferences {
  if (cache) return cache;

  try {
    const raw = localStorage.getItem(PREFS_CACHE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<UserPreferences>;
      cache = {
        ...DEFAULT_PREFS,
        ...parsed,
        notifications: {
          ...DEFAULT_PREFS.notifications,
          ...(parsed.notifications ?? {}),
          events: { ...DEFAULT_PREFS.notifications.events, ...(parsed.notifications?.events ?? {}) },
          channels: { ...DEFAULT_PREFS.notifications.channels, ...(parsed.notifications?.channels ?? {}) },
          quiet_hours: { ...DEFAULT_PREFS.notifications.quiet_hours, ...(parsed.notifications?.quiet_hours ?? {}) },
        },
      };
      return cache;
    }
  } catch {
    // Corrupt cache falls back to defaults; the API will correct it.
  }

  cache = DEFAULT_PREFS;
  return cache;
}

export function setCachedPrefs(next: UserPreferences) {
  cache = next;
  try {
    localStorage.setItem(PREFS_CACHE_KEY, JSON.stringify(next));
  } catch {
    // Private-mode storage failures must not break the page.
  }
}

export function setCachedPrefsPatch(patch: Partial<UserPreferences>) {
  setCachedPrefs({ ...cachedPrefs(), ...patch });
}

export function panelRefreshMs(): number | undefined {
  const prefs = cachedPrefs();
  if (!prefs.auto_refresh) return undefined;
  return Math.max(15, Number(prefs.refresh_interval) || 30) * 1000;
}

export function landingPage(): LandingPage {
  return cachedPrefs().landing_page;
}

export function applyDensity(density: Density = cachedPrefs().density) {
  const root = document.documentElement;
  if (density === 'compact') root.dataset.density = 'compact';
  else delete root.dataset.density;
}

export function applyMotion(reduceMotion: boolean = cachedPrefs().reduce_motion) {
  const root = document.documentElement;
  if (reduceMotion) root.dataset.motion = 'reduced';
  else delete root.dataset.motion;
}

export function applyAppearance(prefs: UserPreferences = cachedPrefs()) {
  applyDensity(prefs.density);
  applyMotion(prefs.reduce_motion);
}

const pad = (value: number) => String(value).padStart(2, '0');

function zonedParts(date: Date, timeZone: string) {
  try {
    const formatter = new Intl.DateTimeFormat('en-GB', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
    const parts = formatter.formatToParts(date);
    const lookup = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
    return {
      year: lookup('year'),
      month: lookup('month'),
      day: lookup('day'),
      hour: lookup('hour'),
      minute: lookup('minute'),
      second: lookup('second'),
    };
  } catch {
    return {
      year: String(date.getFullYear()),
      month: pad(date.getMonth() + 1),
      day: pad(date.getDate()),
      hour: pad(date.getHours()),
      minute: pad(date.getMinutes()),
      second: pad(date.getSeconds()),
    };
  }
}

/** Formats an API timestamp using the date/time/timezone preferences. */
export function formatDateTime(
  value: string | null | undefined,
  options: { seconds?: boolean } = {},
): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';

  const prefs = cachedPrefs();
  const parts = zonedParts(date, prefs.timezone);
  const dateFormat: DateFormatKey = prefs.date_format;
  const timeFormat: TimeFormatKey = prefs.time_format;

  const datePart =
    dateFormat === 'DD/MM/YYYY'
      ? `${parts.day}/${parts.month}/${parts.year}`
      : dateFormat === 'MM/DD/YYYY'
        ? `${parts.month}/${parts.day}/${parts.year}`
        : `${parts.year}-${parts.month}-${parts.day}`;

  let hour = Number(parts.hour);
  let suffix = '';
  if (timeFormat === '12h') {
    suffix = hour >= 12 ? ' PM' : ' AM';
    hour = hour % 12 || 12;
  }
  const timePart = `${timeFormat === '12h' ? hour : parts.hour}:${parts.minute}${options.seconds ? `:${parts.second}` : ''}${suffix}`;

  return `${datePart} ${timePart}`;
}

export const TIME_ZONES: string[] = (() => {
  const fallback = ['UTC', 'Europe/London', 'Europe/Berlin', 'America/New_York', 'America/Chicago', 'America/Los_Angeles', 'Asia/Kolkata', 'Asia/Singapore', 'Australia/Sydney'];
  try {
    const zones = (Intl as unknown as { supportedValuesOf?: (key: string) => string[] }).supportedValuesOf?.('timeZone');
    return zones && zones.length ? zones : fallback;
  } catch {
    return fallback;
  }
})();
