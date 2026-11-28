"""Real-time analysis over the live quote flow (Stage 11, D-059).

The owner's requirement was that the system analyse *in real time, before actual trading*. This
module is that analysis, and it is written to be replaceable: :class:`QuoteFlowAnalyzer` is a
reference implementation whose whole job is to turn real observations into a
:class:`~nexus.domain.decision.DecisionVerb` with an honest confidence attached.

Three properties are deliberate.

**It abstains rather than guesses.** With fewer observations than ``minimum_history`` it returns
``ABSTAIN`` and says why. A verdict manufactured from two quotes is not analysis, and in a paper
engine it would be worse than useless: it would produce a P&L curve that looks like evidence for a
strategy that was never tested.

**Its confidence is a band, not a threshold (D-057).** Below ``confidence_low`` the analyzer
``WAIT``s; above ``confidence_high`` it acts; in between it waits and records that it was in the
band. A single threshold makes every marginal observation tradeable, and the marginal observations
are precisely where a strategy loses its money.

**Every verdict carries its inputs.** The evidence dict records the mid, spread, momentum, size
imbalance and staleness that produced the verdict, so a filled paper order can always be traced
back to the numbers that motivated it. Without that, "the system bought" is an unanswerable
statement.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from nexus.core.ids import iso_utc, new_id, utc_now
from nexus.domain.decision import DecisionVerb

__all__ = [
    "Analyzer",
    "AnalysisConfig",
    "AnalysisVerdict",
    "QuoteFlowAnalyzer",
]

_BPS = Decimal(10_000)


class Analyzer(Protocol):
    """What the real-time loop asks of an analyzer.

    A Protocol so the reference implementation can be swapped for a strategy from the Strategy
    Laboratory (Stage 7) without the loop changing. The loop only requires that a verdict arrives
    with a verb, a confidence and the evidence behind it.
    """

    def observe(self, quote: Any, *, now: datetime | None = None) -> None: ...

    def verdict(self, instrument_id: str, venue: str, *, now: datetime | None = None) -> AnalysisVerdict: ...


@dataclass(frozen=True, slots=True)
class AnalysisConfig:
    """Tuning for the reference analyzer.

    Defaults are conservative: they are chosen so that the analyzer trades rarely and abstains
    often, because a paper platform that trades on everything cannot distinguish a good idea from a
    lucky one.
    """

    #: Observations required before any verdict other than ABSTAIN is possible.
    minimum_history: int = 12
    #: Rolling window the momentum is measured over.
    window: int = 20
    #: Mid movement, in basis points over the window, that counts as a signal at all.
    momentum_threshold_bps: Decimal = Decimal("15")
    #: Order-book size imbalance that counts as corroborating pressure.
    imbalance_threshold: Decimal = Decimal("0.20")
    #: A quote older than this is not analysable, whatever it says.
    max_quote_age_seconds: Decimal = Decimal("30")
    #: D-057's band. Below low → WAIT, above high → act, between → WAIT and record the band.
    confidence_low: Decimal = Decimal("0.35")
    confidence_high: Decimal = Decimal("0.70")
    #: A spread wider than this eats the edge, so the analyzer will not act into it.
    max_spread_bps: Decimal = Decimal("120")

    def validated(self) -> AnalysisConfig:
        problems: list[str] = []
        if self.minimum_history < 2:
            problems.append("minimum_history must be at least 2 (one observation has no momentum)")
        if self.window < self.minimum_history:
            problems.append("window cannot be smaller than minimum_history")
        if not (Decimal("0") <= self.confidence_low <= self.confidence_high <= Decimal("1")):
            problems.append("the confidence band must satisfy 0 <= low <= high <= 1")
        if self.momentum_threshold_bps < 0:
            problems.append("momentum_threshold_bps cannot be negative")
        if self.max_quote_age_seconds <= 0:
            problems.append("max_quote_age_seconds must be positive")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@dataclass(frozen=True, slots=True)
class AnalysisVerdict:
    """One analysis result. Always carries the evidence that produced it."""

    analysis_id: str
    instrument_id: str
    venue: str
    verb: DecisionVerb
    confidence: Decimal
    in_confidence_band: bool
    #: The band the verdict was judged against, carried so `actionable` can be recomputed by a
    #: reader without knowing which config produced it.
    confidence_low: Decimal = Decimal("0.35")
    confidence_high: Decimal = Decimal("0.70")
    reasons: tuple[str, ...] = ()
    evidence: dict[str, Any] = field(default_factory=dict)
    observations_used: int = 0
    analysed_at: str = field(default_factory=lambda: iso_utc(utc_now()))
    #: How long the analyzer took, so the loop can report whether "real time" is actually real time.
    elapsed_ms: float = 0.0
    simulated_environment: str = "PAPER"

    @property
    def actionable(self) -> bool:
        """Whether the loop should turn this into an intent.

        A verdict is actionable only when it proposes a change *and* clears the upper band the
        config actually set. WAIT, ABSTAIN and ESCALATE never trade; ESCALATE goes to a human,
        which is the whole point of it.
        """
        return (
            self.verb in (DecisionVerb.ACCEPT, DecisionVerb.REDUCE, DecisionVerb.EXIT)
            and self.confidence >= self.confidence_high
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "analysis_id": self.analysis_id,
            "instrument_id": self.instrument_id,
            "venue": self.venue,
            "verb": self.verb.value,
            "confidence": str(self.confidence),
            "in_confidence_band": self.in_confidence_band,
            "confidence_band": [str(self.confidence_low), str(self.confidence_high)],
            "actionable": self.actionable,
            "reasons": list(self.reasons),
            "evidence": self.evidence,
            "observations_used": self.observations_used,
            "analysed_at": self.analysed_at,
            "elapsed_ms": self.elapsed_ms,
            "simulated_environment": self.simulated_environment,
        }


class QuoteFlowAnalyzer:
    """Reference analyzer: momentum, spread and size imbalance from observed top-of-book quotes.

    It holds a bounded rolling window per instrument and computes on demand, so observing a quote
    is cheap and the analysis cost lands where the loop can measure it. Thread-safe, because the
    ingestion thread observes while the loop analyses.
    """

    def __init__(self, config: AnalysisConfig | None = None) -> None:
        self._config = (config or AnalysisConfig()).validated()
        self._windows: dict[tuple[str, str], deque[dict[str, Any]]] = {}
        self._lock = threading.RLock()

    @property
    def config(self) -> AnalysisConfig:
        return self._config

    def describe(self) -> dict[str, Any]:
        """The analyzer's assumptions, published so a verdict can be read against them."""
        return {
            "analyzer": "QuoteFlowAnalyzer",
            "reference_implementation": True,
            "minimum_history": self._config.minimum_history,
            "window": self._config.window,
            "momentum_threshold_bps": str(self._config.momentum_threshold_bps),
            "imbalance_threshold": str(self._config.imbalance_threshold),
            "max_quote_age_seconds": str(self._config.max_quote_age_seconds),
            "confidence_band": [str(self._config.confidence_low), str(self._config.confidence_high)],
            "max_spread_bps": str(self._config.max_spread_bps),
        }

    def observe(self, quote: Any, *, now: datetime | None = None) -> None:
        """Record one real observation. Quotes without both sides are dropped, not repaired."""
        bid = getattr(quote, "bid", None)
        ask = getattr(quote, "ask", None)
        if not isinstance(bid, Decimal) or not isinstance(ask, Decimal):
            return
        if bid <= 0 or ask <= 0:
            return
        key = (str(quote.instrument_id), str(quote.venue))
        observed = getattr(quote, "observed_at", None)
        entry = {
            "bid": bid,
            "ask": ask,
            "mid": ((bid + ask) / 2).quantize(Decimal("0.00000001")),
            "spread_bps": (((ask - bid) / ((bid + ask) / 2)) * _BPS).quantize(Decimal("0.0001")),
            "bid_size": getattr(quote, "bid_size", None),
            "ask_size": getattr(quote, "ask_size", None),
            "last": getattr(quote, "last", None),
            "delayed": bool(getattr(quote, "delayed", False)),
            "source": str(getattr(quote, "source", "UNKNOWN")),
            "observed_at": observed if isinstance(observed, datetime) else (now or utc_now()),
        }
        with self._lock:
            window = self._windows.setdefault(key, deque(maxlen=self._config.window))
            window.append(entry)

    def observations(self, instrument_id: str, venue: str) -> int:
        with self._lock:
            return len(self._windows.get((instrument_id, venue), ()))

    def mark(self, instrument_id: str, venue: str) -> Decimal | None:
        """The most recent real last price, for marking positions. ``None`` if none was observed."""
        with self._lock:
            window = self._windows.get((instrument_id, venue))
            if not window:
                return None
            for entry in reversed(window):
                last = entry["last"]
                if isinstance(last, Decimal):
                    return last
            # No last trade in the window: the mid is a real derived price, not an invented one, but
            # the caller can tell which it got from `mark_is_mid`.
            mid = window[-1]["mid"]
            return mid if isinstance(mid, Decimal) else None

    def mark_is_mid(self, instrument_id: str, venue: str) -> bool:
        with self._lock:
            window = self._windows.get((instrument_id, venue))
            if not window:
                return False
            return not isinstance(window[-1]["last"], Decimal)

    def verdict(self, instrument_id: str, venue: str, *, now: datetime | None = None) -> AnalysisVerdict:
        """Analyse the window and return a verb with an honest confidence."""
        started = utc_now()
        moment = now or started
        cfg = self._config
        with self._lock:
            window = list(self._windows.get((instrument_id, venue), ()))

        def build(
            verb: DecisionVerb,
            confidence: Decimal,
            reasons: tuple[str, ...],
            evidence: dict[str, Any],
        ) -> AnalysisVerdict:
            elapsed = (utc_now() - started).total_seconds() * 1000.0
            low, high = cfg.confidence_low, cfg.confidence_high
            return AnalysisVerdict(
                analysis_id=new_id("ANL"),
                instrument_id=instrument_id,
                venue=venue,
                verb=verb,
                confidence=confidence.quantize(Decimal("0.0001")),
                in_confidence_band=low <= confidence < high,
                confidence_low=low,
                confidence_high=high,
                reasons=reasons,
                evidence=evidence,
                observations_used=len(window),
                analysed_at=iso_utc(moment),
                elapsed_ms=round(elapsed, 3),
            )

        if not window:
            return build(
                DecisionVerb.ABSTAIN,
                Decimal("0"),
                ("NO_OBSERVATIONS:nothing has been seen for this instrument on this venue",),
                {},
            )

        latest = window[-1]
        age = self._age(latest["observed_at"], moment)
        if age is not None and age > cfg.max_quote_age_seconds:
            return build(
                DecisionVerb.WAIT,
                Decimal("0"),
                (f"STALE_DATA:the newest observation is {age}s old",),
                {"age_seconds": str(age), "source": latest["source"]},
            )
        if latest["delayed"]:
            return build(
                DecisionVerb.ABSTAIN,
                Decimal("0"),
                ("DELAYED_FEED:this source is delayed, so any edge measured on it is not ours",),
                {"source": latest["source"]},
            )
        if len(window) < cfg.minimum_history:
            return build(
                DecisionVerb.ABSTAIN,
                Decimal("0"),
                (
                    f"INSUFFICIENT_HISTORY:{len(window)} of the {cfg.minimum_history} observations "
                    "required; a verdict now would be a guess with a P&L attached",
                ),
                {"observations": len(window)},
            )

        oldest = window[0]
        mid_now: Decimal = latest["mid"]
        mid_then: Decimal = oldest["mid"]
        momentum_bps = (((mid_now - mid_then) / mid_then) * _BPS).quantize(Decimal("0.0001"))
        spread_bps: Decimal = latest["spread_bps"]
        imbalance = self._imbalance(latest)
        evidence = {
            "mid": str(mid_now),
            "bid": str(latest["bid"]),
            "ask": str(latest["ask"]),
            "spread_bps": str(spread_bps),
            "momentum_bps": str(momentum_bps),
            "window_observations": len(window),
            "window_span_seconds": str(self._age(oldest["observed_at"], moment)),
            "size_imbalance": None if imbalance is None else str(imbalance),
            "source": latest["source"],
            "age_seconds": None if age is None else str(age),
            "mark_is_mid": self.mark_is_mid(instrument_id, venue),
        }

        # A spread wider than the move being traded means the venue takes the edge before the
        # strategy can. This is checked before momentum for that reason: it is the cheaper way to be
        # wrong, and the more common one.
        if spread_bps > cfg.max_spread_bps:
            return build(
                DecisionVerb.WAIT,
                Decimal("0.10"),
                (
                    f"SPREAD_TOO_WIDE:{spread_bps}bps against a {cfg.max_spread_bps}bps limit; the "
                    "cost of crossing exceeds the move being measured",
                ),
                evidence,
            )

        threshold = cfg.momentum_threshold_bps
        if abs(momentum_bps) < threshold:
            return build(
                DecisionVerb.WAIT,
                Decimal("0.20"),
                (
                    f"NO_SIGNAL:mid moved {momentum_bps}bps over {len(window)} observations, inside "
                    f"the {threshold}bps threshold",
                ),
                evidence,
            )

        direction = 1 if momentum_bps > 0 else -1
        # Confidence is the momentum expressed in thresholds, capped, then adjusted by whether the
        # book agrees. It is not a probability and is not claimed to be one: it is a monotone score
        # whose band the owner ruled (D-057), which is what makes WAIT a real state rather than a
        # decoration.
        strength = min(abs(momentum_bps) / threshold, Decimal("3")) / Decimal("3")
        confidence = (Decimal("0.30") + strength * Decimal("0.55")).quantize(Decimal("0.0001"))
        reasons = [
            f"MOMENTUM:{momentum_bps}bps over {len(window)} observations "
            f"({'up' if direction > 0 else 'down'})"
        ]
        if imbalance is not None:
            agrees = (imbalance > 0 and direction > 0) or (imbalance < 0 and direction < 0)
            if abs(imbalance) >= cfg.imbalance_threshold:
                if agrees:
                    confidence += Decimal("0.10")
                    reasons.append(f"BOOK_AGREES:size imbalance {imbalance} favours the same side")
                else:
                    confidence -= Decimal("0.15")
                    reasons.append(
                        f"BOOK_DISAGREES:size imbalance {imbalance} favours the other side; "
                        "the move may already be absorbed"
                    )
        confidence = max(Decimal("0"), min(Decimal("1"), confidence)).quantize(Decimal("0.0001"))

        if cfg.confidence_low <= confidence < cfg.confidence_high:
            return build(
                DecisionVerb.WAIT,
                confidence,
                (
                    *reasons,
                    f"IN_CONFIDENCE_BAND:{confidence} sits between {cfg.confidence_low} and "
                    f"{cfg.confidence_high} (D-057), so it is recorded and not acted on",
                ),
                evidence,
            )
        if confidence < cfg.confidence_low:
            return build(DecisionVerb.WAIT, confidence, (*reasons, "BELOW_CONFIDENCE_LOW"), evidence)

        verb = DecisionVerb.ACCEPT
        if direction < 0:
            # A falling mid is not an invitation to buy. Whether it means EXIT or a short depends on
            # what is held, which the engine decides; the analyzer states the direction and lets the
            # caller resolve it against the position.
            verb = DecisionVerb.EXIT
        return build(verb, confidence, tuple(reasons), evidence)

    # -- internals ---------------------------------------------------------

    def _imbalance(self, entry: dict[str, Any]) -> Decimal | None:
        """(bid_size - ask_size) / (bid_size + ask_size), in [-1, 1]. ``None`` without both sizes."""
        bid_size = entry["bid_size"]
        ask_size = entry["ask_size"]
        if not isinstance(bid_size, Decimal) or not isinstance(ask_size, Decimal):
            return None
        total = bid_size + ask_size
        if total <= 0:
            return None
        return ((bid_size - ask_size) / total).quantize(Decimal("0.0001"))

    def _age(self, observed: Any, now: datetime) -> Decimal | None:
        if not isinstance(observed, datetime):
            return None
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        return Decimal((now - observed).total_seconds()).quantize(Decimal("0.001"))
