"use client";

/**
 * The real-time connection to the paper platform.
 *
 * `EventSource` rather than a polling `setInterval`, for three reasons that matter here rather than
 * in the abstract: the browser reconnects by itself after a dropped connection; the server decides
 * the cadence and states it in every frame, so the UI can show the latency it is actually running at
 * instead of the one it asked for; and it is what the ruled stack permits — native SSE from our own
 * API, with no paid realtime service in the path (§3.5, D-019).
 *
 * The connection state is returned alongside the data and is **not** optional to render. A dashboard
 * showing a frozen equity curve with no indication that its stream died is worse than one showing an
 * error, because the frozen curve looks like a stable market.
 */

import { useEffect, useRef, useState } from "react";

import { paperStreamUrl } from "./api";
import type { PaperStreamFrame } from "./types";

export type StreamState = "idle" | "connecting" | "open" | "closed" | "error";

export interface PaperStream {
  frame: PaperStreamFrame | null;
  state: StreamState;
  /** Frames received since mount. Zero while `state` is `open` means the stream is silent. */
  frames: number;
  lastFrameAt: number | null;
  /** The cadence the server declared, which is the one that is true. */
  intervalSeconds: number | null;
  error: string | null;
}

export function usePaperStream(enabled = true): PaperStream {
  const [frame, setFrame] = useState<PaperStreamFrame | null>(null);
  const [state, setState] = useState<StreamState>("idle");
  const [frames, setFrames] = useState(0);
  const [lastFrameAt, setLastFrameAt] = useState<number | null>(null);
  const [intervalSeconds, setIntervalSeconds] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!enabled) {
      setState("idle");
      return;
    }
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      // No SSE support (or no window at all, during a server render). Saying so beats hanging in
      // "connecting" forever, which is indistinguishable from a slow backend.
      setState("closed");
      setError("this browser has no EventSource support");
      return;
    }

    setState("connecting");
    setError(null);
    const source = new EventSource(paperStreamUrl);
    sourceRef.current = source;

    source.addEventListener("open", () => {
      setState("open");
      setError(null);
    });

    // The server names its events, so each needs its own listener: a bare `onmessage` only ever
    // receives events with no name, and would silently receive nothing at all here.
    source.addEventListener("hello", (event: MessageEvent<string>) => {
      try {
        const hello = JSON.parse(event.data) as { interval_seconds?: number };
        if (typeof hello.interval_seconds === "number") setIntervalSeconds(hello.interval_seconds);
      } catch {
        // A malformed greeting is not worth dropping the stream over.
      }
    });

    source.addEventListener("paper", (event: MessageEvent<string>) => {
      try {
        const parsed = JSON.parse(event.data) as PaperStreamFrame;
        setFrame(parsed);
        setFrames((count) => count + 1);
        setLastFrameAt(Date.now());
        if (typeof parsed.interval_seconds === "number") setIntervalSeconds(parsed.interval_seconds);
      } catch (cause) {
        setError(`could not parse a stream frame: ${String(cause)}`);
      }
    });

    source.addEventListener("error", () => {
      // EventSource fires `error` both for a fatal failure and while it is reconnecting, and does
      // not distinguish them. `readyState` is the only honest signal available: CLOSED means it gave
      // up, CONNECTING means it is trying again and the data on screen is getting older.
      if (source.readyState === EventSource.CLOSED) {
        setState("error");
        setError("the stream closed and will not reconnect on its own");
      } else {
        setState("connecting");
        setError("reconnecting — values shown are from the last frame received");
      }
    });

    return () => {
      source.close();
      sourceRef.current = null;
      setState((current) => (current === "error" ? current : "closed"));
    };
  }, [enabled]);

  return { frame, state, frames, lastFrameAt, intervalSeconds, error };
}

/**
 * How long since the last frame, in seconds.
 *
 * Exposed separately from `lastFrameAt` so a component can render "last update 12s ago" on a timer
 * of its own: the value has to keep changing even when no frame arrives, and that is precisely the
 * case it exists to surface.
 */
export function useStreamAge(lastFrameAt: number | null, tickMs = 1000): number | null {
  const [age, setAge] = useState<number | null>(
    lastFrameAt === null ? null : (Date.now() - lastFrameAt) / 1000,
  );

  useEffect(() => {
    if (lastFrameAt === null) {
      setAge(null);
      return;
    }
    setAge((Date.now() - lastFrameAt) / 1000);
    const timer = setInterval(() => setAge((Date.now() - lastFrameAt) / 1000), tickMs);
    return () => clearInterval(timer);
  }, [lastFrameAt, tickMs]);

  return age;
}
