"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ScanStateOut } from "./api";

/**
 * Fetch-with-state, the shape almost every screen needs.
 *
 * Deliberately small. A data-fetching library would be a reasonable choice
 * for a larger app, but this one has a handful of endpoints and no cache
 * invalidation worth the dependency.
 */
export function useResource<T>(
  load: () => Promise<T>,
  deps: React.DependencyList = [],
  options: { pollMs?: number } = {},
) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;

  const refresh = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError("Something went wrong.", 500));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!options.pollMs) return;
    const id = setInterval(() => void refresh(true), options.pollMs);
    return () => clearInterval(id);
  }, [options.pollMs, refresh]);

  return { data, error, loading, refresh, setData };
}

/**
 * Scan state, polled.
 *
 * Fast while a scan is running so progress moves, slow when idle so the app
 * is not chattering at the backend for no reason. Progress is reported as
 * sources completed — the backend knows that number, and a time-based
 * percentage would be invented.
 */
export function useScanState() {
  const [state, setState] = useState<ScanStateOut | null>(null);
  const [starting, setStarting] = useState(false);

  const poll = useCallback(async () => {
    try {
      setState(await api.scanState());
    } catch {
      /* the top bar simply shows nothing rather than an error */
    }
  }, []);

  useEffect(() => {
    void poll();
    const id = setInterval(poll, state?.running ? 2_000 : 30_000);
    return () => clearInterval(id);
  }, [poll, state?.running]);

  const start = useCallback(async () => {
    setStarting(true);
    try {
      const next = await api.startScan();
      setState(next);
      return { ok: true as const };
    } catch (e) {
      const error = e instanceof ApiError ? e : new ApiError("Could not start a scan.", 500);
      void poll();
      return { ok: false as const, message: error.message };
    } finally {
      setStarting(false);
    }
  }, [poll]);

  const progress =
    state?.running && state.providers_total > 0
      ? Math.min(100, Math.round((state.providers_done / state.providers_total) * 100))
      : null;

  return { state, start, starting, progress, refresh: poll };
}

/** Debounce a rapidly-changing value, so typing does not fire a request per key. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

/** Register a global keyboard shortcut, ignoring keystrokes meant for inputs. */
export function useHotkey(
  key: string,
  handler: () => void,
  options: { meta?: boolean; allowInInput?: boolean } = {},
) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing =
        target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (typing && !options.allowInInput) return;
      if (options.meta && !(event.metaKey || event.ctrlKey)) return;
      if (!options.meta && (event.metaKey || event.ctrlKey)) return;
      if (event.key.toLowerCase() !== key.toLowerCase()) return;
      event.preventDefault();
      handler();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [key, handler, options.meta, options.allowInInput]);
}
