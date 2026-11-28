/**
 * The shapes the API actually returns.
 *
 * Two rules are visible in every type here, and both come from having been bitten by the opposite:
 *
 * **Money is a string, never a number.** The backend computes in `Decimal` and serialises with
 * `str()`, because a float cannot represent a price exactly. If this file declared `equity: number`,
 * JSON parsing would silently round it and the dashboard would disagree with the ledger by a cent
 * that no one could trace. Every monetary field is therefore `string` and is only ever formatted,
 * never arithmetic'd — `format.ts` is the one place that turns it into something printable.
 *
 * **`simulated` and `environment` are required, not optional.** A response from the paper namespace
 * that omits them is a defect, and an optional field would let that defect render as a plausible
 * balance. Making them required means the compiler refuses to build a component that forgets to ask.
 */

export type EnvironmentName =
  | "DISABLED"
  | "OBSERVE"
  | "RESEARCH"
  | "SHADOW"
  | "PAPER"
  | "PILOT"
  | "LIVE";

export interface Simulated {
  /** Always true for anything from the paper namespace. The UI must never hide it. */
  simulated: boolean;
  environment: EnvironmentName | string;
}

export interface PaperPosition extends Simulated {
  instrument_id: string;
  venue: string;
  quantity: string;
  side: "LONG" | "SHORT" | "FLAT";
  average_entry: string;
  mark: string | null;
  realized_pnl: string;
  unrealized_pnl: string;
  commission_paid: string;
  notional: string;
  fills: number;
  opened_at: string | null;
  updated_at: string | null;
  /** Whether `mark` is a real observed price. When false the P&L is carried at entry — an
   *  assumption, and one the screen has to name rather than let the reader assume away. */
  marked_with_real_data: boolean;
}

export interface PaperAccount extends Simulated {
  account_id: string;
  currency: string;
  simulated_cash: string;
  starting_cash: string;
  equity: string;
  realized_pnl: string;
  unrealized_pnl: string;
  commission_paid: string;
  net_pnl: string;
  return_pct: string;
  positions: PaperPosition[];
  open_position_count: number;
  fills_applied: number;
  positions_marked_with_real_data: number;
  positions_carried_at_entry: string[];
  updated_at: string;
}

export interface PaperAccountResponse extends PaperAccount {
  disabled?: boolean;
}

export interface FillModelDescription {
  slippage_bps: string;
  commission_bps: string;
  minimum_commission: string;
  latency_ms: number;
  max_quote_age_seconds: string;
  respect_displayed_size: boolean;
  refuse_delayed_data: boolean;
  seed: number;
  simulated: true;
}

export interface PaperFill extends Simulated {
  fill_id: string;
  order_id: string;
  instrument_id: string;
  venue: string;
  side: "BUY" | "SELL";
  quantity: string;
  /** What was actually paid: the real quote's executable side, moved adversely by slippage. */
  price: string;
  commission: string;
  currency: string;
  /** The real price the fill executed against, kept beside it so cost is never invisible. */
  reference_price: string;
  bid_at_fill: string | null;
  ask_at_fill: string | null;
  quote_source: string;
  quote_observed_at: string | null;
  latency_ms: number;
  slippage_bps_applied: string;
  filled_at: string;
}

export interface PaperOrder extends Simulated {
  status: "SIMULATED" | "SIMULATED_PARTIAL" | "UNFILLED" | "REFUSED";
  intent_id: string;
  order_id: string;
  order_state: string;
  instrument_id: string;
  venue: string;
  side: string;
  quantity: string;
  filled_quantity: string;
  average_price: string | null;
  total_commission: string | null;
  no_fill_reason: string | null;
  reasons: string[];
  mark?: string | null;
  account_id?: string;
  at: string;
}

export interface AnalysisEvidence {
  mid?: string;
  bid?: string;
  ask?: string;
  spread_bps?: string;
  momentum_bps?: string;
  window_observations?: number;
  window_span_seconds?: string | null;
  size_imbalance?: string | null;
  source?: string;
  age_seconds?: string | null;
  mark_is_mid?: boolean;
}

export interface AnalysisVerdict {
  analysis_id: string;
  instrument_id: string;
  venue: string;
  verb: "ACCEPT" | "REJECT" | "WAIT" | "REDUCE" | "EXIT" | "ESCALATE" | "ABSTAIN";
  confidence: string;
  in_confidence_band: boolean;
  confidence_band: [string, string];
  actionable: boolean;
  reasons: string[];
  evidence: AnalysisEvidence;
  observations_used: number;
  analysed_at: string;
  elapsed_ms: number;
  /** Present when the loop held the trade back: cooldown, position limit, or sizing. */
  blocked?: string;
}

export interface LoopStats extends Simulated {
  quotes_observed: number;
  analyses_run: number;
  analyses_throttled: number;
  actionable_verdicts: number;
  intents_created: number;
  trades_simulated: number;
  trades_refused: number;
  trades_unfilled: number;
  blocked_by_position_limit: number;
  blocked_by_cooldown: number;
  blocked_by_sizing: number;
  last_analysis_elapsed_ms: number;
  slowest_analysis_ms: number;
  started_at: string | null;
  stopped_at: string | null;
  running: boolean;
  instruments_tracked: number;
  queue_depth: number;
}

export interface PaperEngineDescription {
  engine: "paper";
  simulated: true;
  environment: "PAPER";
  can_place_live_orders: false;
  is_venue_adapter: false;
  adapter_count: number;
  account_id: string;
  currency: string;
  fill_model: FillModelDescription;
  ledger: { backend: string; durable?: boolean; orders?: number; fills?: number };
  halt_connected: boolean;
}

export interface PaperOverview extends Simulated {
  platform: "paper";
  enabled: boolean;
  can_place_live_orders: false;
  is_venue_adapter: false;
  adapter_count: number;
  network_access: false;
  credentials_required: false;
  stream_interval_seconds: number;
  engine: PaperEngineDescription;
  analyzer: Record<string, unknown>;
  loop: Record<string, unknown>;
  stats: LoopStats;
  account: PaperAccount;
}

export interface PhaseGate {
  phase: number;
  name: string;
  live_trading: boolean;
  venue_adapters: boolean;
  real_money_orders_possible: boolean;
  market_data_sources: boolean;
  order_capability: boolean;
}

export interface LiveAuthority {
  status: "GRANTED" | "DENIED";
  blocking_reasons?: string[];
  [key: string]: unknown;
}

export interface SystemStatus {
  app: { name: string; version: string; phase: string };
  phase_gate: PhaseGate;
  environment: EnvironmentName | string;
  time_utc: string;
  halt: { scope: string; active: boolean; reason?: string };
  live_authority: LiveAuthority;
  paper: {
    enabled: boolean;
    simulated: true;
    environment: "PAPER";
    can_place_live_orders: false;
    is_venue_adapter: false;
    stats: LoopStats;
  };
  cost_constraint: string;
  persistence?: { engine: string; ephemeral: boolean; path: string | null };
}

export interface PaperStreamFrame extends Simulated {
  interval_seconds: number;
  account: PaperAccount;
  stats: LoopStats;
  latest_analysis: AnalysisVerdict[];
}
