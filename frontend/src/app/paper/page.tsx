"use client";

/**
 * Page 7 (partial) — the Strategy Laboratory's paper trading bench.
 *
 * This is the control room for the machine the platform exists to run: it starts and stops the
 * real-time loop, shows the analysis it is producing as it produces it, and states the assumptions
 * every simulated number depends on. The assumptions are on this page rather than in a tooltip
 * because a paper result read without its cost model is not a result — it is a suggestion.
 *
 * Live updates arrive over SSE (`usePaperStream`). The queries underneath are the fallback for when
 * the stream is closed, and both are shown: a page that silently froze would be indistinguishable
 * from a market that stopped moving.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  ActionButton,
  DataTable,
  Panel,
  PnlValue,
  Provenance,
  ReasonList,
  SimulatedBanner,
  Stat,
  StatusDot,
  StreamStatus,
  type Column,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatBps, formatMoney, formatPrice, formatTimestamp } from "@/lib/format";
import { usePaperStream, useStreamAge } from "@/lib/usePaperStream";
import type { AnalysisVerdict, LoopStats } from "@/lib/types";

export default function PaperTradingPage() {
  const queryClient = useQueryClient();
  const overview = useQuery({ queryKey: ["paper"], queryFn: ({ signal }) => api.paper(signal) });
  const analysis = useQuery({
    queryKey: ["paper", "analysis"],
    queryFn: ({ signal }) => api.analysis(40, signal),
  });

  const stream = usePaperStream(true);
  const age = useStreamAge(stream.lastFrameAt);

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["paper"] });
    void queryClient.invalidateQueries({ queryKey: ["status"] });
  };
  const start = useMutation({ mutationFn: api.start, onSuccess: invalidate });
  const stop = useMutation({ mutationFn: api.stop, onSuccess: invalidate });
  const reset = useMutation({ mutationFn: api.reset, onSuccess: invalidate });

  const data = overview.data;
  const stats: LoopStats | undefined = stream.frame?.stats ?? data?.stats;
  const account = stream.frame?.account ?? data?.account;
  const model = data?.engine.fill_model;
  const running = stats?.running ?? false;
  const startResult = start.data;

  return (
    <div className="space-y-4">
      <SimulatedBanner
        account={account?.account_id}
        detail={data ? `stream interval ${data.stream_interval_seconds}s` : undefined}
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-heading">Paper Trading</h1>
          <p className="label mt-0.5">
            Real-time analysis and simulated execution · docs/03 §2 page 7
          </p>
        </div>
        <StreamStatus
          state={stream.state}
          ageSeconds={age}
          intervalSeconds={stream.intervalSeconds}
          error={stream.error}
        />
      </div>

      {/* ---- controls ---------------------------------------------------- */}
      <Panel
        title="The machine"
        subtitle="Starting it consumes quotes and simulates trades. It cannot send an order."
        aside={
          <StatusDot
            active={running}
            label={running ? "LOOP RUNNING" : "LOOP STOPPED"}
            tone={running ? "positive" : "muted"}
          />
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <ActionButton
            onClick={() => start.mutate()}
            tone="primary"
            disabled={running || start.isPending || data?.enabled === false}
            title="Begin analysing incoming quotes and simulating the trades they justify"
          >
            ▶ Start real-time loop
          </ActionButton>
          <ActionButton
            onClick={() => stop.mutate()}
            disabled={!running || stop.isPending}
            title="Stop analysing. Quotes already queued are dropped and the count is reported."
          >
            ◼ Stop loop
          </ActionButton>
          <ActionButton
            onClick={() => reset.mutate()}
            tone="danger"
            disabled={reset.isPending}
            confirm={
              "Reset the paper account to its starting capital?\n\n" +
              `This discards ${account?.fills_applied ?? 0} simulated fills and every position built ` +
              "from them, in this process. The audit log keeps its record; the account does not.\n\n" +
              "A restarted equity curve is not a recovered one."
            }
            title="Return simulated capital to its starting balance"
          >
            ⟲ Reset account
          </ActionButton>

          {data?.enabled === false ? (
            <span className="text-data text-warning" role="note">
              ⚠ Disabled by configuration: <span className="numeric">NEXUS_PAPER_ENABLED=false</span>
            </span>
          ) : null}
          {startResult && startResult.started === false && startResult.reason ? (
            <span className="text-data text-warning">⚠ {startResult.reason}</span>
          ) : null}
          {stop.data ? (
            <span className="text-data text-muted">
              stopped · {stop.data.stats.quotes_observed} quotes observed before it did
            </span>
          ) : null}
        </div>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-4 xl:grid-cols-8">
          <Stat label="Quotes observed" value={stats?.quotes_observed ?? "—"} />
          <Stat label="Analyses run" value={stats?.analyses_run ?? "—"} />
          <Stat label="Throttled" value={stats?.analyses_throttled ?? "—"} hint="held by the interval" />
          <Stat label="Actionable" value={stats?.actionable_verdicts ?? "—"} tone="info" />
          <Stat label="Simulated" value={stats?.trades_simulated ?? "—"} tone="positive" />
          <Stat label="Unfilled" value={stats?.trades_unfilled ?? "—"} tone="warning" />
          <Stat label="Refused" value={stats?.trades_refused ?? "—"} tone="negative" />
          <Stat
            label="Held back"
            value={
              stats
                ? stats.blocked_by_cooldown +
                  stats.blocked_by_position_limit +
                  stats.blocked_by_sizing
                : "—"
            }
            hint={
              stats
                ? `${stats.blocked_by_cooldown} cooldown · ${stats.blocked_by_position_limit} position limit · ${stats.blocked_by_sizing} sizing`
                : undefined
            }
          />
        </div>

        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-1 border-t border-line pt-3 text-data text-muted">
          <span>
            analysis latency:{" "}
            <span className="numeric text-secondary">
              {stats ? `${stats.last_analysis_elapsed_ms} ms` : "—"}
            </span>{" "}
            (slowest <span className="numeric">{stats?.slowest_analysis_ms ?? "—"} ms</span>)
          </span>
          <span>
            queue depth: <span className="numeric text-secondary">{stats?.queue_depth ?? "—"}</span>
          </span>
          <span>
            started:{" "}
            <span className="numeric text-secondary">
              {stats?.started_at ? formatTimestamp(stats.started_at) : "never"}
            </span>
          </span>
        </div>
      </Panel>

      {/* ---- the assumptions --------------------------------------------- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          title="Execution cost model"
          subtitle="What every simulated fill pays. Read this before reading any P&L."
        >
          {model ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-data">
              <Assumption label="Slippage" value={formatBps(model.slippage_bps)} note="always adverse" />
              <Assumption label="Commission" value={formatBps(model.commission_bps)} />
              <Assumption
                label="Minimum commission"
                value={formatMoney(model.minimum_commission, { digits: 2, symbol: "$" })}
                note="small fills are not free"
              />
              <Assumption label="Latency" value={`${model.latency_ms} ms`} note="decision to venue" />
              <Assumption
                label="Max quote age"
                value={`${model.max_quote_age_seconds} s`}
                note="older is refused, not traded"
              />
              <Assumption
                label="Displayed size"
                value={model.respect_displayed_size ? "respected" : "ignored"}
                note={
                  model.respect_displayed_size
                    ? "orders larger than the book fill partially"
                    : "⚠ assumes infinite depth"
                }
              />
              <Assumption
                label="Delayed feeds"
                value={model.refuse_delayed_data ? "refused" : "traded"}
                note={
                  model.refuse_delayed_data
                    ? "the edge on a delayed quote is not ours"
                    : "⚠ delayed data is being traded"
                }
              />
              <Assumption label="Random seed" value={String(model.seed)} note="a replay is a replay" />
            </dl>
          ) : (
            <p className="text-data text-muted">Waiting for the API…</p>
          )}
        </Panel>

        <Panel
          title="Analysis"
          subtitle="The reference analyzer and the confidence band it is judged against (D-057)"
        >
          {data ? (
            <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-data">
              {Object.entries(data.analyzer).map(([key, value]) => (
                <Assumption
                  key={key}
                  label={key.replace(/_/g, " ")}
                  value={Array.isArray(value) ? value.join(" – ") : String(value)}
                />
              ))}
              <Assumption
                label="reference implementation"
                value="yes"
                note="swap it for a Strategy Laboratory model"
              />
            </dl>
          ) : (
            <p className="text-data text-muted">Waiting for the API…</p>
          )}
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            A verdict inside the band is recorded and <em>not</em> acted on. That is the point of a
            band: a single threshold would trade every marginal observation, and the marginal
            observations are where a strategy loses its money.
          </p>
        </Panel>
      </div>

      {/* ---- the live decision feed --------------------------------------- */}
      <Panel
        title="Real-time analysis"
        subtitle="Every verdict, with the evidence that produced it and what the loop did about it"
        aside={
          <span className="numeric text-data text-muted">
            {analysis.data?.confidence_band
              ? `band ${analysis.data.confidence_band[0]} – ${analysis.data.confidence_band[1]}`
              : ""}
          </span>
        }
      >
        <DataTable<AnalysisVerdict>
          rows={analysis.data?.analyses}
          columns={verdictColumns}
          rowKey={(row) => row.analysis_id}
          loading={analysis.isLoading}
          error={analysis.error ? String(analysis.error.message) : null}
          empty={
            running
              ? "The loop is running but nothing has been analysed yet. It needs real quotes — connect a data source."
              : "The loop is stopped. Start it, and it will analyse quotes as they arrive."
          }
          caption="Real-time analysis verdicts"
        />
      </Panel>

      {account ? (
        <Panel title="Simulated account" subtitle="The same figures as the Command Centre, from the stream">
          <div className="grid grid-cols-2 gap-x-6 gap-y-4 md:grid-cols-3 xl:grid-cols-5">
            <Stat
              label="Equity"
              value={formatMoney(account.equity, { symbol: `${account.currency} ` })}
              hint={`cash ${formatMoney(account.simulated_cash)}`}
            />
            <Stat label="Net P&L" value={<PnlValue value={account.net_pnl} />} mono={false} />
            <Stat label="Realized" value={<PnlValue value={account.realized_pnl} />} mono={false} />
            <Stat label="Unrealized" value={<PnlValue value={account.unrealized_pnl} />} mono={false} />
            <Stat label="Fills applied" value={account.fills_applied} />
          </div>
        </Panel>
      ) : null}
    </div>
  );
}

