"use client";

/**
 * The shared components. Three of the rules in docs/03 §3.3–§3.5 are implemented here rather than
 * left to each page to remember, because a rule that depends on every author recalling it is a rule
 * that will be broken:
 *
 * - **Colour is never the sole signal.** `PnlValue` always renders a glyph and a sign alongside the
 *   colour. `StatusDot` always renders a shape and a word.
 * - **Nothing simulated is shown as though it were real.** `SimulatedBanner` and `EnvironmentBadge`
 *   are not decorative; the paper pages cannot render their numbers without them, because
 *   `PaperAccount` requires `simulated` and `environment` to exist.
 * - **Every value says where it came from.** `Provenance` prints source, venue, timezone, delay and
 *   staleness, which is what §3.5 demands of every chart and every figure.
 */

import type { ReactNode } from "react";

import { formatAge, pnlTone, signOf, splitReason } from "@/lib/format";

/* ------------------------------------------------------------------ surfaces */

export function Panel({
  title,
  subtitle,
  children,
  aside,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <section className="rounded-md border border-line bg-panel">
      <header className="flex items-baseline justify-between gap-4 border-b border-line px-4 py-3">
        <div>
          <h2 className="text-card text-primary">{title}</h2>
          {subtitle ? <p className="label mt-0.5">{subtitle}</p> : null}
        </div>
        {aside ? <div className="shrink-0">{aside}</div> : null}
      </header>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

/** A labelled figure. Not a tile: §3.4 permits cards only for meaningfully grouped information. */
export function Stat({
  label,
  value,
  hint,
  tone = "neutral",
  mono = true,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "positive" | "negative" | "warning" | "info";
  mono?: boolean;
}) {
  const colour =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : tone === "warning"
          ? "text-warning"
          : tone === "info"
            ? "text-info"
            : "text-primary";
  return (
    <div className="min-w-0">
      <div className="label truncate">{label}</div>
      <div className={`mt-1 text-heading ${colour} ${mono ? "numeric" : ""}`}>{value}</div>
      {hint ? <div className="mt-1 text-data text-muted">{hint}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ semantics */

const ENVIRONMENT_GLYPH: Record<string, string> = {
  DISABLED: "○",
  OBSERVE: "○",
  RESEARCH: "◇",
  SHADOW: "◐",
  PAPER: "▤",
  PILOT: "◑",
  LIVE: "●",
};

/**
 * The environment badge. Shape + word + colour, in that order of importance: §3.3 requires the shape
 * and the label to carry the meaning, so the badge still reads correctly in greyscale.
 */
export function EnvironmentBadge({ environment }: { environment: string }) {
  const glyph = ENVIRONMENT_GLYPH[environment] ?? "○";
  const tone =
    environment === "LIVE"
      ? "border-negative/60 text-negative"
      : environment === "PAPER"
        ? "border-warning/60 text-warning"
        : environment === "SHADOW" || environment === "PILOT"
          ? "border-info/60 text-info"
          : "border-line text-secondary";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-label ${tone}`}
      title={`Environment: ${environment}`}
    >
      <span aria-hidden="true">{glyph}</span>
      {environment}
    </span>
  );
}

/**
 * The banner that says the numbers are not real.
 *
 * Rendered on every paper page, above the fold, and it is not dismissible. `docs/03` §3.5 forbids a
 * fake balance that does not announce itself; a banner the user can close is an announcement that
 * stops being one.
 */
export function SimulatedBanner({
  environment = "PAPER",
  account,
  detail,
}: {
  environment?: string;
  account?: string;
  detail?: string;
}) {
  return (
    <div
      role="note"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border border-warning/50 bg-warning/10 px-4 py-2.5"
    >
      <span className="text-label font-semibold text-warning" aria-hidden="true">
        ⚠ SIMULATED
      </span>
      <span className="text-body text-primary">
        Paper trading — no real money, no real orders, and no connection to any venue.
      </span>
      <EnvironmentBadge environment={environment} />
      {account ? <span className="numeric text-data text-secondary">account {account}</span> : null}
      {detail ? <span className="text-data text-muted">{detail}</span> : null}
    </div>
  );
}

/** A P&L figure: glyph, sign, colour. All three, because any one of them can be unavailable. */
export function PnlValue({
  value,
  symbol = "",
  className = "",
}: {
  value: string | null | undefined;
  symbol?: string;
  className?: string;
}) {
  const tone = pnlTone(value);
  const sign = signOf(value);
  const colour =
    tone === "positive" ? "text-positive" : tone === "negative" ? "text-negative" : "text-secondary";
  return (
    <span className={`numeric ${colour} ${className}`}>
      <span aria-hidden="true">{sign > 0 ? "▲" : sign < 0 ? "▼" : "•"}</span>{" "}
      <span className="sr-only">{sign > 0 ? "profit " : sign < 0 ? "loss " : "flat "}</span>
      {symbol}
      {formatSigned(value)}
    </span>
  );
}

function formatSigned(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const sign = signOf(value);
  const unsigned = value.replace(/^[+-]/, "");
  const [integer = "0", fraction = ""] = unsigned.split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const body = fraction ? `${grouped}.${fraction.slice(0, 2)}` : `${grouped}.00`;
  return `${sign > 0 ? "+" : sign < 0 ? "−" : ""}${body}`;
}

/** ● LIVE / ◐ SHADOW / ○ OBSERVE — a status that is legible without colour. */
export function StatusDot({
  active,
  label,
  tone = "info",
}: {
  active: boolean;
  label: string;
  tone?: "positive" | "negative" | "warning" | "info" | "muted";
}) {
  const colour =
    tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : tone === "warning"
          ? "text-warning"
          : tone === "muted"
            ? "text-muted"
            : "text-info";
  return (
    <span className={`inline-flex items-center gap-1.5 text-data ${colour}`}>
      <span aria-hidden="true">{active ? "●" : "○"}</span>
      {label}
    </span>
  );
}

/* ------------------------------------------------------------------ data */

export interface Column<Row> {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  /** Data columns are right-aligned and monospaced (§3.2). */
  numeric?: boolean;
}

/**
 * A dense table with explicit empty, loading and error states.
 *
 * §3.4 requires all three, and the empty state in particular is not allowed to be a blank rectangle:
 * on a paper blotter, "no trades yet" and "the feed is disconnected" are different facts and lead to
 * different actions.
 */
export function DataTable<Row>({
  rows,
  columns,
  rowKey,
  empty,
  loading,
  error,
  caption,
}: {
  rows: Row[] | undefined;
  columns: Column<Row>[];
  rowKey: (row: Row) => string;
  empty: ReactNode;
  loading?: boolean;
  error?: string | null;
  caption?: string;
}) {
  if (loading && (!rows || rows.length === 0)) {
    return <p className="py-6 text-center text-data text-muted">Loading…</p>;
  }
  if (error) {
    return (
      <p role="alert" className="py-6 text-center text-data text-negative">
        ⚠ {error}
      </p>
    );
  }
  if (!rows || rows.length === 0) {
    return <p className="py-6 text-center text-data text-muted">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-data">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr className="border-b border-line">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={`label whitespace-nowrap px-2 py-2 font-normal ${
                  column.numeric ? "text-right" : "text-left"
                }`}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line/60 last:border-0">
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={`whitespace-nowrap px-2 py-1.5 ${
                    column.numeric ? "numeric text-right" : "text-left"
                  }`}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * `CODE:detail` reasons, rendered with the code as the emphasis.
 *
 * The backend's convention puts the machine-readable code first. Showing the detail alone would read
 * better and be less useful: an operator searching the audit log for `STALE_QUOTE` needs the code to
 * appear exactly as it is stored.
 */
export function ReasonList({ reasons, limit }: { reasons: string[]; limit?: number }) {
  if (!reasons.length) return <span className="text-muted">—</span>;
  const shown = limit ? reasons.slice(0, limit) : reasons;
  return (
    <ul className="space-y-1">
      {shown.map((reason) => {
        const { code, detail } = splitReason(reason);
        return (
          <li key={reason} className="flex flex-wrap gap-x-2">
            <span className="numeric text-label text-warning">{code}</span>
            {detail ? <span className="text-data text-secondary">{detail}</span> : null}
          </li>
        );
      })}
      {limit && reasons.length > limit ? (
        <li className="text-data text-muted">+{reasons.length - limit} more</li>
      ) : null}
    </ul>
  );
}

/** Where a number came from: source, venue, delay, staleness. §3.5 requires all of it be visible. */
export function Provenance({
  source,
  venue,
  instrument,
  delayed,
  observedAt,
  staleAfterSeconds,
}: {
  source?: string | null;
  venue?: string | null;
  instrument?: string | null;
  delayed?: boolean;
  observedAt?: string | null;
  staleAfterSeconds?: number;
}) {
  const age = observedAt ? secondsSince(observedAt) : null;
  const stale = age !== null && staleAfterSeconds !== undefined && age > staleAfterSeconds;
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-data text-muted">
      {instrument ? <span className="numeric text-secondary">{instrument}</span> : null}
      {venue ? <span>{venue}</span> : null}
      {source ? <span className="numeric">{source}</span> : null}
      {delayed ? (
        <span className="text-warning" title="This feed is delayed; the edge measured on it is not ours">
          ⚠ DELAYED
        </span>
      ) : null}
      {stale ? (
        <span className="text-warning" title="Older than the age this system will act on">
          ⚠ STALE {formatAge(observedAt)}
        </span>
      ) : observedAt ? (
        <span>{formatAge(observedAt)}</span>
      ) : null}
      <span title="All times are UTC">UTC</span>
    </span>
  );
}

function secondsSince(iso: string): number | null {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  return Math.max(0, (Date.now() - then) / 1000);
}

/** The stream's own health, shown beside the data it carries. */
export function StreamStatus({
  state,
  ageSeconds,
  intervalSeconds,
  error,
}: {
  state: string;
  ageSeconds: number | null;
  intervalSeconds: number | null;
  error: string | null;
}) {
  const tone =
    state === "open"
      ? ageSeconds !== null && intervalSeconds !== null && ageSeconds > intervalSeconds * 4
        ? "warning"
        : "positive"
      : state === "connecting"
        ? "warning"
        : state === "error"
          ? "negative"
          : "muted";
  const label =
    state === "open" ? "LIVE STREAM" : state === "connecting" ? "RECONNECTING" : state.toUpperCase();
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      <StatusDot active={state === "open"} label={label} tone={tone as "positive"} />
      {ageSeconds !== null ? (
        <span className="numeric text-data text-muted">
          last frame {ageSeconds < 1 ? "<1" : Math.round(ageSeconds)}s ago
        </span>
      ) : null}
      {intervalSeconds !== null ? (
        <span className="numeric text-data text-muted" title="The cadence the server declared">
          interval {intervalSeconds}s
        </span>
      ) : null}
      {error ? (
        <span role="alert" className="text-data text-warning">
          ⚠ {error}
        </span>
      ) : null}
    </div>
  );
}

/** A button that says what it will do, and confirms the destructive ones. */
export function ActionButton({
  children,
  onClick,
  tone = "ghost",
  disabled,
  confirm,
  title,
}: {
  children: ReactNode;
  onClick: () => void;
  tone?: "primary" | "danger" | "ghost";
  disabled?: boolean;
  /** Text for a confirmation prompt. Required for anything that discards state. */
  confirm?: string;
  title?: string;
}) {
  const palette =
    tone === "danger"
      ? "border-negative/60 text-negative hover:bg-negative/10"
      : tone === "primary"
        ? "border-info/60 text-info hover:bg-info/10"
        : "border-line text-secondary hover:bg-elevated";
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={() => {
        // The confirmation names the exact consequence rather than asking "are you sure?", because a
        // prompt that does not say what will be lost gets clicked through.
        if (confirm && !window.confirm(confirm)) return;
        onClick();
      }}
      className={`rounded border px-3 py-1.5 text-label transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${palette}`}
    >
      {children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-6 text-center text-data text-muted">{children}</p>;
}
