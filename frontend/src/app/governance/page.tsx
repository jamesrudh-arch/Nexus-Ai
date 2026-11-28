"use client";

/**
 * Page 15 — Settings & Governance (docs/03 §2).
 *
 * This is the page that answers "can this thing trade my money?" and it answers with evidence rather
 * than assurance. Every gate is read from the running process, not from a constant in this file, so
 * the page cannot drift into claiming a safety property the backend stopped having.
 *
 * It also draws the line the whole product depends on: **paper authority is not live authority.** The
 * two are rendered side by side because they look similar and mean opposite things, and a dashboard
 * that showed one without the other would invite exactly that confusion.
 */

import { useQuery } from "@tanstack/react-query";

import { EnvironmentBadge, Panel, ReasonList, SimulatedBanner, StatusDot } from "@/components/ui";
import { api } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";

const LADDER: { state: string; glyph: string; meaning: string; preLive: boolean }[] = [
  { state: "DISABLED", glyph: "○", meaning: "nothing runs; the default", preLive: true },
  { state: "OBSERVE", glyph: "○", meaning: "market data only, no decisions", preLive: true },
  { state: "RESEARCH", glyph: "◇", meaning: "decisions computed, not acted on", preLive: true },
  { state: "SHADOW", glyph: "◐", meaning: "decisions computed and logged, never sent", preLive: true },
  { state: "PAPER", glyph: "▤", meaning: "simulated execution against live data — this build", preLive: true },
  { state: "PILOT", glyph: "◑", meaning: "restricted live trading under hard caps", preLive: false },
  { state: "LIVE", glyph: "●", meaning: "unrestricted live trading", preLive: false },
];

