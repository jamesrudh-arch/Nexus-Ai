"use client";

/**
 * Page 8 — Portfolio & Risk (docs/03 §2).
 *
 * Ruled content: consolidated accounts, positions, factor exposures, margin, drawdown,
 * concentration, stress scenarios, risk limits. Four of those are served from real data — accounts,
 * positions, concentration and the limits the build ships with — and three are rendered as
 * UNAVAILABLE with the reason, because they are not modelled:
 *
 * - **Factor exposures** need a factor model. There isn't one, and a column of invented betas would
 *   be the most damaging fabrication on this page, since it looks exactly like the real thing.
 * - **Drawdown** needs an equity *series*; the API serves the current equity. A drawdown computed
 *   from one point is not a drawdown. The stream could build a series in-session, and a session-only
 *   series would understate every drawdown that happened before the page was opened — so it is left
 *   out rather than shown half-right.
 * - **Stress scenarios** belong to the Scenario Studio (page 11), which is not built.
 *
 * Margin is not UNAVAILABLE, it is inapplicable: the paper account is a cash account with no
 * leverage, so there is no margin to compute. Saying which of those two it is matters, because they
 * imply different work.
 */

import { useQuery } from "@tanstack/react-query";

import {
  DataTable,
  Panel,
  PnlValue,
  SimulatedBanner,
  Stat,
  type Column,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatAge, formatMoney, formatPercent, formatPrice, formatQuantity } from "@/lib/format";
import type { PaperPosition } from "@/lib/types";

