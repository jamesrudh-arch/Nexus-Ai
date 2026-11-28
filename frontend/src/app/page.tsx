"use client";

/**
 * Page 1 — Command Centre (docs/03 §2).
 *
 * Ruled content: global equity, realized/unrealized P&L, exposure, live risk, system health, market
 * regime, active research, open positions, decision queue. Every one of those is here. One of them —
 * market regime — is rendered as UNAVAILABLE, because no regime model exists in the backend and
 * inventing a label for it would be exactly the fabrication §3.5 forbids. An honest gap on a
 * dashboard tells an operator where the work is; a plausible guess tells them nothing and will be
 * believed.
 *
 * The page is a client component: everything on it moves, and a server render would be stale before
 * it painted.
 */

import { useQuery } from "@tanstack/react-query";

import {
  DataTable,
  EnvironmentBadge,
  Panel,
  PnlValue,
  ReasonList,
  SimulatedBanner,
  Stat,
  StatusDot,
  StreamStatus,
  type Column,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatAge, formatMoney, formatPercent, formatPrice, formatQuantity } from "@/lib/format";
import { usePaperStream, useStreamAge } from "@/lib/usePaperStream";
import type { AnalysisVerdict, PaperPosition } from "@/lib/types";

export default function CommandCentre() {
  const status = useQuery({ queryKey: ["status"], queryFn: ({ signal }) => api.status(signal) });
  const overview = useQuery({ queryKey: ["paper"], queryFn: ({ signal }) => api.paper(signal) });
  const positions = useQuery({
    queryKey: ["paper", "positions"],
    queryFn: ({ signal }) => api.positions(signal),
  });
  const decisions = useQuery({
    queryKey: ["paper", "analysis"],
    queryFn: ({ signal }) => api.analysis(12, signal),
  });
  const dossiers = useQuery({
    queryKey: ["dossiers"],
    queryFn: ({ signal }) => api.dossiers(signal),
    // Research changes on a human timescale, not a market one.
    refetchInterval: 30_000,
  });

  const stream = usePaperStream(true);
  const age = useStreamAge(stream.lastFrameAt);

  // The stream is the freshest source and the queries are the fallback: while the stream is open its
  // frame is authoritative, so a slow poll cannot overwrite a newer value with an older one.
  const account = stream.frame?.account ?? overview.data?.account;
  const stats = stream.frame?.stats ?? overview.data?.stats ?? status.data?.paper.stats;

  const gate = status.data?.phase_gate;
  const authority = status.data?.live_authority;
  const halt = status.data?.halt;

  return (
    <div className="space-y-4">
      <SimulatedBanner
        environment={String(account?.environment ?? "PAPER")}
        account={account?.account_id}
        detail={account ? `updated ${formatAge(account.updated_at)}` : undefined}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-heading">Command Centre</h1>
        <StreamStatus
          state={stream.state}
          ageSeconds={age}
          intervalSeconds={stream.intervalSeconds}
          error={stream.error}
        />
      </div>

      {/* ---- equity, P&L, exposure -------------------------------------- */}
      <Panel
        title="Global equity"
        subtitle="Simulated capital, marked with the last real prices observed"
        aside={
          account ? (
            <span className="numeric text-data text-muted">
              {account.positions_marked_with_real_data} of {account.open_position_count} positions
              marked with real data
            </span>
          ) : null
        }
      >
        {status.isError || overview.isError ? (
          <p role="alert" className="text-data text-negative">
            ⚠ The API did not answer: {String(status.error?.message ?? overview.error?.message)}. Is
            the backend running, and is <span className="numeric">NEXUS_API_URL</span> pointed at it?
          </p>
        ) : !account ? (
          <p className="text-data text-muted">Waiting for the first frame…</p>
        ) : (
          <div className="grid grid-cols-2 gap-x-6 gap-y-5 md:grid-cols-3 xl:grid-cols-6">
            <Stat
              label="Equity"
              value={formatMoney(account.equity, { symbol: `${account.currency} ` })}
              hint={`from ${formatMoney(account.starting_cash, { symbol: `${account.currency} ` })} simulated`}
            />
            <Stat
              label="Net P&L"
              value={<PnlValue value={account.net_pnl} />}
              tone="neutral"
              hint={`${formatPercent(account.return_pct)} on starting capital`}
              mono={false}
            />
            <Stat
              label="Realized"
              value={<PnlValue value={account.realized_pnl} />}
              mono={false}
              hint="booked on fills only, never on marks"
            />
            <Stat
              label="Unrealized"
              value={<PnlValue value={account.unrealized_pnl} />}
              mono={false}
              hint={
                account.positions_carried_at_entry.length
                  ? `⚠ ${account.positions_carried_at_entry.length} carried at entry price`
                  : "every open position has a real mark"
              }
            />
            <Stat
              label="Simulated cash"
              value={formatMoney(account.simulated_cash, { symbol: `${account.currency} ` })}
              hint={`${account.fills_applied} fills applied`}
            />
            <Stat
              label="Costs paid"
              value={formatMoney(account.commission_paid, { symbol: `${account.currency} ` })}
              tone="warning"
              hint="commission, on top of spread and slippage"
            />
          </div>
        )}
      </Panel>

      {/* ---- live risk, system health, market regime --------------------- */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Live risk" subtitle="What the system is forbidden from doing, and by what">
          <dl className="space-y-2.5 text-data">
            <Row label="Phase gate">
              {gate ? (
                <span className="numeric">
                  phase {gate.phase} · live {String(gate.live_trading)} · adapters{" "}
                  {String(gate.venue_adapters)} · order capability {String(gate.order_capability)}
                </span>
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Live authority">
              {authority ? (
                <StatusDot
                  active={authority.status === "GRANTED"}
                  label={authority.status}
                  tone={authority.status === "GRANTED" ? "negative" : "positive"}
                />
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Blocking reasons">
              {authority?.blocking_reasons?.length ? (
                <ReasonList reasons={authority.blocking_reasons} limit={4} />
              ) : (
                <span className="text-muted">—</span>
              )}
            </Row>
            <Row label="Halt / kill switch">
              {halt ? (
                <StatusDot
                  active={halt.active}
                  label={halt.active ? `ENGAGED ${halt.scope}` : `clear (${halt.scope})`}
                  tone={halt.active ? "negative" : "positive"}
                />
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Real money possible">
              <span className="numeric text-positive">
                {gate ? String(gate.real_money_orders_possible) : "—"}
              </span>
            </Row>
          </dl>
        </Panel>

        <Panel title="System health" subtitle="The process serving this page">
          <dl className="space-y-2.5 text-data">
            <Row label="App">
              {status.data ? (
                <span className="numeric">
                  {status.data.app.name} {status.data.app.version}
                </span>
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Environment">
              {status.data ? <EnvironmentBadge environment={status.data.environment} /> : <Unknown />}
            </Row>
            <Row label="Persistence">
              {status.data?.persistence ? (
                <span className="numeric">
                  {status.data.persistence.engine}
                  {status.data.persistence.ephemeral ? (
                    <span className="text-warning"> ⚠ EPHEMERAL — lost on restart</span>
                  ) : null}
                </span>
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Paper engine">
              {overview.data ? (
                <span className="numeric">
                  {overview.data.engine.engine} · {overview.data.engine.adapter_count} adapters ·
                  ledger {overview.data.engine.ledger.backend}
                  {overview.data.engine.ledger.durable === false ? (
                    <span className="text-warning"> ⚠ not durable</span>
                  ) : null}
                </span>
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Can place live orders">
              <span className="numeric text-positive">
                {overview.data ? String(overview.data.can_place_live_orders) : "—"}
              </span>
            </Row>
            <Row label="Server time">
              <span className="numeric text-muted">
                {status.data ? formatAge(status.data.time_utc) : "—"}
              </span>
            </Row>
          </dl>
        </Panel>

        <Panel title="Market regime & research" subtitle="What is modelled, and what is not yet">
          <dl className="space-y-2.5 text-data">
            <Row label="Market regime">
              <span className="text-warning" title="No regime model exists in the backend">
                ⚠ UNAVAILABLE
              </span>
            </Row>
            <Row label="Why">
              <span className="text-muted">
                no regime model is implemented; a guessed label here would be believed
              </span>
            </Row>
            <Row label="Active research">
              {dossiers.data ? (
                <span className="numeric">
                  {dossiers.data.count ?? dossiers.data.dossiers?.length ?? 0} dossiers
                  {dossiers.data.empty ? (
                    <span className="text-muted" title={String(dossiers.data.empty)}>
                      {" "}
                      · none yet
                    </span>
                  ) : null}
                </span>
              ) : dossiers.isError ? (
                <span className="text-warning">⚠ unavailable</span>
              ) : (
                <Unknown />
              )}
            </Row>
            <Row label="Instruments tracked">
              <span className="numeric">{stats?.instruments_tracked ?? "—"}</span>
            </Row>
            <Row label="Quotes observed">
              <span className="numeric">{stats?.quotes_observed ?? "—"}</span>
            </Row>
            <Row label="Cost constraint">
              <span className="text-muted">{status.data?.cost_constraint ?? "D-019 zero-cost"}</span>
            </Row>
          </dl>
        </Panel>
      </div>

      {/* ---- open positions and the decision queue ----------------------- */}
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel
          title="Open positions"
          subtitle="Simulated holdings, marked with real prices where one exists"
          aside={
            <span className="numeric text-data text-muted">
              {positions.data?.count ?? account?.open_position_count ?? 0} open
            </span>
          }
        >
          <DataTable<PaperPosition>
            rows={account?.positions.filter((position) => position.quantity !== "0")}
            columns={positionColumns}
            rowKey={(row) => `${row.instrument_id}@${row.venue}`}
            loading={positions.isLoading}
            error={positions.error ? String(positions.error.message) : null}
            empty="No open positions. The loop has not acted, or every position has been closed."
            caption="Open simulated positions"
          />
        </Panel>

        <Panel
          title="Decision queue"
          subtitle="The most recent real-time verdicts, with the evidence behind each"
          aside={
            <span className="numeric text-data text-muted">
              {stats ? `${stats.actionable_verdicts} actionable of ${stats.analyses_run}` : ""}
            </span>
          }
        >
          <DataTable<AnalysisVerdict>
            rows={decisions.data?.analyses ?? stream.frame?.latest_analysis}
            columns={decisionColumns}
            rowKey={(row) => row.analysis_id}
            loading={decisions.isLoading}
            error={decisions.error ? String(decisions.error.message) : null}
            empty="No analysis yet. The loop analyses a quote when one arrives."
            caption="Recent real-time analysis verdicts"
          />
        </Panel>
      </div>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="label shrink-0">{label}</dt>
      <dd className="min-w-0 text-right">{children}</dd>
    </div>
  );
}

function Unknown() {
  return (
    <span className="text-muted" title="The API has not answered yet">
      …
    </span>
  );
}

const positionColumns: Column<PaperPosition>[] = [
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument_id}</span> },
  { key: "venue", header: "Venue", render: (row) => row.venue },
  {
    key: "side",
    header: "Side",
    render: (row) => (
      <span className={row.side === "LONG" ? "text-positive" : "text-negative"}>
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
        <span className="text-warning" title="No real price observed; valued at entry">
          ⚠ entry
        </span>
      ) : (
        formatPrice(row.mark)
      ),
  },
  { key: "unrealized", header: "Unrealized", numeric: true, render: (row) => <PnlValue value={row.unrealized_pnl} /> },
  { key: "realized", header: "Realized", numeric: true, render: (row) => <PnlValue value={row.realized_pnl} /> },
];

const decisionColumns: Column<AnalysisVerdict>[] = [
  {
    key: "verb",
    header: "Verb",
    render: (row) => (
      <span className={row.actionable ? "text-info" : "text-secondary"}>
        {row.verb === "ACCEPT" ? "▲" : row.verb === "EXIT" ? "▼" : "◇"} {row.verb}
      </span>
    ),
  },
  { key: "instrument", header: "Instrument", render: (row) => <span className="numeric">{row.instrument_id}</span> },
  {
    key: "confidence",
    header: "Confidence",
    numeric: true,
    render: (row) => (
      <span title={`Band ${row.confidence_band[0]}–${row.confidence_band[1]}`}>
        {row.confidence}
        {row.in_confidence_band ? <span className="text-warning"> ⚠ in band</span> : null}
      </span>
    ),
  },
  {
    key: "momentum",
    header: "Momentum",
    numeric: true,
    render: (row) => (row.evidence.momentum_bps ? `${row.evidence.momentum_bps} bps` : "—"),
  },
  {
    key: "state",
    header: "Outcome",
    render: (row) =>
      row.blocked ? (
        <span className="text-warning">⚠ held</span>
      ) : row.actionable ? (
        <span className="text-info">traded</span>
      ) : (
        <span className="text-muted">no action</span>
      ),
  },
  { key: "when", header: "Analysed", numeric: true, render: (row) => formatAge(row.analysed_at) },
];