export default function Governance() {
  const status = useQuery({ queryKey: ["status"], queryFn: ({ signal }) => api.status(signal) });
  const overview = useQuery({ queryKey: ["paper"], queryFn: ({ signal }) => api.paper(signal) });
  const audit = useQuery({ queryKey: ["audit"], queryFn: ({ signal }) => api.auditVerify(signal) });

  const gate = status.data?.phase_gate;
  const authority = status.data?.live_authority;
  const paper = status.data?.paper;
  const current = String(status.data?.environment ?? "DISABLED");

  return (
    <div className="space-y-4">
      <SimulatedBanner detail="governance state read from the running process" />

      <h1 className="text-heading">Settings &amp; Governance</h1>

      <Panel
        title="Can this system trade real money?"
        subtitle="Read from the running process, not from a constant in this file"
      >
        <div className="grid gap-x-8 gap-y-3 md:grid-cols-2 xl:grid-cols-4">
          <Gate
            label="Phase gate · live trading"
            value={gate?.live_trading}
            goodWhenFalse
            detail={gate ? `phase ${gate.phase}: ${gate.name}` : undefined}
          />
          <Gate label="Venue adapters present" value={gate?.venue_adapters} goodWhenFalse />
          <Gate label="Real-money orders possible" value={gate?.real_money_orders_possible} goodWhenFalse />
          <Gate label="Order capability" value={gate?.order_capability} goodWhenFalse />
          <Gate
            label="Live authority"
            value={authority?.status === "GRANTED"}
            goodWhenFalse
            detail={authority?.status}
          />
          <Gate label="Paper can place live orders" value={overview.data?.can_place_live_orders} goodWhenFalse />
          <Gate label="Paper is a venue adapter" value={overview.data?.is_venue_adapter} goodWhenFalse />
          <Gate label="Paper needs a credential" value={overview.data?.credentials_required} goodWhenFalse />
        </div>

        {authority?.blocking_reasons?.length ? (
          <div className="mt-4 border-t border-line pt-3">
            <p className="label mb-2">Why live authority is denied</p>
            <ReasonList reasons={authority.blocking_reasons} />
          </div>
        ) : null}

        <p className="mt-4 border-t border-line pt-3 text-data text-muted">
          Every gate above must be true simultaneously, at the moment of a request, for a real order
          to be possible — and there is no override flag, no debug bypass, and no configuration value
          that grants it alone. This page shows the gates as the process reports them, so if one ever
          changed, it would change here first.
        </p>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Paper authority vs live authority" subtitle="They look similar and mean opposite things">
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded border border-warning/40 p-3">
              <p className="label mb-2">Paper</p>
              <p className="text-body text-warning">
                {paper?.enabled ? "ENABLED" : "DISABLED"}
              </p>
              <ul className="mt-2 space-y-1 text-data text-secondary">
                <li>executes against real quotes</li>
                <li>moves simulated capital only</li>
                <li>holds {overview.data?.adapter_count ?? 0} venue adapters</li>
                <li>can place live orders: {String(paper?.can_place_live_orders ?? false)}</li>
                <li>requires no credential</li>
              </ul>
            </div>
            <div className="rounded border border-line p-3">
              <p className="label mb-2">Live</p>
              <p className="text-body text-secondary">{authority?.status ?? "UNKNOWN"}</p>
              <ul className="mt-2 space-y-1 text-data text-secondary">
                <li>requires environment ≥ PILOT</li>
                <li>requires Nigerian legal review (O-004)</li>
                <li>requires separate owner authority</li>
                <li>requires phases 0–9 accepted with evidence</li>
                <li>requires a per-account LIVE_VERIFIED venue</li>
              </ul>
            </div>
          </div>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            Nothing on the left contributes to the right. Running the paper platform for a year
            grants no live authority whatsoever, and the phase gate CI asserts on every push is
            unchanged by the paper package existing.
          </p>
        </Panel>

        <Panel title="Environment ladder" subtitle="Where this build sits, and what it cannot skip to">
          <ol className="space-y-1.5">
            {LADDER.map((rung) => {
              const isCurrent = rung.state === current;
              return (
                <li
                  key={rung.state}
                  className={`flex items-baseline gap-3 rounded px-2 py-1 text-data ${
                    isCurrent ? "bg-elevated text-primary" : "text-secondary"
                  }`}
                >
                  <span aria-hidden="true" className={isCurrent ? "text-warning" : "text-muted"}>
                    {rung.glyph}
                  </span>
                  <span className={`numeric w-20 shrink-0 ${isCurrent ? "text-primary" : ""}`}>
                    {rung.state}
                  </span>
                  <span className="min-w-0 flex-1">{rung.meaning}</span>
                  {isCurrent ? <EnvironmentBadge environment={rung.state} /> : null}
                  {!rung.preLive ? (
                    <span className="label shrink-0 text-muted" title="Beyond this build's phase gate">
                      unreachable
                    </span>
                  ) : null}
                </li>
              );
            })}
          </ol>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            The ladder cannot be jumped: reaching LIVE requires passing through PILOT, and PAPER is
            the highest rung this build can occupy. That is enforced in
            <span className="numeric"> core/environment.py</span>, not by convention.
          </p>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Data sources" subtitle="Free, public, unauthenticated (D-019, D-026)">
          <dl className="space-y-2.5 text-data">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Market data enabled</dt>
              <dd className="numeric text-positive">
                {gate ? String(gate.market_data_sources) : "—"}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Authenticated sources</dt>
              <dd className="numeric text-positive">false</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Cost constraint</dt>
              <dd className="text-right text-muted">{status.data?.cost_constraint ?? "—"}</dd>
            </div>
          </dl>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            No source in this build can place an order and none is given a credential. The paper
            analyzer consumes whatever these sources observe; it has no feed of its own.
          </p>
        </Panel>

        <Panel title="Record & retention" subtitle="What persists, and where">
          <dl className="space-y-2.5 text-data">
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Persistence engine</dt>
              <dd className="numeric">{status.data?.persistence?.engine ?? "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Ephemeral</dt>
              <dd className="numeric">
                {status.data?.persistence?.ephemeral ? (
                  <span className="text-warning">⚠ yes — lost on restart</span>
                ) : (
                  String(status.data?.persistence?.ephemeral ?? "—")
                )}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Paper ledger</dt>
              <dd className="numeric">
                {overview.data?.engine.ledger.backend ?? "—"}
                {overview.data?.engine.ledger.durable === false ? (
                  <span className="text-warning"> ⚠ not durable</span>
                ) : null}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Audit chain</dt>
              <dd className="numeric">
                {audit.data ? (
                  audit.data.intact ? (
                    <span className="text-positive">● intact</span>
                  ) : (
                    <span className="text-negative">✕ broken</span>
                  )
                ) : (
                  "—"
                )}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Audit records</dt>
              <dd className="numeric">{audit.data?.records ?? "—"}</dd>
            </div>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="label">Server time</dt>
              <dd className="numeric text-muted">
                {status.data ? formatTimestamp(status.data.time_utc) : "—"}
              </dd>
            </div>
          </dl>
          <p className="mt-3 border-t border-line pt-3 text-data text-muted">
            Simulated trades are written to the same audit chain as everything else, so a paper
            result cannot be quietly edited out of history. The paper ledger itself is in-process by
            default and says so: a restart loses the blotter, not the audit record of it.
          </p>
        </Panel>
      </div>

      <Panel title="Halt state" subtitle="The one control that always works, whatever the gates say">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-data">
          <StatusDot
            active={status.data?.halt.active ?? false}
            label={
              status.data?.halt.active
                ? `ENGAGED ${status.data.halt.scope}`
                : `clear (${status.data?.halt.scope ?? "NONE"})`
            }
            tone={status.data?.halt.active ? "negative" : "positive"}
          />
          {status.data?.halt.reason ? (
            <span className="text-muted">reason: {status.data.halt.reason}</span>
          ) : null}
          <span className="text-muted">
            Engaging it requires owner authority via <span className="numeric">POST /v1/halt</span>;
            it stops the paper loop opening positions and still permits closing them.
          </span>
        </div>
      </Panel>
    </div>
  );
}

function Gate({
  label,
  value,
  goodWhenFalse,
  detail,
}: {
  label: string;
  value: boolean | string | undefined;
  goodWhenFalse: boolean;
  detail?: string;
}) {
  if (value === undefined) {
    return (
      <div>
        <p className="label">{label}</p>
        <p className="mt-1 text-data text-muted">…</p>
      </div>
    );
  }
  const flag = typeof value === "boolean" ? value : value === "GRANTED";
  const good = goodWhenFalse ? !flag : flag;
  return (
    <div>
      <p className="label">{label}</p>
      <p className={`mt-1 text-body ${good ? "text-positive" : "text-negative"}`}>
        {good ? "✓" : "✕"} {typeof value === "string" ? value : String(value)}
      </p>
      {detail ? <p className="mt-0.5 text-data text-muted">{detail}</p> : null}
    </div>
  );
}
