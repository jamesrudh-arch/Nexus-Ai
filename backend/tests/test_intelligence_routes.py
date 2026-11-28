"""The read-only dossier route (L-D, Stage 8.3), and the honesty of what it cannot serve.

``docs/15`` §6 scoped this lever as *"`/v1/intelligence/dossiers`, read-only, serving what exists and
rendering empty honestly"*, because the Intelligence Centre chrome has been reserved since D-035 with
nothing behind it. So the interesting assertions here are not that a 200 comes back. They are:

* that an empty list says what empty means instead of looking like a working route with no data —
  the distinction ``/v1/data/coverage`` already draws between "no archive" and "archive holds nothing";
* that the elements of ``docs/03`` J-04 and ``docs/10`` §3.1's dossier view which have no column to come
  from are **named in the response** rather than silently omitted, so the view cannot render as complete;
* that there is no write verb on either path, at the router level and not only by convention;
* and that the served evidence checksum is *recomputed* on the way out (F-21), which is the first place
  in the system where an evidence row's integrity is checked rather than merely recorded.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from nexus.api.app import DOSSIER_VIEW_GAPS, DOSSIER_VOCABULARIES, create_app
from nexus.core.config import Settings
from nexus.data.freshness import DataStatus
from nexus.intelligence.dossier import (
    SUFFICIENCY_BASIS_KEY,
    SUFFICIENCY_TARGET_KEY,
    VENUE_MAPS_INSTRUMENT_KEY,
    open_dossier,
)
from nexus.intelligence.evidence import CHECKSUMMED_FIELDS, record_evidence

LIST_PATH = "/v1/intelligence/dossiers"
OBSERVED = datetime(2026, 11, 26, 12, 0, 0, tzinfo=UTC)
RETRIEVED = OBSERVED + timedelta(milliseconds=300)
BTC_PERP = "INS-BTC-USDT-USDT"
EUR_USD = "INS-EUR-USD"
SUMMARY = "Perp basis widening into the US session."
UNCERTAINTY = "Sixty seconds of ticker data only."


@pytest.fixture
def booted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, TestClient]]:
    """A durable boot, so the app seeds and projects the master and dossiers have parents to point at."""
    monkeypatch.setenv("NEXUS_AUDIT_BACKEND", "sqlite")
    path = tmp_path / "nexus.db"
    app = create_app(settings=Settings(_env_file=None, database_url=f"sqlite:///{path}"))
    client = TestClient(app)
    yield app, client
    client.close()


def _open(app: Any, **overrides: Any) -> str:
    base: dict[str, Any] = {
        "summary": SUMMARY,
        "uncertainty": UNCERTAINTY,
        "instrument_id": BTC_PERP,
        "venue": "OKX",
    }
    base.update(overrides)
    receipt = open_dossier(audit=app.state.audit, store=app.state.store, **base)
    return str(receipt.dossier_id)


def _attach(app: Any, dossier_id: str, source: str, at: datetime, **extra: Any) -> str:
    receipt = record_evidence(
        audit=app.state.audit,
        store=app.state.store,
        source=source,
        observed_at=at,
        retrieved_at=at + timedelta(milliseconds=300),
        data_status=DataStatus.LIVE,
        locator=f"https://www.okx.com/api/v5/market/{source.split('.')[-1]}",
        dossier_id=dossier_id,
        payload={"bid": "60736.2"},
        **extra,
    )
    return str(receipt.evidence_id)


class TestTheRouteIsReadOnly:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    def test_no_write_verb_exists_on_the_collection(
        self, booted: tuple[Any, TestClient], method: str
    ) -> None:
        app, client = booted
        response = getattr(client, method)(LIST_PATH)
        assert response.status_code == 405, "read-only at the router, not only by convention"

    def test_only_get_is_registered_on_either_path(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        methods = {
            method
            for route in app.routes
            if LIST_PATH in getattr(route, "path", "")
            for method in route.methods
        }
        assert methods == {"GET"}, methods

    def test_both_paths_are_published_under_the_intelligence_tag(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        app, client = booted
        spec = client.get("/openapi.json").json()
        assert spec["paths"][LIST_PATH]["get"]["tags"] == ["intelligence"]
        assert spec["paths"][f"{LIST_PATH}/{{dossier_id}}"]["get"]["tags"] == ["intelligence"]
        assert "post" not in spec["paths"][LIST_PATH]

    def test_the_limit_is_bounded(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        assert client.get(LIST_PATH, params={"limit": 200}).status_code == 200
        assert client.get(LIST_PATH, params={"limit": 1}).status_code == 200
        assert client.get(LIST_PATH, params={"limit": 0}).status_code == 422
        assert client.get(LIST_PATH, params={"limit": 201}).status_code == 422


class TestTheEmptyIsHonest:
    def test_an_empty_list_says_what_empty_means(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        body = client.get(LIST_PATH).json()
        assert body["count"] == 0
        assert body["dossiers"] == []
        empty = body["empty"]
        assert empty is not None, "an empty list without an explanation renders as a working route"
        assert empty["meaning"] == "no dossier has been opened at all"
        assert "open_dossier" in empty["writer"]
        assert "none yet" in empty["callers"], "the writer exists and nothing calls it — said out loud"
        assert "/v1/data/coverage" in empty["not_a_fault"]

    def test_the_empty_is_scoped_when_the_list_is_filtered(self, booted: tuple[Any, TestClient]) -> None:
        """Otherwise a filter that matches nothing reads as a system that has researched nothing."""
        app, client = booted
        _open(app)
        body = client.get(LIST_PATH, params={"instrument_id": EUR_USD}).json()
        assert body["count"] == 0
        assert body["empty"]["meaning"] == "no dossier has been opened for this instrument"

    def test_empty_disappears_once_a_case_exists(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        _open(app)
        body = client.get(LIST_PATH).json()
        assert body["empty"] is None
        assert body["count"] == 1


class TestWhatIsServed:
    def test_a_dossier_round_trips_through_the_route(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        dossier_id = _open(
            app,
            sufficiency="SUFFICIENT_FOR_REVIEW",
            sufficiency_basis="one okx ticker and one book snapshot, both LIVE",
            sufficiency_target="V1 evidence and data sufficiency, not a trade",
        )
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["dossier_id"] == dossier_id
        assert served["instrument_id"] == BTC_PERP
        assert served["venue"] == "OKX"
        assert served[VENUE_MAPS_INSTRUMENT_KEY] is True
        assert (served["state"], served["stance"]) == ("DRAFT", "ABSTAIN")
        assert served["summary"] == SUMMARY
        assert served["uncertainty"] == UNCERTAINTY
        assert served["sufficiency"] == "SUFFICIENT_FOR_REVIEW"
        assert served[SUFFICIENCY_BASIS_KEY] == "one okx ticker and one book snapshot, both LIVE"
        assert served[SUFFICIENCY_TARGET_KEY] == "V1 evidence and data sufficiency, not a trade"
        assert served["audit_ref"], "the run-record link docs/10 §3.1 asks for"
        assert served["created_at"] and served["updated_at"]

    def test_the_pinned_keys_are_lifted_out_of_the_payload_beside_it(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """A reader should not have to know they live in ``payload`` to find them."""
        app, client = booted
        _open(app, sufficiency_basis="the basis", sufficiency_target="the target")
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served[SUFFICIENCY_BASIS_KEY] == "the basis"
        assert served["payload"][SUFFICIENCY_BASIS_KEY] == "the basis"

    def test_the_chronology_runs_forwards_while_the_store_returns_newest_first(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """``docs/10`` §3.1 asks the dossier view for a chronology, and a chronology does not run
        backwards — which is the opposite of the order ``store.evidence_refs`` returns."""
        app, client = booted
        dossier_id = _open(app)
        first = _attach(app, dossier_id, "okx.books", OBSERVED)
        second = _attach(app, dossier_id, "okx.ticker", OBSERVED + timedelta(seconds=2))
        stored = [row["evidence_id"] for row in app.state.store.evidence_refs(dossier_id=dossier_id)]
        assert stored == [second, first], "the store really does return newest first"

        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["evidence_count"] == 2
        assert [entry["evidence_id"] for entry in served["chronology"]] == [first, second]
        entry = served["chronology"][0]
        assert entry["source"] == "okx.books"
        assert entry["observed_at"] == "2026-11-26T12:00:00.000Z"
        assert entry["retrieved_at"] == "2026-11-26T12:00:00.300Z"
        assert entry["observed_at_source"] == "VENUE"
        assert entry["apparent_latency_seconds"] == pytest.approx(0.3)
        assert entry["data_status"] == "LIVE"
        assert entry["locator"].endswith("/books")
        assert entry["audit_ref"]

    def test_evidence_can_be_left_out_but_the_count_is_still_told(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        app, client = booted
        dossier_id = _open(app)
        _attach(app, dossier_id, "okx.ticker", OBSERVED)
        served = client.get(LIST_PATH, params={"evidence": "false"}).json()["dossiers"][0]
        assert served["chronology"] is None
        assert served["evidence_count"] == 1

    def test_the_detail_route_serves_one_case(self, booted: tuple[Any, TestClient]) -> None:
        """``docs/03`` J-04 step 1 is "selects case", which needs a single-case read."""
        app, client = booted
        dossier_id = _open(app)
        body = client.get(f"{LIST_PATH}/{dossier_id}").json()
        assert body["dossier"]["dossier_id"] == dossier_id
        assert body["dossier"]["chronology"] == []
        assert body["view_gaps"] == list(DOSSIER_VIEW_GAPS)
        assert body["vocabularies"] == DOSSIER_VOCABULARIES

    def test_an_unknown_id_is_a_404_and_not_a_successful_empty(self, booted: tuple[Any, TestClient]) -> None:
        """A typo and a case that holds nothing must not look the same."""
        app, client = booted
        response = client.get(f"{LIST_PATH}/CASE-NOPE")
        assert response.status_code == 404
        assert response.json() == {"detail": "unknown dossier: CASE-NOPE"}

    def test_the_filter_narrows_to_one_instrument(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        perp = _open(app, instrument_id=BTC_PERP, venue="OKX")
        fx = _open(app, instrument_id=EUR_USD, venue="DUKASCOPY")
        assert client.get(LIST_PATH).json()["count"] == 2
        served = client.get(LIST_PATH, params={"instrument_id": EUR_USD}).json()
        assert served["count"] == 1
        assert served["dossiers"][0]["dossier_id"] == fx
        assert perp not in {row["dossier_id"] for row in served["dossiers"]}

    def test_a_dossier_with_no_instrument_is_still_served(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        dossier_id = _open(app, instrument_id=None, venue=None)
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["dossier_id"] == dossier_id
        assert served["instrument_id"] is None
        assert served[VENUE_MAPS_INSTRUMENT_KEY] is None
        assert client.get(LIST_PATH, params={"instrument_id": BTC_PERP}).json()["count"] == 0


class TestTheServedChecksumIsRecomputedNotTrusted:
    def test_an_untampered_row_verifies(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        dossier_id = _open(app)
        _attach(app, dossier_id, "okx.ticker", OBSERVED)
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["chronology"][0]["checksum_ok"] is True
        assert served["evidence_checksums_verify"] is True

    def test_tampering_with_a_stored_column_is_visible_in_the_response(
        self, booted: tuple[Any, TestClient], tmp_path: Path
    ) -> None:
        """F-21's payoff: the checksum covers ten stored fields including ``observed_at`` — nine when F-21
        widened it from one, and ten since Stage 8.5 added ``contradicts`` to the table and to the covered
        set in one commit — and this route is the first reader that recomputes it, so an altered row is
        reported rather than served."""
        app, client = booted
        dossier_id = _open(app)
        evidence_id = _attach(app, dossier_id, "okx.ticker", OBSERVED)
        conn = sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)
        conn.execute(
            "UPDATE evidence_ref SET observed_at = ? WHERE evidence_id = ?",
            ("2020-01-01T00:00:00.000Z", evidence_id),
        )
        conn.close()

        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["chronology"][0]["checksum_ok"] is False
        assert served["chronology"][0]["observed_at"] == "2020-01-01T00:00:00.000Z"
        assert served["evidence_checksums_verify"] is False
        detail = client.get(f"{LIST_PATH}/{dossier_id}").json()["dossier"]
        assert detail["evidence_checksums_verify"] is False

    def test_a_row_with_no_checksum_does_not_verify_as_fine(
        self, booted: tuple[Any, TestClient], tmp_path: Path
    ) -> None:
        """``checksum`` is nullable, so absence fails closed: no evidence of tampering is not evidence
        of integrity."""
        app, client = booted
        dossier_id = _open(app)
        evidence_id = _attach(app, dossier_id, "okx.ticker", OBSERVED)
        conn = sqlite3.connect(tmp_path / "nexus.db", isolation_level=None)
        conn.execute("UPDATE evidence_ref SET checksum = NULL WHERE evidence_id = ?", (evidence_id,))
        conn.close()
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["chronology"][0]["checksum_ok"] is False

    def test_a_dossier_with_no_evidence_says_none_rather_than_true(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """``all(())`` is ``True``, which would report a case with no evidence as verified."""
        app, client = booted
        _open(app)
        served = client.get(LIST_PATH).json()["dossiers"][0]
        assert served["evidence_count"] == 0
        assert served["evidence_checksums_verify"] is None

    def test_the_route_does_not_mutate_the_row_it_verifies(self, booted: tuple[Any, TestClient]) -> None:
        app, client = booted
        dossier_id = _open(app)
        _attach(app, dossier_id, "okx.ticker", OBSERVED)
        client.get(LIST_PATH)
        client.get(f"{LIST_PATH}/{dossier_id}")
        row = app.state.store.evidence_refs(dossier_id=dossier_id)[0]
        assert set(row) == set(CHECKSUMMED_FIELDS) | {"checksum", "audit_ref"}


class TestARecordedContradictionIsServedBothWays:
    """``docs/10`` §3.1 asks the dossier view for *"contradictions highlighted and linked"*.

    Stage 8.5 added ``evidence_ref.contradicts`` (migration ``0005_memory_beliefs``, F-18's fourth gap), so
    the *link* half is servable and this class pins it: the stored direction, the derived reverse direction,
    and a count at the top of the case. What it also pins is that serving the link decides nothing — no
    winner, no downgrade, no verdict — because ``docs/12`` §1.3's law (A-02+A-08) is that no gate can be
    satisfied by a confidence value, and the gap stays open for exactly that reason.
    """

    def test_both_directions_of_one_recorded_disagreement_are_served(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        app, client = booted
        dossier_id = _open(app)
        first = _attach(app, dossier_id, "okx.books", OBSERVED)
        second = _attach(app, dossier_id, "bybit.books", OBSERVED + timedelta(seconds=2), contradicts=first)

        served = client.get(f"{LIST_PATH}/{dossier_id}").json()["dossier"]
        assert served["contradiction_count"] == 1
        by_id = {entry["evidence_id"]: entry for entry in served["chronology"]}
        assert by_id[second]["contradicts"] == first, "the stored direction"
        assert by_id[second]["contradicted_by"] == []
        assert by_id[first]["contradicts"] is None
        assert by_id[first]["contradicted_by"] == [second], "the derived reverse direction"

    def test_a_case_with_no_recorded_disagreement_says_zero_and_not_none(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """Zero is a fact this route can establish from the rows it holds; ``None`` would be an admission
        that it did not look, and it did look."""
        app, client = booted
        dossier_id = _open(app)
        first = _attach(app, dossier_id, "okx.books", OBSERVED)
        served = client.get(f"{LIST_PATH}/{dossier_id}").json()["dossier"]
        assert served["contradiction_count"] == 0
        assert served["chronology"][0]["contradicts"] is None
        assert served["chronology"][0]["contradicted_by"] == []
        assert first

    def test_two_rows_pointing_at_one_are_one_pair_each(self, booted: tuple[Any, TestClient]) -> None:
        """The count is of distinct pairs, not of pointers, so a row contradicted twice reads as two
        disagreements and a mutual one would read as one."""
        app, client = booted
        dossier_id = _open(app)
        first = _attach(app, dossier_id, "okx.books", OBSERVED)
        second = _attach(app, dossier_id, "bybit.books", OBSERVED + timedelta(seconds=2), contradicts=first)
        third = _attach(app, dossier_id, "binance.books", OBSERVED + timedelta(seconds=4), contradicts=first)
        served = client.get(f"{LIST_PATH}/{dossier_id}").json()["dossier"]
        assert served["contradiction_count"] == 2
        by_id = {entry["evidence_id"]: entry for entry in served["chronology"]}
        assert by_id[first]["contradicted_by"] == sorted([second, third])

    def test_serving_a_contradiction_decides_nothing(self, booted: tuple[Any, TestClient]) -> None:
        """Both rows are served unchanged and both still verify.

        A route that marked the contradicted row stale, hid it, or ranked it below the row that contradicts
        it would be resolving a disagreement nobody asked it to resolve — and ``docs/10`` §3.2 is explicit
        that confidence never overrides a failed stage, so no numeric column may settle it either.
        """
        app, client = booted
        dossier_id = _open(app)
        first = _attach(app, dossier_id, "okx.books", OBSERVED)
        _attach(app, dossier_id, "bybit.books", OBSERVED + timedelta(seconds=2), contradicts=first)

        before = app.state.store.get_evidence_ref(first)
        client.get(LIST_PATH)
        client.get(f"{LIST_PATH}/{dossier_id}")
        after = app.state.store.get_evidence_ref(first)
        assert after == before, "the read did not touch the row it served"

        served = client.get(f"{LIST_PATH}/{dossier_id}").json()["dossier"]
        assert served["evidence_checksums_verify"] is True
        assert all(entry["data_status"] == "LIVE" for entry in served["chronology"])
        assert {"winner", "resolved", "verdict", "losing_evidence"} & set(served) == set()

    def test_a_contradiction_across_two_cases_appears_in_neither_scan(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """The derived reverse direction is scoped to one dossier, and this pins the limit rather than
        hiding it: the pointer is stored and served on the row that made it, but the case that was
        contradicted shows no reverse link, because the row that contradicts it is not among its own.

        That is one of the three reasons the ``contradictions`` gap stays open after Stage 8.5.
        """
        app, client = booted
        one = _open(app, summary="The first case.", venue="OKX")
        two = _open(app, summary="The second case.", venue="BYBIT")
        target = _attach(app, one, "okx.books", OBSERVED)
        _attach(app, two, "bybit.books", OBSERVED + timedelta(seconds=2), contradicts=target)

        first = client.get(f"{LIST_PATH}/{one}").json()["dossier"]
        second = client.get(f"{LIST_PATH}/{two}").json()["dossier"]
        assert first["contradiction_count"] == 0, (
            "the contradicted case cannot see a row that is not one of its own"
        )
        assert first["chronology"][0]["contradicted_by"] == []
        assert second["contradiction_count"] == 1, "the stored direction is served wherever the row is"
        assert second["chronology"][0]["contradicts"] == target
        assert second["chronology"][0]["contradicted_by"] == []


class TestTheGapsArePartOfTheResponse:
    def test_every_gap_names_its_source_and_its_reason(self) -> None:
        assert len(DOSSIER_VIEW_GAPS) >= 8, "the approved view asks for more than the schema can serve"
        for gap in DOSSIER_VIEW_GAPS:
            assert set(gap) == {"element", "asked_by", "why_not_servable", "deferred_by"}, gap
            assert gap["asked_by"].startswith(("docs/03", "docs/10")), gap
            assert len(gap["why_not_servable"]) > 40, gap

    @pytest.mark.parametrize(
        "element",
        [
            "contradictions highlighted and linked",
            "counter-thesis",
            "publication time in the evidence table",
            "research depth Tier 0–4",
            "freshness",
            "quant result with run id",
            "knowledge-sufficiency meter",
            "beliefs with confidence band, validity interval and change conditions",
            "disposition with reason code",
        ],
    )
    def test_what_the_approved_view_asks_for_is_either_served_or_named(self, element: str) -> None:
        assert element in {gap["element"] for gap in DOSSIER_VIEW_GAPS}

    def test_the_gaps_a_ruling_moved_name_the_ruling_and_which_kind_it_was(self) -> None:
        """Three gaps cite D-051 and they are not the same kind of thing: two were deferred to the
        stage-10 writer, and the third was given a batch of its own. A test that counted them without
        distinguishing them would pass on a ruling that meant something else.

        The third has since changed kind, and this test changed with it rather than being left to
        pass on stale text: Stage 8.4 **ran** and did not fill the gap, because its ruling scoped it
        to F-14's expensive half alone — no new tables, no new columns, no writer wiring. So the gap
        is no longer scheduled for a batch that has not happened; it is unscheduled, and the route
        must say so instead of pointing at a batch the reader can go and find already merged.

        The other two changed kind in Stage 8.5, which **is** the batch they were deferred to, and
        each was filled differently: the contradiction link arrived and is served both ways, while the
        beliefs gap gained three columns and a writer but no route and no band. Both texts now say what
        landed and what did not, for the same reason the publication-time one does — a gap that still
        reads as waiting sends the reader to a queue that is empty, and a gap that reads as closed hides
        the half that is not.
        """
        ruled = [gap for gap in DOSSIER_VIEW_GAPS if gap["deferred_by"] and "D-051" in gap["deferred_by"]]
        assert {gap["element"] for gap in ruled} == {
            "contradictions highlighted and linked",
            "publication time in the evidence table",
            "beliefs with confidence band, validity interval and change conditions",
        }
        deferred = [gap for gap in ruled if "stage-10" in gap["deferred_by"]]
        assert {gap["element"] for gap in deferred} == {
            "contradictions highlighted and linked",
            "beliefs with confidence band, validity interval and change conditions",
        }, "F-18's columns, deferred by D-051 to the batch that writes memory_item"
        scheduled = [gap for gap in ruled if "8.4" in gap["deferred_by"]]
        assert [gap["element"] for gap in scheduled] == ["publication time in the evidence table"]
        assert [
            gap for gap in ruled if "stage-10" in gap["deferred_by"] and "8.4" in gap["deferred_by"]
        ] == []
        # And the batch it names has landed, which the text must not hide: a gap that says "waiting
        # on 8.4" after 8.4 merged sends the reader to a queue that is empty.
        publication = next(gap for gap in ruled if gap["element"] == "publication time in the evidence table")
        assert "has now landed" in publication["deferred_by"], (
            "the publication-time gap still reads as though Stage 8.4 had not run"
        )
        assert "Nothing is scheduled" in publication["deferred_by"], (
            "a gap with no batch behind it must say so, rather than implying one is coming"
        )
        assert "receipt time" in publication["why_not_servable"], (
            "the gap must say why a receipt time does not fill it: when we got it is not when the "
            "source published it"
        )

        contradictions = next(
            gap for gap in deferred if gap["element"] == "contradictions highlighted and linked"
        )
        assert "has now landed" in contradictions["deferred_by"], (
            "the stage-10 batch this gap was deferred to has run, and the text must not imply it has not"
        )
        assert "no such column" not in contradictions["why_not_servable"], (
            "evidence_ref.contradicts exists since migration 0005_memory_beliefs; a gap that still says "
            "the column is missing sends the reader to a defect that was fixed"
        )
        assert "contradicts" in contradictions["why_not_servable"], "and must name the column that arrived"
        assert "A-02+A-08" in contradictions["why_not_servable"], (
            "the reason a contradiction is not resolved here is a law, so the gap must cite it rather "
            "than leave the reader to guess whether the verdict is merely unbuilt"
        )

        beliefs = next(
            gap
            for gap in deferred
            if gap["element"] == "beliefs with confidence band, validity interval and change conditions"
        )
        assert "has now landed" in beliefs["deferred_by"]
        why = beliefs["why_not_servable"]
        assert "schema-only" not in why and "no writer" not in why, (
            "memory_item has a writer since Stage 8.5; the gap must say what is still missing instead"
        )
        assert "memory.recorded" in beliefs["why_not_servable"], "the writer is named by its audit event"
        assert "no memory_item route" in beliefs["why_not_servable"], (
            "recordable and not readable over HTTP is the part this route cannot serve"
        )
        assert "F-24" in beliefs["why_not_servable"], (
            "the band is the half the three new columns do not deliver — they are on the time axis — and "
            "it is a recorded finding, not an omission this text may quietly absorb"
        )

    def test_the_freshness_gap_says_why_the_stored_status_is_not_a_freshness_reading(self) -> None:
        gap = next(g for g in DOSSIER_VIEW_GAPS if g["element"] == "freshness")
        assert "re-evaluates" in gap["why_not_servable"]
        assert "stays LIVE" in gap["why_not_servable"]

    def test_the_served_dossier_invents_none_of_the_missing_elements(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """Naming a gap is only honest if the response does not also fake filling it."""
        app, client = booted
        _open(app)
        served = client.get(LIST_PATH).json()["dossiers"][0]
        for invented in ("counter_thesis", "contradictions", "tier", "research_tier", "publication_time"):
            assert invented not in served, invented
        assert "uncertainty" in served, "what is unresolved is served as itself, not as a counter-thesis"

    def test_the_vocabularies_say_when_nothing_is_declared(self) -> None:
        assert DOSSIER_VOCABULARIES["stance"]["values"] == [
            "ACCEPT",
            "REJECT",
            "WAIT",
            "REDUCE",
            "EXIT",
            "ESCALATE",
            "ABSTAIN",
        ]
        assert DOSSIER_VOCABULARIES["stance"]["enforced_by"].startswith("the writer")
        assert DOSSIER_VOCABULARIES["sufficiency"]["values"] is None
        assert "stage 10" in DOSSIER_VOCABULARIES["sufficiency"]["source"]
        assert DOSSIER_VOCABULARIES["state"]["values"] is None

    def test_the_note_keeps_a_stance_from_reading_as_a_trade_signal(
        self, booted: tuple[Any, TestClient]
    ) -> None:
        """``docs/03`` J-04's exit condition is "Research completion ≠ trade signal"."""
        app, client = booted
        body = client.get(LIST_PATH).json()
        assert "never a trade signal" in body["note"]
        assert "DENIED" in body["note"]
        assert body["served_from"].startswith("operational projection")


class TestTheRouteAddedNothingToTheStatusPayload:
    def test_the_counts_were_already_there_and_still_are(self, booted: tuple[Any, TestClient]) -> None:
        """``counts()`` has listed ``dossier`` since Stage 6, so an empty Intelligence Centre was always
        observable from ``/v1/status``; this route adds a view, not another key."""
        app, client = booted
        before = client.get("/v1/status").json()
        assert not [key for key in before if "intelligence" in key or "dossier" in key]
        assert before["persistence"]["counts"]["dossier"] == 0
        assert before["persistence"]["counts"]["evidence_ref"] == 0

        dossier_id = _open(app)
        _attach(app, dossier_id, "okx.ticker", OBSERVED)
        after = client.get("/v1/status").json()
        assert sorted(after) == sorted(before), "no new top-level key"
        assert after["persistence"]["counts"]["dossier"] == 1
        assert after["persistence"]["counts"]["evidence_ref"] == 1
        assert after["persistence"]["counts"]["memory_item"] == 0
        assert after["instrument_master"] == before["instrument_master"]
