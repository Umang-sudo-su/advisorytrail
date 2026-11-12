import { useCallback, useEffect, useRef, useState } from 'react';
import { subscribeLive } from './live';

type State<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T };

interface FetchOptions {
  /** Safety-net interval for silent re-fetch; server pushes refresh immediately. */
  pollMs?: number;
}

export function useFetch<T>(loader: () => Promise<T>, options: FetchOptions = {}) {
  const { pollMs } = options;
  const [state, setState] = useState<State<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const refreshRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    let cancelled = false;
    let busy = false;

    const load = async (quiet: boolean) => {
      if (busy) return;
      busy = true;

      try {
        const data = await loader();
        if (!cancelled) setState({ status: 'success', data });
      } catch {
        if (cancelled) return;
        // A failed background refresh keeps the last good data on screen.
        // Only the first load (or an explicit retry) shows the error screen.
        if (!quiet) setState({ status: 'error', message: 'Could not load the data.' });
      } finally {
        busy = false;
      }
    };

    refreshRef.current = () => {
      void load(true);
    };

    void load(false);

    if (!pollMs) {
      return () => {
        cancelled = true;
        refreshRef.current = null;
      };
    }

    const timer = window.setInterval(() => void load(true), pollMs);
    const refresh = () => void load(true);
    window.addEventListener('focus', refresh);
    document.addEventListener('visibilitychange', refresh);

    return () => {
      cancelled = true;
      refreshRef.current = null;
      window.clearInterval(timer);
      window.removeEventListener('focus', refresh);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, [loader, attempt, pollMs]);

  // Server-pushed updates: refetch as soon as a scan/finding/audit change lands.
  useEffect(() => {
    const unsubscribe = subscribeLive(() => refreshRef.current?.());
    return unsubscribe;
  }, []);

  const retry = useCallback(() => {
    setState({ status: 'loading' });
    setAttempt((n) => n + 1);
  }, []);

  // Quiet re-fetch that leaves the current data (and any UI state) in place.
  const refresh = useCallback(() => {
    refreshRef.current?.();
  }, []);

  return { state, retry, refresh };
}
