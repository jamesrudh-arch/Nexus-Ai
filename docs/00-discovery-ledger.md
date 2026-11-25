# NEXUS Discovery Ledger — Living Record

**Spec:** NEXUS Living Master Specification v1.0 / 25 Nov 2026  
**Owner:** Personal (Nigeria)  
**Baseline approved:** 2026-11-25  
**Status language:** Appendix C (PROPOSED / CONFIRMED / DEFERRED / UNRESOLVED)

> Per Section 0.1, this ledger is the visible record of every discovery decision.  
> Never convert assumptions into requirements silently. OPEN = unknown. PROVISIONAL = temporary assumption with stated risk.

| # | Question | Owner's Answer | Date | Status | Impact / Dependent Requirements | Follow-up |
|---|----------|----------------|------|--------|--------------------------------|-----------|
| D-001 | Intended use & user model | Personal accounts only | 2026-11-25 | CONFIRMED | Single-owner identity, no SaaS tenancy. Sections 25, 18 | None |
| D-002 | Priority markets / asset classes | Multi-asset (broad) | 2026-11-25 | CONFIRMED | Full instrument registry (Sec 3), staged activation. Sec 3, 11 | Certify adapters in stages |
| D-003 | Jurisdiction / residency | Nigeria | 2026-11-25 | CONFIRMED | Broker eligibility, regulation, data rights, tax/reporting. Sec 19, 33 | Nigeria legal review before live |
| D-004 | Autonomy & approval model | Fully autonomous live (within hard limits) | 2026-11-25 | CONFIRMED | Live authority; staged rollout Observe→Research→Shadow/Paper→Pilot→Autonomous. Sec 2, 9, 12, 13 | Separate live-authority approval required |
| D-005 | Initial capital & currency | Over $100,000 USD equiv. | 2026-11-25 | CONFIRMED | Sizing, minimum order, reporting. Sec 10 | Currency per account (USD/USDT/NGN) — OPEN |
| D-006 | Risk limits & leverage | Conservative: 1% per trade, ≤2x leverage, 2% daily halt | 2026-11-25 | CONFIRMED | Hard limits override AI. Sec 10.1, 13 | Exact numbers to finalize in Risk Policy |
| D-007 | Priority venues | All venues: Bybit, Binance, OKX, MT4, MT5, cTrader, IBKR, OANDA, Alpaca+ | 2026-11-25 | CONFIRMED | Adapter framework + independent certification per venue. Sec 11 | Nigeria eligibility per venue (see Feasibility Report) |
| D-008 | Trading horizons & styles | Intraday / day trading | 2026-11-25 | CONFIRMED | Real-time data, execution quality, latency. Sec 4, 7, 11.4 | No unvalidated HFT claims |
| D-009 | Research / data budget | Free / official sources first | 2026-11-25 | CONFIRMED | FRED, SEC EDGAR, EIA, CFTC, exchange feeds. Sec 16 | Licensed upgrade path documented |
| D-010 | Hosting & deployment | Cloud hosting | 2026-11-25 | CONFIRMED | Cloud-native core, Docker. Sec 22.2 | VPS only if MT bridges require it |
| D-011 | Devices & mobile access | All: desktop + iOS + Android | 2026-11-25 | CONFIRMED | Responsive web; halt/approvals explicit. Sec 17.5 | No tiny ambiguous taps for live actions |
| D-012 | Intelligence & learning | Independent research + learning (owner approves changes) | 2026-11-25 | CONFIRMED | Persistent memory; no self-promotion to production. Sec 6.3 | Model-update approval workflow |
| D-013 | Legal review before live | Yes — Nigerian jurisdiction review required | 2026-11-25 | CONFIRMED | Live disabled until reviewed. Sec 19 | Commission review; maintain Supported-Country matrix |
| D-014 | Product name & visual direction | Keep NEXUS + dark terminal | 2026-11-25 | CONFIRMED | Dark premium terminal, Section 17 | NEXUS remains working label |
| D-015 | Preferred stack & delivery | Reference stack (Section 22) | 2026-11-25 | CONFIRMED | Python + TypeScript + MQL bridges, PostgreSQL, Docker, React/Next.js | Owner owns source + handover docs |
| D-016 | Critical alert channels | All: in-app, email, push, SMS, Telegram/WhatsApp | 2026-11-25 | CONFIRMED | Delivery status, retries, escalation. Sec 24 | Provider selection + consent |
| D-017 | Owner Requirements Baseline approval | Approved — proceed to Appendix B feasibility report | 2026-11-25 | CONFIRMED | Gates implementation. Sec 0.3, 0.4 | Feasibility report required before production code |
| D-018 | Appendix B Feasibility Report approval | Approved — proceed to Phase 1 (Product/UX Bible) | 2026-11-25 | CONFIRMED | Unlocks Phase 1. Sec 26 | Nigeria eligibility findings accepted as current-as-of-date; re-verify before live |
| D-019 | **Cost constraint — free tools / free APIs / free data only** | "I told you free tools APIs and all but you keep mentioning using money" → **ZERO-COST: no paid services, $0/month** | 2026-11-25 | CONFIRMED | Hard constraint on every component: hosting, data, models, notifications, software licences. Feasibility Report v1.1 §4/§10/§11/§13 rewritten; paid vendors moved to REJECTED | Any component with no $0 option = BLOCKED + escalated as separate owner decision; never silently adopt paid. Scope narrows instead of spending |

