"""Application settings.

Security rules (Section 13.3, D-019):
- Configuration carries secret *references*, never secret values.
- Live trading defaults to disabled. Enabling it requires several independent,
  explicitly-set conditions (see :class:`LiveAuthority` in nexus.risk.authority).
- Unknown or contradictory configuration resolves to the most restrictive behaviour.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus import __version__
from nexus.core.environment import EnvironmentState

SecretRef = str  # a *name* to resolve via the secrets provider, never a raw value


class RiskLimits(BaseSettings):
    """Hard, deterministic risk limits (Section 10.1). PROVISIONAL per D-006/O-002.

    These values override any model, strategy or plugin output. They are conservative by
    owner decision and are enforced by pure functions in :mod:`nexus.risk.engine`.
    """

    model_config = SettingsConfigDict(env_prefix="NEXUS_RISK_", extra="ignore")

    max_risk_per_trade_pct: float = Field(default=1.0, ge=0.0, le=100.0)
    max_leverage: float = Field(default=2.0, ge=1.0, le=10.0)
    daily_drawdown_halt_pct: float = Field(default=2.0, ge=0.0, le=100.0)
    max_open_positions: int = Field(default=10, ge=0)
    max_notional_per_position_usd: float = Field(default=25_000.0, ge=0.0)
    max_portfolio_notional_usd: float = Field(default=100_000.0, ge=0.0)
    # Exposure is *notional* as a percentage of equity, so it can legitimately exceed 100%
    # when leverage is used (2x leverage permits up to 200% of equity in notional).
    max_single_instrument_exposure_pct: float = Field(default=10.0, ge=0.0, le=1000.0)
    max_correlated_exposure_pct: float = Field(default=25.0, ge=0.0, le=1000.0)
    min_stop_distance_pct: float = Field(default=0.05, ge=0.0)
    max_participation_of_adv_pct: float = Field(default=1.0, ge=0.0)


class DataQualityLimits(BaseSettings):
    """Freshness thresholds. Exceeding them blocks *new risk* (fail closed)."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_DATA_", extra="ignore")

    max_quote_age_seconds: float = Field(default=5.0, gt=0.0)
    max_book_age_seconds: float = Field(default=10.0, gt=0.0)
    max_account_snapshot_age_seconds: float = Field(default=60.0, gt=0.0)
    allow_stale_reads: bool = True  # reads allowed, labelled stale; new risk still blocked


class SecretsConfig(BaseSettings):
    """Secrets are resolved from a provider by reference name only."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_SECRETS_", extra="ignore")

    backend: Literal["openbao", "sops", "env"] = "env"
    # These are *reference names* used to look a secret up in the provider — not secret
    # values. No credential ever appears in this file, in CI logs, or in the audit trail.
    # The S105 suppressions below are deliberate: ruff pattern-matches on the field names.
    ref_bybit_api_key: SecretRef = "bybit/api-key"  # noqa: S105 - reference name, not a value
    ref_bybit_api_secret: SecretRef = "bybit/api-secret"  # noqa: S105 - reference name, not a value
    ref_okx_api_key: SecretRef = "okx/api-key"  # noqa: S105 - reference name, not a value
    ref_okx_api_secret: SecretRef = "okx/api-secret"  # noqa: S105 - reference name, not a value
    ref_okx_passphrase: SecretRef = "okx/passphrase"  # noqa: S105 - reference name, not a value
    ref_owner_totp_secret: SecretRef = "owner/totp-secret"  # noqa: S105 - reference name, not a value
    ref_owner_api_token: SecretRef = "owner/api-token"  # noqa: S105 - reference name, not a value
    ref_telegram_bot_token: SecretRef = "alerts/telegram-bot-token"  # noqa: S105 - reference name
    ref_brevo_api_key: SecretRef = "alerts/brevo-api-key"  # noqa: S105 - reference name, not a value

    @field_validator("backend")
    @classmethod
    def _validate_backend(cls, value: str) -> str:
        """Backend must be one of the free/OSS options (D-019). No cloud KMS."""
        if value not in {"openbao", "sops", "env"}:
            raise ValueError(f"unsupported secrets backend: {value}")
        return value


class AlertConfig(BaseSettings):
    """Free channels only (D-019/D-020). SMS and WhatsApp are not available at $0."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_ALERTS_", extra="ignore")

    telegram_enabled: bool = True
    webpush_enabled: bool = True
    email_enabled: bool = True
    in_app_enabled: bool = True
    # Deliberately absent: sms_enabled, whatsapp_enabled (BLOCKED by D-019, O-006).
    email_daily_budget: int = Field(default=250, ge=0, le=300)  # Brevo free cap is 300/day
    max_retries: int = Field(default=3, ge=0)
    escalation_after_seconds: float = Field(default=120.0, gt=0.0)