function Assumption({ label, value, note }: { label: string; value: string; note?: string }) {
  const warning = note?.startsWith("⚠") || value === "ignored" || value === "traded";
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className={`numeric mt-0.5 ${warning ? "text-warning" : "text-primary"}`}>
        {warning && !value.startsWith("⚠") ? "⚠ " : ""}
        {value}
      </dd>
      {note ? <dd className="mt-0.5 text-data text-muted">{note}</dd> : null}
    </div>
  );
}

const verdictColumns: Column<AnalysisVerdict>[] = [
  {
    key: "when",
    header: "Analysed (UTC)",
    numeric: true,
    render: (row) => <span className="text-muted">{formatTimestamp(row.analysed_at)}</span>,
  },
  {
    key: "instrument",
    header: "Instrument",
    render: (row) => (
      <Provenance
        instrument={row.instrument_id}
        venue={row.venue}
        source={row.evidence.source}
        observedAt={null}
      />
    ),
  },
  {
    key: "verb",
    header: "Verb",
    render: (row) => (
      <span className={row.actionable ? "text-info" : "text-secondary"}>
        {row.verb === "ACCEPT" ? "▲" : row.verb === "EXIT" ? "▼" : "◇"} {row.verb}
      </span>
    ),
  },
  {
    key: "confidence",
    header: "Confidence",
    numeric: true,
    render: (row) => (
      <span>
        {row.confidence}
        {row.in_confidence_band ? (
          <span className="text-warning" title="Inside the band: recorded, not acted on">
            {" "}
            ⚠ band
          </span>
        ) : null}
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
    key: "mid",
    header: "Mid",
    numeric: true,
    render: (row) => (row.evidence.mid ? formatPrice(row.evidence.mid) : "—"),
  },
  {
    key: "spread",
    header: "Spread",
    numeric: true,
    render: (row) => (row.evidence.spread_bps ? `${row.evidence.spread_bps} bps` : "—"),
  },
  {
    key: "obs",
    header: "Obs",
    numeric: true,
    render: (row) => row.observations_used,
  },
  {
    key: "outcome",
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
  {
    key: "reasons",
    header: "Why",
    render: (row) => <ReasonList reasons={row.blocked ? [row.blocked, ...row.reasons] : row.reasons} limit={2} />,
  },
  {
    key: "elapsed",
    header: "Took",
    numeric: true,
    render: (row) => <span className="text-muted">{row.elapsed_ms} ms</span>,
  },
];