## OPEN / PROVISIONAL Items (not yet decided)

| ID | Item | Status | Why it matters | Default stance |
|----|------|--------|----------------|----------------|
| O-001 | Per-account currency (USD / USDT / NGN) | OPEN | Sizing, FX conversion, reporting | No live capital assumptions |
| O-002 | Exact risk numbers (per-trade, daily, drawdown, exposure) | PROVISIONAL (conservative profile) | Hard-limit enforcement | Conservative profile until Risk Policy finalized |
| O-003 | Broker eligibility for Nigerian residents (per venue) | OPEN | Determines which adapters can go live | Build framework; certify per account |
| O-004 | Nigerian legal review outcome | OPEN | Live authority gate | Live disabled until reviewed |
| O-005 | Free-data coverage/latency sufficiency | PROVISIONAL | Intraday needs real-time feeds | Free only (D-019). If insufficient → narrow scope, never purchase |
| O-006 | SMS + WhatsApp alert channels | **BLOCKED by D-019** | Not deliverable at $0 (no reliable free SMS gateway for Nigeria; WhatsApp Cloud API charges per business-initiated message) | Free set in use: in-app + Telegram (primary) + Web Push + Brevo email. Owner decision Q-05 |
| O-007 | Single free VM as primary host (Oracle Always Free, 2 OCPU/12 GB) | OPEN (Q-07) | Idle-reclaim + allowance-change risk; no HA | Accept for Observe→Shadow/Paper with GCP watchdog, encrypted off-box backups, IaC rebuild <1 hr; re-review before live |
| O-008 | 200 GB storage cap vs tick-history depth | OPEN (Q-08) | Limits backtest depth | Tiered retention (raw ticks → 1s → 1m rollups + purge) and honest coverage labels, or narrower instrument universe |

## Change Log

| Date | Change | Rationale | Owner approval |
|------|--------|-----------|----------------|
| 2026-11-25 | Baseline approved | Discovery complete (D-001–D-016) | Yes — D-017 |
| 2026-11-25 | Feasibility Report approved; Phase 1 unlocked | Appendix B gate (Sec 0.4, 26) | Yes — D-018 |
| 2026-11-25 | **Zero-cost constraint added (D-019).** Feasibility Report revised to v1.1: §4 data sources → free-only; §10 rewritten as $0 hosting/tooling/models/notifications plan with disclosed free-tier trade-offs (Z-01–Z-10); §11 paid vendors moved to Rejected; §13 dependencies all $0. Baseline §1.6/§1.7/§1.8, O-005–O-008, risks and §7 updated. README + UX Bible updated. | Owner correction: paid options kept appearing despite "free tools/APIs" instruction | Yes — owner-initiated |
| 2026-11-25 | SMS/WhatsApp alerting marked BLOCKED (O-006) | Cannot be delivered at $0; escalated as Q-05 rather than silently paid for | Pending owner decision |

---

*Traceability: Every requirement links to design → implementation → test → release status (NOT STARTED / IN DISCOVERY / DESIGNED / IN DEVELOPMENT / TESTING / BLOCKED / ACCEPTED / DEFERRED) per Section 0.5.*
