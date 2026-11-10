import { getStoredToken } from './api';
import { getApiBase } from './settings';

type Listener = () => void;

const listeners = new Set<Listener>();

let running = false;
let abort: AbortController | null = null;
let retryTimer: number | undefined;
let retryCount = 0;

function emit() {
  for (const listener of listeners) listener();
}

/**
 * Refreshes every subscriber whenever the server reports a state change.
 * Falls back to reconnecting with backoff if the stream drops.
 */
export function subscribeLive(listener: Listener) {
  listeners.add(listener);
  startLiveStream();

  return () => {
    listeners.delete(listener);
  };
}

export function stopLiveStream() {
  running = false;
  abort?.abort();
  abort = null;
  if (retryTimer !== undefined) window.clearTimeout(retryTimer);
  retryTimer = undefined;
  retryCount = 0;
}

function startLiveStream() {
  if (running) return;
  running = true;
  void connect();
}

async function connect() {
  const token = getStoredToken();
  if (!token) {
    running = false;
    return;
  }

  const controller = new AbortController();
  abort = controller;

  try {
    const response = await fetch(`${getApiBase()}/api/v1/events`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'text/event-stream',
      },
      signal: controller.signal,
      cache: 'no-store',
    });

    if (!response.ok || !response.body) {
      throw new Error(`Live stream unavailable (${response.status})`);
    }

    retryCount = 0;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf('\n\n');
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        if (frame.startsWith('event: state')) emit();
        boundary = buffer.indexOf('\n\n');
      }
    }
  } catch {
    // Network loss or an aborted connection: reconnect below.
  } finally {
    if (abort === controller) abort = null;
    if (running) scheduleReconnect();
  }
}

function scheduleReconnect() {
  const delay = Math.min(1000 * 2 ** retryCount, 15000);
  retryCount += 1;

  retryTimer = window.setTimeout(() => {
    if (running) void connect();
  }, delay);
}
