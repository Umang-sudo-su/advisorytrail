import { useEffect, useState } from 'react';

type State<T> =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'success'; data: T };

export function useFetch<T>(loader: () => Promise<T>) {
  const [state, setState] = useState<State<T>>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;

    loader()
      .then((data) => {
        if (!cancelled) setState({ status: 'success', data });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'error', message: 'Could not load the data.' });
      });

    return () => {
      cancelled = true;
    };
  }, [loader, attempt]);

  const retry = () => {
    setState({ status: 'loading' });
    setAttempt((n) => n + 1);
  };

  return { state, retry };
}