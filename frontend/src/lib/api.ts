/**
 * The API client. Every path is relative, so the browser never needs to know where the backend is —
 * `next.config.mjs` rewrites `/api/*` to it. See that file for why that matters in a preview.
 */

import type {
  AnalysisVerdict,
  LoopStats,
  PaperAccountResponse,
  PaperFill,
  PaperOrder,
  PaperOverview,
  SystemStatus,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string, path: string) {
    super(`GET ${path} failed with ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    signal,
    headers: { Accept: "application/json" },
    // A dashboard showing a stale balance and calling it current is worse than one showing an
    // error, so nothing is cached by the browser: freshness is TanStack Query's job, where it is
    // visible and configurable.
    cache: "no-store",
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, text, path);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    // An empty or HTML body means something other than the API answered — a proxy, usually.
    // Reporting that as a parse error would send whoever debugs it to the wrong file.
    throw new ApiError(response.status, `response was not JSON: ${text.slice(0, 200)}`, path);
  }
}

export interface OrdersResponse {
  simulated: boolean;
  environment: string;
  count: number;
  orders: PaperOrder[];
}

export interface FillsResponse {
  simulated: boolean;
  environment: string;
  count: number;
  total_commission: string;
  fills: PaperFill[];
}

export interface PositionsResponse {
  simulated: boolean;
  environment: string;
  count: number;
  positions_marked_with_real_data: number;
  positions_carried_at_entry: string[];
  positions: PaperAccountResponse["positions"];
}

/**
 * `/v1/intelligence/dossiers`. The route publishes `view_gaps` — the elements the approved dossier
 * view asks for that have no column to come from — and that field is kept here rather than dropped,
 * because a research panel that hides its own gaps renders as complete.
 */
/** `/v1/audit/verify` — the hash chain's own verdict on itself. */
export interface AuditVerifyResponse {
  intact?: boolean;
  records?: number;
  head?: string | null;
  [key: string]: unknown;
}

export interface DossiersResponse {
  count?: number;
  dossiers?: Array<Record<string, unknown>>;
  empty?: string | null;
  view_gaps?: Record<string, unknown> | string[];
  served_from?: string;
}

export interface AnalysisResponse {
  simulated: boolean;
  environment: string;
  count: number;
  analyzer: Record<string, unknown>;
  confidence_band: [string, string];
  analyses: AnalysisVerdict[];
}

export const api = {
  status: (signal?: AbortSignal) => getJson<SystemStatus>("/v1/status", signal),
  health: (signal?: AbortSignal) => getJson<{ status: string; phase: string }>("/healthz", signal),
  paper: (signal?: AbortSignal) => getJson<PaperOverview>("/v1/paper", signal),
  account: (signal?: AbortSignal) => getJson<PaperAccountResponse>("/v1/paper/account", signal),
  orders: (limit = 100, signal?: AbortSignal) =>
    getJson<OrdersResponse>(`/v1/paper/orders?limit=${limit}`, signal),
  fills: (limit = 200, signal?: AbortSignal) =>
    getJson<FillsResponse>(`/v1/paper/fills?limit=${limit}`, signal),
  positions: (signal?: AbortSignal) => getJson<PositionsResponse>("/v1/paper/positions", signal),
  analysis: (limit = 50, signal?: AbortSignal) =>
    getJson<AnalysisResponse>(`/v1/paper/analysis?limit=${limit}`, signal),
  dossiers: (signal?: AbortSignal) => getJson<DossiersResponse>("/v1/intelligence/dossiers", signal),
  auditVerify: (signal?: AbortSignal) => getJson<AuditVerifyResponse>("/v1/audit/verify", signal),
  stats: async (signal?: AbortSignal): Promise<LoopStats> =>
    (await getJson<PaperOverview>("/v1/paper", signal)).stats,

  /** POST control. These start, stop and reset a simulation; none can transmit an order. */
  start: () => postJson<{ started: boolean; reason?: string; stats: LoopStats }>("/v1/paper/start"),
  stop: () => postJson<{ stopped: boolean; stats: LoopStats }>("/v1/paper/stop"),
  reset: () =>
    postJson<{ reset: boolean; starting_cash: string; account: PaperAccountResponse }>(
      "/v1/paper/reset",
    ),
};

async function postJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  const text = await response.text();
  if (!response.ok) {
    throw new ApiError(response.status, text, path);
  }
  return JSON.parse(text) as T;
}

/**
 * The stream endpoint. Built as a URL rather than fetched, because `EventSource` does the fetching:
 * it reconnects on its own and speaks SSE, which is what the ruled stack allows (§3.5: native
 * WebSocket/SSE from our own API, no paid realtime service in the path).
 */
export const paperStreamUrl = `${BASE}/v1/paper/stream`;
