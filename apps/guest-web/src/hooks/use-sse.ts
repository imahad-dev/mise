import { useCallback, useEffect, useRef, useState } from "react";

export interface SseManagerOptions<T> {
  url: string | null;
  fetchState: () => Promise<T>;
  onMessage?: (event: MessageEvent) => void;
  pollingIntervalMs?: number;
  onStateChange?: (state: {
    data: T | null;
    isConnected: boolean;
    isReconnecting: boolean;
    error: Error | null;
  }) => void;
}

export class SseManager<T> {
  url: string | null;
  fetchState: () => Promise<T>;
  onMessage?: (event: MessageEvent) => void;
  pollingIntervalMs: number;
  onStateChange?: (state: {
    data: T | null;
    isConnected: boolean;
    isReconnecting: boolean;
    error: Error | null;
  }) => void;

  data: T | null = null;
  isConnected = false;
  isReconnecting = false;
  error: Error | null = null;

  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private es: EventSource | null = null;
  private destroyed = false;

  constructor(options: SseManagerOptions<T>) {
    this.url = options.url;
    this.fetchState = options.fetchState;
    this.onMessage = options.onMessage;
    this.pollingIntervalMs = options.pollingIntervalMs ?? 5000;
    this.onStateChange = options.onStateChange;
  }

  private notify() {
    this.onStateChange?.({
      data: this.data,
      isConnected: this.isConnected,
      isReconnecting: this.isReconnecting,
      error: this.error,
    });
  }

  private fetchSeq = 0;

  async executeFetch(): Promise<void> {
    if (this.destroyed) return;
    const seq = ++this.fetchSeq;
    try {
      const result = await this.fetchState();
      if (this.destroyed || seq !== this.fetchSeq) return;
      this.data = result;
      this.error = null;
      this.notify();
    } catch (err: unknown) {
      if (this.destroyed || seq !== this.fetchSeq) return;
      this.error = err instanceof Error ? err : new Error(String(err));
      this.notify();
    }
  }

  startPolling() {
    if (this.pollTimer !== null) return;
    void this.executeFetch();
    this.pollTimer = setInterval(() => {
      void this.executeFetch();
    }, this.pollingIntervalMs);
  }

  stopPolling() {
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  start() {
    if (!this.url || this.destroyed) return;

    // Initial state fetch
    void this.executeFetch();

    try {
      const EventSourceClass =
        typeof window !== "undefined"
          ? window.EventSource
          : (globalThis as unknown as { EventSource?: typeof EventSource }).EventSource;

      if (!EventSourceClass) {
        this.isReconnecting = true;
        this.notify();
        this.startPolling();
        return;
      }

      const es = new EventSourceClass(this.url);
      this.es = es;

      es.onopen = () => {
        this.isConnected = true;
        this.isReconnecting = false;
        this.error = null;
        this.stopPolling();
        this.notify();
        // Re-fetch full state on every connect and reconnect
        void this.executeFetch();
      };

      es.onmessage = (event: MessageEvent) => {
        this.onMessage?.(event);
        // Re-fetch state on change signals
        void this.executeFetch();
      };

      es.onerror = () => {
        this.isConnected = false;
        this.isReconnecting = true;
        this.error = new Error("SSE connection interrupted");
        this.notify();
        this.startPolling();
      };
    } catch (err: unknown) {
      this.isConnected = false;
      this.isReconnecting = true;
      this.error = err instanceof Error ? err : new Error(String(err));
      this.notify();
      this.startPolling();
    }
  }

  destroy() {
    this.destroyed = true;
    this.stopPolling();
    if (this.es) {
      this.es.close();
      this.es = null;
    }
  }
}

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

export function useSse<T>(options: UseSseOptions<T>): UseSseReturn<T> {
  const [state, setState] = useState({
    data: null as T | null,
    isConnected: false,
    isReconnecting: false,
    error: null as Error | null,
  });

  const managerRef = useRef<SseManager<T> | null>(null);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    setState({
      data: null,
      isConnected: false,
      isReconnecting: false,
      error: null,
    });

    if (options.enabled === false || !options.url) {
      return;
    }

    const manager = new SseManager<T>({
      url: options.url,
      fetchState: () => optionsRef.current.fetchState(),
      onMessage: (ev) => optionsRef.current.onMessage?.(ev),
      pollingIntervalMs: options.pollingIntervalMs,
      onStateChange: (newState) => setState(newState),
    });
    managerRef.current = manager;
    manager.start();

    return () => {
      manager.destroy();
      managerRef.current = null;
    };
  }, [options.url, options.enabled, options.pollingIntervalMs]);

  const refetch = useCallback(async () => {
    await managerRef.current?.executeFetch();
  }, []);

  return {
    data: state.data,
    isConnected: state.isConnected,
    isReconnecting: state.isReconnecting,
    error: state.error,
    refetch,
  };
}