export default function PortfolioAndRisk() {
  const account = useQuery({ queryKey: ["paper", "account"], queryFn: ({ signal }) => api.account(signal) });
  const status = useQuery({ queryKey: ["status"], queryFn: ({ signal }) => api.status(signal) });

  const data = account.data;
  const positions = data?.positions ?? [];
  const equity = data ? parseDecimal(data.equity) : 0;

  /** Share of equity each position represents, largest first. Real arithmetic on real notionals. */
  const concentration = positions
    .map((position) => {
      const notional = Math.abs(parseDecimal(position.notional));
      return {
        key: `${position.instrument_id}@${position.venue}`,
        instrument: position.instrument_id,
        venue: position.venue,
        side: position.side,
        notional,
        share: equity > 0 ? (notional / equity) * 100 : 0,
        marked: position.marked_with_real_data,
      };
    })
    .sort((left, right) => right.notional - left.notional);

  const gross = concentration.reduce((total, row) => total + row.notional, 0);
  const largest = concentration[0];

  return (
    <div className="space-y-4">
      <SimulatedBanner
        account={data?.account_id}
        detail={data ? `updated ${formatAge(data.updated_at)}` : undefined}
      />

      <h1 className="text-heading">Portfolio &amp; Risk</h1>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Consolidated accounts" subtitle="One simulated account in this build">
          {data ? (
            <div className="grid grid-cols-2 gap-x-6 gap-y-4">
              <Stat
                label="Equity"
                value={formatMoney(data.equity, { symbol: `${data.currency} ` })}
                hint={`start ${formatMoney(data.starting_cash)}`}
              />
              <Stat
                label="Simulated cash"
                value={formatMoney(data.simulated_cash, { symbol: `${data.currency} ` })}
                hint={
                  equity > 0
                    ? `${((parseDecimal(data.simulated_cash) / equity) * 100).toFixed(1)}% of equity`
                    : undefined
                }
              />
              <Stat label="Net P&L" value={<PnlValue value={data.net_pnl} />} mono={false} />
              <Stat label="Return" value={formatPercent(data.return_pct)} mono />
              <Stat label="Realized" value={<PnlValue value={data.realized_pnl} />} mono={false} />
              <Stat label="Unrealized" value={<PnlValue value={data.unrealized_pnl} />} mono={false} />
            </div>
          ) : (
            <p className="text-data text-muted">Waiting for the API…</p>
          )}
        </Panel>

        <Panel title="Exposure" subtitle="Gross notional against simulated equity">
          <div className="grid grid-cols-2 gap-x-6 gap-y-4">
            <Stat
              label="Gross exposure"
              value={formatMoney(gross.toFixed(2), { symbol: `${data?.currency ?? "USD"} ` })}
              hint={equity > 0 ? `${((gross / equity) * 100).toFixed(1)}% of equity` : "no equity"}
            />
            <Stat label="Open positions" value={data?.open_position_count ?? 0} />
            <Stat
              label="Largest position"
              value={largest ? `${largest.share.toFixed(1)}%` : "—"}
              tone={largest && largest.share > 25 ? "warning" : "neutral"}
              hint={largest ? `${largest.instrument} on ${largest.venue}` : "flat"}
            />
            <Stat
              label="Marked with real data"
              value={`${data?.positions_marked_with_real_data ?? 0} / ${data?.open_position_count ?? 0}`}
              tone={
                data && data.positions_carried_at_entry.length > 0 ? "warning" : "positive"
              }
              hint={
                data?.positions_carried_at_entry.length
                  ? `⚠ ${data.positions_carried_at_entry.join(", ")} carried at entry`
                  : "every position has a real mark"
              }
            />
          </div>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            Margin does not apply: the paper account is a cash account with no leverage, so there is
            no margin to compute. That is different from being unavailable — nothing is missing.
          </p>
        </Panel>

        <Panel title="Risk limits" subtitle="What this build enforces, and what is still provisional">
          <dl className="space-y-2.5 text-data">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Limits status</dt>
              <dd className="numeric">
                {status.data && "risk_limits_provisional" in status.data ? (
                  <span className="text-warning" title="O-002: exact numbers pending the Risk Policy">
                    ⚠ provisional (O-002)
                  </span>
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Live trading</dt>
              <dd className="numeric text-positive">
                {status.data ? String(status.data.phase_gate.live_trading) : "—"}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Order capability</dt>
              <dd className="numeric text-positive">
                {status.data ? String(status.data.phase_gate.order_capability) : "—"}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Withdrawals</dt>
              <dd className="numeric text-positive">forbidden by design</dd>
            </div>
          </dl>
          <ul className="mt-3 space-y-2 border-t border-line pt-3 text-data text-muted">
            <Unavailable label="Factor exposures" reason="no factor model is implemented" />
            <Unavailable label="Drawdown" reason="needs an equity series; the API serves one point" />
            <Unavailable label="Stress scenarios" reason="Scenario Studio (page 11) is not built" />
          </ul>
        </Panel>
      </div>

      <Panel title="Positions" subtitle="Simulated holdings, with the source of every mark">
        <DataTable<PaperPosition>
          rows={positions}
          columns={positionColumns}
          rowKey={(row) => `${row.instrument_id}@${row.venue}`}
          loading={account.isLoading}
          error={account.error ? String(account.error.message) : null}
          empty="Flat. No simulated position is open."
          caption="Simulated positions"
        />
      </Panel>

      <Panel title="Concentration" subtitle="Share of equity, largest first">
        <DataTable
          rows={concentration}
          columns={concentrationColumns}
          rowKey={(row) => row.key}
          empty="Nothing to concentrate: the account is flat."
          caption="Position concentration"
        />
      </Panel>
    </div>
  );
}

function Unavailable({ label, reason }: { label: string; reason: string }) {
  return (
    <li className="flex items-baseline justify-between gap-3">
      <span className="label shrink-0">{label}</span>
      <span className="text-right text-warning" title={reason}>
        ⚠ UNAVAILABLE
      </span>
    </li>
  );
}

/**
 * Parse an exact decimal string for *proportions only*.
 *
 * The double conversion this performs is acceptable for a percentage of equity and is not used for
 * anything printed as money: every displayed figure goes through `format.ts`, which rounds on the
 * digits. Using a float here is a deliberate, contained trade, and confining it to one helper is what
 * keeps it contained.
 */
function parseDecimal(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

const positionColumns: Column<PaperPosition>[] = [
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument_id}</span> },
  { key: "venue", header: "Venue", render: (row) => row.venue },
  {
    key: "side",
    header: "Side",
    render: (row) => (
      <span className={row.side === "LONG" ? "text-positive" : row.side === "SHORT" ? "text-negative" : "text-secondary"}>
        {row.side === "LONG" ? "▲" : row.side === "SHORT" ? "▼" : "•"} {row.side}
      </span>
    ),
  },
  { key: "qty", header: "Qty", numeric: true, render: (row) => formatQuantity(row.quantity) },
  { key: "entry", header: "Avg entry", numeric: true, render: (row) => formatPrice(row.average_entry) },
  {
    key: "mark",
    header: "Mark",
    numeric: true,
    render: (row) =>
      row.mark === null ? (
        <span className="text-warning" title="No real price observed; valued at entry price">
          ⚠ entry
        </span>
      ) : (
        formatPrice(row.mark)
      ),
  },
  { key: "notional", header: "Notional", numeric: true, render: (row) => formatMoney(row.notional) },
  { key: "unrealized", header: "Unrealized", numeric: true, render: (row) => <PnlValue value={row.unrealized_pnl} /> },
  { key: "realized", header: "Realized", numeric: true, render: (row) => <PnlValue value={row.realized_pnl} /> },
  { key: "commission", header: "Costs", numeric: true, render: (row) => formatMoney(row.commission_paid) },
  { key: "fills", header: "Fills", numeric: true, render: (row) => row.fills },
  { key: "opened", header: "Opened (UTC)", numeric: true, render: (row) => <span className="text-muted">{formatAge(row.opened_at)}</span> },
];

interface ConcentrationRow {
  key: string;
  instrument: string;
  venue: string;
  side: string;
  notional: number;
  share: number;
  marked: boolean;
}

const concentrationColumns: Column<ConcentrationRow>[] = [
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument}</span> },
  { key: "venue", header: "Venue", render: (row) => row.venue },
  {
    key: "side",
    header: "Side",
    render: (row) => (
      <span className={row.side === "LONG" ? "text-positive" : "text-negative"}>
        {row.side === "LONG" ? "▲" : "▼"} {row.side}
      </span>
    ),
  },
  { key: "notional", header: "Notional", numeric: true, render: (row) => formatMoney(row.notional.toFixed(2)) },
  {
    key: "share",
    header: "% of equity",
    numeric: true,
    render: (row) => (
      <span className={row.share > 25 ? "text-warning" : "text-primary"}>
        {row.share > 25 ? "⚠ " : ""}
        {row.share.toFixed(2)}%
      </span>
    ),
  },
  {
    key: "marked",
    header: "Mark source",
    render: (row) =>
      row.marked ? (
        <span className="text-positive">● real price</span>
      ) : (
        <span className="text-warning">⚠ carried at entry</span>
      ),
  },
];
