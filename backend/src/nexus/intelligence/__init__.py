"""Intelligence memory: what the system knows, and what it knows it on (stages 8–10).

Three tables were built in Stage 6 with no writers — `dossier`, `evidence_ref`, `memory_item` — because
their shape had to be right before anything could be written into them. This package is where the writers
arrived: `evidence_ref` in Stage 8.2, `dossier` in 8.3 (D-051), `memory_item` in 8.5 (D-053's ruling 4,
which named this batch as the stage-10 writer D-052 had already ordered) together with migration
`0005_memory_beliefs`' three columns and `evidence_ref.contradicts`.

Stage 9 added a fourth, and it is not one of the three: `decision`, also built in Stage 6 and also never
written, is where a candidate thesis lands. `thesis.py` lives here rather than beside
`domain/decision.py` because this package's own first line claims stages 8–10 and because a thesis is
step 1 of `design/build_board52.py`'s intelligence-to-execution path — the domain dataclass is the shape
of the record, and this package is the discipline around writing one.

All four are built and **none is wired**: no caller in `src/nexus` invokes any of them, and each batch's
test that scans the tree for one keeps saying so. Wiring a writer means deciding what the system should
research, remember, cite and propose, and no ruling has made that decision.

Nothing here decides anything. A dossier records a stance; the stance is produced elsewhere and this
package's default for every one of them is the ABSTAIN side, because an intelligence record that can be
created without a basis is a record that will be. `docs/12` §1.3's law (A-02+A-08) is that no gate can be
satisfied by a confidence value, which is why `memory_item.confidence` is written, read and refused on its
own terms here and is an input to no check anywhere in the system — and why `thesis.py` refuses the three
verbs and six states that would claim a gate this repository has not built yet.
"""

from nexus.intelligence.dossier import (
    DOSSIER_EVENT_TYPE,
    DOSSIER_PREFIX,
    SUFFICIENCY_BASIS_KEY,
    SUFFICIENCY_INSUFFICIENT,
    SUFFICIENCY_TARGET_KEY,
    DossierReceipt,
    open_dossier,
    sufficiency_of,
)
from nexus.intelligence.evidence import (
    EVENT_TYPE,
    EvidenceReceipt,
    ObservedAtSource,
    record_evidence,
    record_snapshot,
    snapshot_payload,
)
from nexus.intelligence.memory import (
    CONFIDENCE_PRECISION,
    CONFIDENCE_SCALE,
    EVIDENCE_IDS_KEY,
    MEMORY_EVENT_TYPE,
    MEMORY_KIND_OBSERVATION,
    MEMORY_PREFIX,
    MEMORY_SCOPE_GLOBAL,
    VALIDITY_OPEN_ENDED_KEY,
    MemoryReceipt,
    confidence_text,
    record_memory_item,
    validity_of,
)
from nexus.intelligence.thesis import (
    GATED_STATES,
    GATED_VERBS,
    THESIS_EVENT_TYPE,
    THESIS_PREFIX,
    THESIS_STATES,
    THESIS_VERBS,
    ThesisReceipt,
    record_thesis,
)

__all__ = [
    "CONFIDENCE_PRECISION",
    "CONFIDENCE_SCALE",
    "DOSSIER_EVENT_TYPE",
    "DOSSIER_PREFIX",
    "EVIDENCE_IDS_KEY",
    "EVENT_TYPE",
    "GATED_STATES",
    "GATED_VERBS",
    "MEMORY_EVENT_TYPE",
    "MEMORY_KIND_OBSERVATION",
    "MEMORY_PREFIX",
    "MEMORY_SCOPE_GLOBAL",
    "SUFFICIENCY_BASIS_KEY",
    "SUFFICIENCY_INSUFFICIENT",
    "SUFFICIENCY_TARGET_KEY",
    "THESIS_EVENT_TYPE",
    "THESIS_PREFIX",
    "THESIS_STATES",
    "THESIS_VERBS",
    "VALIDITY_OPEN_ENDED_KEY",
    "DossierReceipt",
    "EvidenceReceipt",
    "MemoryReceipt",
    "ObservedAtSource",
    "ThesisReceipt",
    "confidence_text",
    "open_dossier",
    "record_evidence",
    "record_memory_item",
    "record_snapshot",
    "record_thesis",
    "snapshot_payload",
    "sufficiency_of",
    "validity_of",
]
