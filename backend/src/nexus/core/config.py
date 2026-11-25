"""Application settings.

Security rules (Section 13.3, D-019):
- Configuration carries secret *references*, never secret values.
- Live trading defaults to disabled. Enabling it requires several independent,
  explicitly-set conditions (see :class:`LiveAuthority` in nexus.risk.authority).
- Unknown or contradictory configuration resolves to the most restrictive behaviour.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    version: str = "0.1.0"
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
    base_currency: str = "USD"  # O-001 per-account currency remains OPEN

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

    @field_validator("base_currency", "timezone_display")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings. Cached; call :func:`reset_settings_cache` in tests."""
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
