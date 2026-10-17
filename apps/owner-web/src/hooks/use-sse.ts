import { useCallback, useEffect, useRef, useState } from "react";

export interface UseSseOptions<T> {
  url: string | null;
  fetchState: () => Promise<T>;
  onMessage?: (event: MessageEvent) => void;
  pollingIntervalMs?: number;
  enabled?: boolean;
}

export interface UseSseReturn<T> {
  data: T | null;
  isConnected: boolean;
  isReconnecting: boolean;
  error: Error | null;
  refetch: () => Promise<void>;
}

export function useSse<T>({
  url,
  fetchState,
  onMessage,
  pollingIntervalMs = 5000,
  enabled = true,
}: UseSseOptions<T>): UseSseReturn<T> {
  const [data, setData] = useState<T | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [isReconnecting, setIsReconnecting] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const fetchStateRef = useRef(fetchState);
  fetchStateRef.current = fetchState;

  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const fetchSeqRef = useRef(0);

  const executeFetch = useCallback(async () => {
    const seq = ++fetchSeqRef.current;
    try {
      const res = await fetchStateRef.current();
      if (seq !== fetchSeqRef.current) return;
      setData(res);
      setError(null);
    } catch (err: unknown) {
      if (seq !== fetchSeqRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current !== null) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollTimerRef.current !== null) return;
    // Immediate fetch on fallback
    void executeFetch();
    pollTimerRef.current = setInterval(() => {
      void executeFetch();
    }, pollingIntervalMs);
  }, [executeFetch, pollingIntervalMs]);

  useEffect(() => {
    if (!enabled || !url) {
      setIsConnected(false);
      setIsReconnecting(false);
      stopPolling();
      return;
    }

    // Initial state fetch
    void executeFetch();

    let es: EventSource | null = null;
    try {
      const EventSourceClass =
        typeof window !== "undefined"
          ? window.EventSource
          : (globalThis as unknown as { EventSource?: typeof EventSource }).EventSource;
      if (EventSourceClass) {
        es = new EventSourceClass(url);
        eventSourceRef.current = es;

        es.onopen = () => {
          setIsConnected(true);
          setIsReconnecting(false);
          stopPolling();
          // Re-fetch full state on every connect and reconnect
          void executeFetch();
        };

        es.onmessage = (event: MessageEvent) => {
          onMessageRef.current?.(event);
          // Re-fetch state on change signals
          void executeFetch();
        };

        es.onerror = () => {
          setIsConnected(false);
          setIsReconnecting(true);
          setError(new Error("SSE connection interrupted"));
          // Start polling fallback while disconnected
          startPolling();
        };
      } else {
        // Fallback to polling if EventSource not supported
        setIsReconnecting(true);
        startPolling();
      }
    } catch (e: unknown) {
      setIsConnected(false);
      setIsReconnecting(true);
      setError(e instanceof Error ? e : new Error(String(e)));
      startPolling();
    }

    return () => {
      stopPolling();
      if (es) {
        es.close();
      }
      eventSourceRef.current = null;
    };
  }, [url, enabled, executeFetch, startPolling, stopPolling]);

  return {
    data,
    isConnected,
    isReconnecting,
    error,
    refetch: executeFetch,
  };
}
