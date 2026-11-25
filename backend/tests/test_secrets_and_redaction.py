"""Secrets and redaction tests (Section 13.3, D-019).

Property: a secret value can never reach a log line, an audit record, or an API response,
and a missing secret always fails closed rather than defaulting to something usable.
"""

from __future__ import annotations

import pytest

from nexus.secrets.provider import (
    EnvSecretProvider,
    NullSecretProvider,
    SecretNotFoundError,
    SopsSecretProvider,
    get_secret_provider,
    reset_secret_provider_cache,
)
from nexus.secrets.redaction import MASK, Redactor, redact, redact_mapping


class TestEnvProvider:
    def test_reads_by_reference_name(self) -> None:
        provider = EnvSecretProvider({"NEXUS_SECRET_ALERTS_TELEGRAM_BOT_TOKEN": "value"})
        assert provider.get("alerts/telegram-bot-token") == "value"

    def test_missing_reference_raises(self) -> None:
        provider = EnvSecretProvider({})
        with pytest.raises(SecretNotFoundError):
            provider.get("bybit/api-secret")

    def test_empty_value_treated_as_missing(self) -> None:
        provider = EnvSecretProvider({"NEXUS_SECRET_BYBIT_API_KEY": ""})
        with pytest.raises(SecretNotFoundError):
            provider.get("bybit/api-key")

    def test_try_get_returns_none_instead_of_raising(self) -> None:
        assert EnvSecretProvider({}).try_get("bybit/api-key") is None

    def test_error_message_never_contains_a_value(self) -> None:
        provider = EnvSecretProvider({"NEXUS_SECRET_BYBIT_API_KEY": "SUPER-SECRET-VALUE"})
        with pytest.raises(SecretNotFoundError) as excinfo:
            provider.get("okx/api-secret")
        assert "SUPER-SECRET-VALUE" not in str(excinfo.value)

    def test_available_is_true(self) -> None:
        assert EnvSecretProvider({}).available()


class TestNullProvider:
    def test_provides_nothing(self) -> None:
        provider = NullSecretProvider()
        assert not provider.available()
        with pytest.raises(SecretNotFoundError):
            provider.get("anything")

    def test_try_get_is_none(self) -> None:
        assert NullSecretProvider().try_get("anything") is None


class TestSopsProvider:
    def test_missing_file_is_unavailable(self, tmp_path: object) -> None:
        import pathlib

        provider = SopsSecretProvider(pathlib.Path(str(tmp_path)) / "absent.yaml")
        assert not provider.available()
        with pytest.raises(SecretNotFoundError):
            provider.get("bybit/api-key")

    def test_decrypt_failure_does_not_leak_stderr(self, tmp_path: object) -> None:
        import pathlib

        path = pathlib.Path(str(tmp_path)) / "encrypted.yaml"
        path.write_text("not-a-sops-file", encoding="utf-8")
        provider = SopsSecretProvider(path, sops_binary="/nonexistent/sops-binary")
        with pytest.raises(SecretNotFoundError) as excinfo:
            provider.get("bybit/api-key")
        assert "not-a-sops-file" not in str(excinfo.value)


class TestProviderSelection:
    def test_default_is_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("NEXUS_SECRETS_BACKEND", raising=False)
        reset_secret_provider_cache()
        assert get_secret_provider().name == "env"

    def test_openbao_is_not_pretended_to_work_yet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Phase 2: OpenBao wiring lands in Phase 8. It must fail closed, not fake success.
        monkeypatch.setenv("NEXUS_SECRETS_BACKEND", "openbao")
        reset_secret_provider_cache()
        provider = get_secret_provider()
        assert provider.name == "null"
        assert not provider.available()

    def test_sops_without_file_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("NEXUS_SECRETS_BACKEND", "sops")
        monkeypatch.delenv("NEXUS_SECRETS_SOPS_FILE", raising=False)
        reset_secret_provider_cache()
        assert get_secret_provider().name == "null"


class TestRedaction:
    @pytest.mark.parametrize(
        "key",
        [
            "api_secret",
            "apiKey",
            "password",
            "passphrase",
            "seed_phrase",
            "mnemonic",
            "authorization",
            "bearer",
            "cookie",
            "private_key",
            "totp_secret",
            "signature",
        ],
    )
    def test_sensitive_keys_are_masked(self, key: str) -> None:
        assert redact({key: "whatever"}) == {key: MASK}

    def test_nested_structures_are_redacted(self) -> None:
        payload = {"outer": {"inner": [{"api_secret": "x"}, {"instrument_id": "INS-BTC"}]}}
        result = redact(payload)
        assert result["outer"]["inner"][0]["api_secret"] == MASK
        assert result["outer"]["inner"][1]["instrument_id"] == "INS-BTC"

    def test_jwt_shaped_values_are_masked(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnopqrstuv"
        assert redact({"note": jwt}) == {"note": MASK}

    def test_aws_key_shape_is_masked(self) -> None:
        assert redact({"note": "AKIA" + "A" * 16}) == {"note": MASK}

    def test_pem_block_is_masked(self) -> None:
        pem = "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----"
        assert redact({"note": pem}) == {"note": MASK}

    def test_long_base64_blob_is_masked(self) -> None:
        blob = "A" * 64
        assert redact({"blob": blob}) == {"blob": MASK}

    def test_normal_values_are_preserved(self) -> None:
        payload = {"instrument_id": "INS-BTCUSDT-PERP-BYBIT", "quantity": "0.25", "reason": "DATA_STALE"}
        assert redact(payload) == payload

    def test_non_string_scalars_pass_through(self) -> None:
        assert redact({"count": 3, "ok": True, "none": None}) == {"count": 3, "ok": True, "none": None}

    def test_registered_value_is_scrubbed_from_text(self) -> None:
        redactor = Redactor()
        redactor.register("hunter2-secret-value")
        assert (
            redactor.scrub_text("failed with key hunter2-secret-value at venue")
            == f"failed with key {MASK} at venue"
        )

    def test_scrub_applies_to_nested_strings(self) -> None:
        redactor = Redactor(["super-secret-token"])
        assert redactor.scrub({"error": "auth failed for super-secret-token"}) == {
            "error": f"auth failed for {MASK}"
        }

    def test_redact_mapping_returns_dict(self) -> None:
        assert redact_mapping({"api_secret": "x"}) == {"api_secret": MASK}

    def test_redact_mapping_wraps_non_dict(self) -> None:
        assert redact_mapping({"a": 1}) == {"a": 1}

    def test_short_values_are_not_registered(self) -> None:
        redactor = Redactor(["abc"])
        assert redactor.scrub_text("abc") == "abc"  # too short to treat as a secret


class TestLoggingRedaction:
    def test_structlog_processor_masks_secrets(self) -> None:
        from nexus.observability.logging import _redact_processor

        event = {"event": "connect failed", "api_secret": "abc123", "instrument_id": "INS-BTC"}
        result = _redact_processor(None, "info", event)
        assert result["api_secret"] == MASK
        assert result["instrument_id"] == "INS-BTC"

    def test_audit_payload_cannot_carry_secrets(self) -> None:
        from nexus.audit.log import SecretMaterialDetected, assert_no_secrets

        with pytest.raises(SecretMaterialDetected):
            assert_no_secrets({"connection": {"api_secret": "value"}})