class ModelConfig_(BaseSettings):
    """Intelligence layer policy under the zero-cost constraint (Q-06 default)."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_MODEL_", extra="ignore")

    local_first: bool = True  # Ollama on-box; sensitive context never leaves the host
    allow_free_hosted_apis: bool = True  # Gemini/Groq/OpenRouter free tiers, non-sensitive only
    allow_paid_apis: bool = False  # D-019: hard-off. Changing this needs an owner decision.
    abstain_when_unavailable: bool = True  # fail closed: ABSTAIN, never guess
    forbid_sensitive_data_to_hosted_models: bool = True
    max_daily_hosted_requests: int = Field(default=900, ge=0)  # below Groq's 1,000/day cap


class Settings(BaseSettings):
    """Root configuration."""

    model_config = SettingsConfigDict(env_prefix="NEXUS_", extra="ignore")

    app_name: str = "NEXUS"
    # Bound to the package version so the API, the docs and the config can never disagree
    # about which build is running (they drifted at the Phase 2 -> 3 transition).
    version: str = __version__
    environment: EnvironmentState = EnvironmentState.DISABLED

    # Live-authority gates. All must be true, plus environment >= PILOT, plus the
    # runtime kill switch off, before any real order can be sent. Defaults are the
    # restrictive ones (Section 34: never live-by-default).
    live_trading_enabled: bool = False
    legal_review_complete: bool = False  # O-004 Nigerian jurisdiction review
    owner_live_authority_granted: bool = False  # separate approval after Phases 0-9
    withdrawal_permission_forbidden: bool = True  # Section 13.3: trade-only keys

    database_url: str = "sqlite:///./data/nexus.db"
    audit_retention_days: int = Field(default=2555, ge=30)  # 7 years (Q-04 default)
    market_data_retention_days: int = Field(default=1095, ge=7)  # 3 years, tiered rollups

    timezone_display: str = "UTC"
    # D-025 (closes O-001 for the system base): all equity, sizing and risk math is in USD.
    base_currency: str = "USD"
    # NGN is shown alongside for tax/ISA reporting only. It is never used for limit math, so
    # a missing or stale NGN rate cannot loosen a risk limit. When no free rate is available
    # the NGN column must read UNAVAILABLE, never an estimate.
    reporting_currency: str = "NGN"

    # ---- Phase 3: first-party market-data archive (D-024 tiered retention) ----
    archive_root: str = "./data/archive"
    #: Free, public, unauthenticated data sources. Comma-separated; empty disables ingestion.
    #: None of these can place an order, and none is given a credential (D-026).
    data_sources_enabled: str = "bybit-public,okx-public,binance-vision,dukascopy"

    # ---- Stage 11: the paper trading platform (D-059) ----
    # Every one of these configures a *simulation*. None of them can bring a live order closer to
    # existing: the paper package holds no socket, no HTTP client and no credential, and it never
    # consults LiveAuthority. `paper_enabled` turns the rehearsal off; it cannot turn trading on.
    paper_enabled: bool = True
    paper_account_id: str = "PAPER-MAIN"
    paper_currency: str = "USD"
    #: Simulated starting capital. A round number by design: the point is the *shape* of the result,
    #: and a starting balance chosen to make a curve look good is the first way a simulation lies.
    paper_starting_cash: Decimal = Field(default=Decimal("100000"), gt=0)
    # Execution costs. Defaults are adverse on purpose — see nexus.paper.fill_model.
    paper_slippage_bps: Decimal = Field(default=Decimal("2"), ge=0)
    paper_commission_bps: Decimal = Field(default=Decimal("5"), ge=0)
    paper_minimum_commission: Decimal = Field(default=Decimal("0.10"), ge=0)
    paper_latency_ms: int = Field(default=120, ge=0)
    paper_max_quote_age_seconds: Decimal = Field(default=Decimal("30"), gt=0)
    paper_respect_displayed_size: bool = True
    paper_refuse_delayed_data: bool = True
    # Sizing and exposure limits.
    paper_risk_fraction: Decimal = Field(default=Decimal("0.02"), gt=0, le=1)
    paper_max_position_notional: Decimal = Field(default=Decimal("25000"), gt=0)
    paper_max_open_positions: int = Field(default=8, ge=1)
    # The real-time loop.
    paper_min_analysis_interval_seconds: Decimal = Field(default=Decimal("1"), ge=0)
    paper_post_trade_cooldown_seconds: Decimal = Field(default=Decimal("60"), ge=0)
    paper_stream_interval_seconds: float = Field(default=1.0, gt=0)
    # D-057's confidence band, applied to the reference analyzer.
    paper_confidence_low: Decimal = Field(default=Decimal("0.35"), ge=0, le=1)
    paper_confidence_high: Decimal = Field(default=Decimal("0.70"), ge=0, le=1)
    paper_momentum_threshold_bps: Decimal = Field(default=Decimal("15"), ge=0)
    paper_minimum_history: int = Field(default=12, ge=2)
    paper_analysis_window: int = Field(default=20, ge=2)
    #: Instruments the loop will act on. Empty means "everything observed", which is the right
    #: default for a rehearsal and the wrong one for a production feed.
    paper_watchlist: str = ""
    #: What the runner polls: "source:SYMBOL,SYMBOL;source:SYMBOL". Real-time sources only — a
    #: historical archive cannot serve a live quote, and feeding one to a real-time loop would
    #: produce analysis of a market that has already moved (the runner refuses it by name).
    #: The default is OKX's seeded mapping, which is at DATA_AVAILABLE. Bybit's BTCUSDT mapping is
    #: only SUPPORTED — below the pipeline's archive floor — so a Bybit default would accept nothing
    #: and report a flat, healthy-looking curve. See `paper/runner.py:_DEFAULT_FEED`.
    paper_feed: str = "okx-public:BTC-USDT-SWAP"
    paper_poll_seconds: float = Field(default=5.0, gt=0)

    risk: RiskLimits = Field(default_factory=RiskLimits)
    data_quality: DataQualityLimits = Field(default_factory=DataQualityLimits)
    secrets: SecretsConfig = Field(default_factory=SecretsConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    models: ModelConfig_ = Field(default_factory=ModelConfig_)

    @field_validator("environment", mode="before")
    @classmethod
    def _coerce_environment(cls, value: object) -> object:
        """Accept name or number; anything unrecognised becomes DISABLED (fail closed)."""
        if isinstance(value, EnvironmentState):
            return value
        if isinstance(value, str):
            try:
                return EnvironmentState[value.strip().upper()]
            except KeyError:
                return EnvironmentState.DISABLED
        if isinstance(value, int):
            try:
                return EnvironmentState(value)
            except ValueError:
                return EnvironmentState.DISABLED
        return EnvironmentState.DISABLED

    @field_validator("base_currency", "timezone_display", "reporting_currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()

    @property
    def enabled_data_sources(self) -> tuple[str, ...]:
        """Parsed list of free public data sources. Empty means ingestion is off."""
        return tuple(part.strip() for part in self.data_sources_enabled.split(",") if part.strip())

    def is_data_source_enabled(self, name: str) -> bool:
        return name.strip().lower() in {s.lower() for s in self.enabled_data_sources}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached; call :func:`reset_settings_cache` in tests."""
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
