"use client";

/**
 * Page 9 — Execution Room (docs/03 §2).
 *
 * Ruled content: order blotter, live order states, fills, slippage, venue health, rejected orders,
 * reconciliation, kill switch. What is served here is the paper equivalent of all of it, and the
 * differences are stated rather than smoothed over:
 *
 * - **Venue health** has nothing to report, because no venue is connected. That is rendered as an
 *   explicit "no adapters", not as a green tick.
 * - **The kill switch is shown but not armed from here.** `POST /v1/halt` requires owner authority
 *   (`_require_owner`), so a button on this page would be refused. A control that cannot work is
 *   worse than an explanation of how to use the one that can.
 * - **Slippage is a first-class column**, not a footnote. It is the number that decides whether a
 *   strategy survives contact with a real venue, and it is the reason this page exists.
 */

import { useQuery } from "@tanstack/react-query";

import {
  DataTable,
  Panel,
  Provenance,
  ReasonList,
  SimulatedBanner,
  Stat,
  StatusDot,
  type Column,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatBps, formatMoney, formatPrice, formatQuantity, formatTimestamp } from "@/lib/format";
import type { PaperFill, PaperOrder } from "@/lib/types";

export default function ExecutionRoom() {
  const orders = useQuery({ queryKey: ["paper", "orders"], queryFn: ({ signal }) => api.orders(200, signal) });
  const fills = useQuery({ queryKey: ["paper", "fills"], queryFn: ({ signal }) => api.fills(300, signal) });
  const status = useQuery({ queryKey: ["status"], queryFn: ({ signal }) => api.status(signal) });
  const overview = useQuery({ queryKey: ["paper"], queryFn: ({ signal }) => api.paper(signal) });

  const all = orders.data?.orders ?? [];
  const refused = all.filter((order) => order.status === "REFUSED");
  const unfilled = all.filter((order) => order.status === "UNFILLED");
  const partial = all.filter((order) => order.status === "SIMULATED_PARTIAL");
  const halt = status.data?.halt;

  return (
    <div className="space-y-4">
      <SimulatedBanner detail="simulated execution — no venue is connected and none can be reached" />

      <h1 className="text-heading">Execution Room</h1>

      <div className="grid gap-4 lg:grid-cols-4">
        <Panel title="Blotter" subtitle="Every simulated order and its terminal state">
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Stat label="Orders" value={orders.data?.count ?? "—"} />
            <Stat label="Filled" value={all.length - refused.length - unfilled.length} tone="positive" />
            <Stat label="Partial" value={partial.length} tone="warning" />
            <Stat label="Unfilled" value={unfilled.length} tone="warning" />
            <Stat label="Refused" value={refused.length} tone="negative" />
            <Stat
              label="Commission"
              value={fills.data ? formatMoney(fills.data.total_commission, { symbol: "$" }) : "—"}
              tone="warning"
            />
          </div>
        </Panel>

        <Panel title="Venue health" subtitle="Adapters connected, and what that means here">
          <dl className="space-y-2.5 text-data">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Adapters</dt>
              <dd className="numeric">{overview.data?.adapter_count ?? "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Network access</dt>
              <dd className="numeric">{overview.data ? String(overview.data.network_access) : "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Credentials</dt>
              <dd className="numeric">
                {overview.data ? String(overview.data.credentials_required) : "—"}
              </dd>
            </div>
          </dl>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            There is no venue health to report: the paper engine holds no adapter and opens no
            connection. That is why it cannot send an order, and it is stated here rather than shown
            as a healthy tick.
          </p>
        </Panel>

        <Panel title="Kill switch" subtitle="Governance, and why it is not a button on this page">
          <div className="space-y-2.5 text-data">
            <StatusDot
              active={halt?.active ?? false}
              label={halt?.active ? `ENGAGED ${halt.scope}` : `clear (${halt?.scope ?? "NONE"})`}
              tone={halt?.active ? "negative" : "positive"}
            />
            {halt?.reason ? <p className="text-muted">reason: {halt.reason}</p> : null}
            <p className="border-t border-line pt-3 text-muted">
              Engaging or releasing a halt requires owner authority
              (<span className="numeric">POST /v1/halt</span>), so this page reports the state rather
              than offering a control that would be refused. A halt also stops the paper loop from
              opening positions — closing them stays allowed, so a halt cannot trap a position.
            </p>
          </div>
        </Panel>

        <Panel title="Reconciliation" subtitle="Whether the ledger and the account agree">
          <p className="text-data text-muted">
            The account is a projection of the fill ledger and can be rebuilt from it
            (<span className="numeric">rebuild_from_fills</span>), which is what makes a disagreement
            recoverable rather than terminal. A live reconciliation against a venue statement is not
            part of the paper platform: there is no venue to reconcile with.
          </p>
          <dl className="mt-3 space-y-2 border-t border-line pt-3 text-data">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Fills recorded</dt>
              <dd className="numeric">{fills.data?.count ?? "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Ledger backend</dt>
              <dd className="numeric">{overview.data?.engine.ledger.backend ?? "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Durable</dt>
              <dd className="numeric">
                {overview.data?.engine.ledger.durable === false ? (
                  <span className="text-warning">⚠ no — in-process only</span>
                ) : (
                  String(overview.data?.engine.ledger.durable ?? "—")
                )}
              </dd>
            </div>
          </dl>
        </Panel>
      </div>

      <Panel title="Order blotter" subtitle="Newest first, with the reason for every state">
        <DataTable<PaperOrder>
          rows={orders.data?.orders}
          columns={orderColumns}
          rowKey={(row) => row.order_id}
          loading={orders.isLoading}
          error={orders.error ? String(orders.error.message) : null}
          empty="No orders yet. The paper loop has not acted — start it on the Paper Trading page."
          caption="Simulated order blotter"
        />
      </Panel>

      <Panel
        title="Fills"
        subtitle="Each fill against the real quote it executed on, and what it cost"
        aside={
          <span className="numeric text-data text-muted">
            {fills.data ? `${fills.data.count} fills` : ""}
          </span>
        }
      >
        <DataTable<PaperFill>
          rows={fills.data?.fills}
          columns={fillColumns}
          rowKey={(row) => row.fill_id}
          loading={fills.isLoading}
          error={fills.error ? String(fills.error.message) : null}
          empty="No fills. An order that could not be executed against a real quote stays unfilled rather than being filled at a price nobody quoted."
          caption="Simulated fills"
        />
      </Panel>
    </div>
  );
}

const orderColumns: Column<PaperOrder>[] = [
  { key: "at", header: "At (UTC)", numeric: true, render: (row) => <span className="text-muted">{formatTimestamp(row.at)}</span> },
  { key: "order", header: "Order", render: (row) => <span className="numeric text-secondary">{row.order_id}</span> },
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument_id}</span> },
  { key: "venue", header: "Venue", render: (row) => row.venue },
  {
    key: "side",
    header: "Side",
    render: (row) => (
      <span className={row.side === "BUY" || row.side === "LONG" ? "text-positive" : "text-negative"}>
        {row.side === "BUY" || row.side === "LONG" ? "▲" : "▼"} {row.side}
      </span>
    ),
  },
  { key: "qty", header: "Qty", numeric: true, render: (row) => formatQuantity(row.quantity) },
  { key: "filled", header: "Filled", numeric: true, render: (row) => formatQuantity(row.filled_quantity) },
  { key: "price", header: "Avg price", numeric: true, render: (row) => formatPrice(row.average_price) },
  {
    key: "state",
    header: "State",
    render: (row) => (
      <span
        className={
          row.status === "REFUSED"
            ? "text-negative"
            : row.status === "UNFILLED"
              ? "text-warning"
              : "text-positive"
        }
      >
        {row.status === "SIMULATED" ? "●" : row.status === "REFUSED" ? "✕" : "◐"} {row.order_state}
      </span>
    ),
  },
  {
    key: "reasons",
    header: "Reasons",
    render: (row) => <ReasonList reasons={row.reasons} limit={2} />,
  },
];

const fillColumns: Column<PaperFill>[] = [
  { key: "at", header: "Filled (UTC)", numeric: true, render: (row) => <span className="text-muted">{formatTimestamp(row.filled_at)}</span> },
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument_id}</span> },
  {
    key: "side",
    header: "Side",
    render: (row) => (
      <span className={row.side === "BUY" ? "text-positive" : "text-negative"}>
        {row.side === "BUY" ? "▲" : "▼"} {row.side}
      </span>
    ),
  },
  { key: "qty", header: "Qty", numeric: true, render: (row) => formatQuantity(row.quantity) },
  {
    key: "reference",
    header: "Quoted",
    numeric: true,
    render: (row) => <span className="text-muted">{formatPrice(row.reference_price)}</span>,
  },
  { key: "price", header: "Paid", numeric: true, render: (row) => formatPrice(row.price) },
  {
    key: "slippage",
    header: "Slippage",
    numeric: true,
    render: (row) => (
      <span className="text-warning" title="Applied against the order, never in its favour">
        {formatBps(row.slippage_bps_applied)}
      </span>
    ),
  },
  { key: "commission", header: "Commission", numeric: true, render: (row) => formatMoney(row.commission, { symbol: "$" }) },
  { key: "latency", header: "Latency", numeric: true, render: (row) => `${row.latency_ms} ms` },
  {
    key: "quote",
    header: "Quote it filled on",
    render: (row) => (
      <Provenance
        source={row.quote_source}
        observedAt={row.quote_observed_at}
        staleAfterSeconds={30}
      />
    ),
  },
];
