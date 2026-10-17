import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SseManager } from "./use-sse";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  close() {
    this.closed = true;
  }

  simulateOpen() {
    this.onopen?.(new Event("open"));
  }

  simulateError(err?: Event) {
    this.onerror?.(err || new Event("error"));
  }

  simulateMessage(data: string) {
    this.onmessage?.(new MessageEvent("message", { data }));
  }
}

describe("useSse / SseManager", () => {
  let originalEventSource: typeof EventSource | undefined;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.instances = [];
    originalEventSource = (globalThis as unknown as { EventSource?: typeof EventSource }).EventSource;
    (globalThis as unknown as { EventSource?: unknown }).EventSource = FakeEventSource;
  });

  afterEach(() => {
    vi.useRealTimers();
    (globalThis as unknown as { EventSource?: typeof EventSource }).EventSource = originalEventSource;
  });

  it("re-fetches full state on connect and reconnect", async () => {
    let callCount = 0;
    const fetchState = vi.fn(async () => {
      callCount += 1;
      return { count: callCount };
    });

    const manager = new SseManager({
      url: "/api/test/stream",
      fetchState,
      pollingIntervalMs: 3000,
    });

    // Start manager
    manager.start();

    // Initial fetch on start
    await Promise.resolve();
    expect(fetchState).toHaveBeenCalledTimes(1);

    const es = FakeEventSource.instances[0];
    expect(es).toBeDefined();

    // 1. Simulate initial connect open
    es.simulateOpen();
    await Promise.resolve();
    // fetchState called again on connect
    expect(fetchState).toHaveBeenCalledTimes(2);
    expect(manager.isConnected).toBe(true);
    expect(manager.isReconnecting).toBe(false);

    // 2. Simulate disconnect / error
    es.simulateError();
    await Promise.resolve();
    expect(manager.isConnected).toBe(false);
    expect(manager.isReconnecting).toBe(true);

    // 3. Simulate reconnect open
    es.simulateOpen();
    await Promise.resolve();
    // fetchState called again on reconnect
    expect(fetchState).toHaveBeenCalledTimes(4); // 2 + 1 (immediate on error fallback) + 1 (on reconnect)
    expect(manager.isConnected).toBe(true);
    expect(manager.isReconnecting).toBe(false);

    manager.destroy();
  });

  it("triggers polling fallback every few seconds when SSE is down and stops on reconnect", async () => {
    let callCount = 0;
    const fetchState = vi.fn(async () => {
      callCount += 1;
      return { count: callCount };
    });

    const manager = new SseManager({
      url: "/api/test/stream",
      fetchState,
      pollingIntervalMs: 3000,
    });

    // Start manager
    manager.start();
    await Promise.resolve();
    expect(fetchState).toHaveBeenCalledTimes(1);

    const es = FakeEventSource.instances[0];

    // Simulate SSE error -> triggers polling fallback
    es.simulateError();
    await Promise.resolve();
    expect(manager.isReconnecting).toBe(true);
    const countAfterError = fetchState.mock.calls.length;

    // Advance 3 seconds -> polling triggers fetchState
    vi.advanceTimersByTime(3000);
    await Promise.resolve();
    expect(fetchState).toHaveBeenCalledTimes(countAfterError + 1);

    // Advance another 3 seconds -> polling triggers again
    vi.advanceTimersByTime(3000);
    await Promise.resolve();
    expect(fetchState).toHaveBeenCalledTimes(countAfterError + 2);

    // Reconnect -> stops polling fallback
    es.simulateOpen();
    await Promise.resolve();
    expect(manager.isConnected).toBe(true);
    expect(manager.isReconnecting).toBe(false);
    const countAfterReconnect = fetchState.mock.calls.length;

    // Advance 6 seconds -> no more polling triggers
    vi.advanceTimersByTime(6000);
    await Promise.resolve();
    expect(fetchState).toHaveBeenCalledTimes(countAfterReconnect);

    manager.destroy();
  });
});
