"""Intelligence memory: what the system knows, and what it knows it on (stages 8–10).

Three tables were built in Stage 6 with no writers — `dossier`, `evidence_ref`, `memory_item` — because
their shape had to be right before anything could be written into them. This package is where the
writers arrive: `evidence_ref` in Stage 8.2, `dossier` in 8.3 (D-051), `memory_item` with stage 10.

Nothing here decides anything. A dossier records a stance; the stance is produced elsewhere and this
package's default for every one of them is the ABSTAIN side, because an intelligence record that can be
created without a basis is a record that will be.
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

__all__ = [
    "DOSSIER_EVENT_TYPE",
    "DOSSIER_PREFIX",
    "EVENT_TYPE",
    "SUFFICIENCY_BASIS_KEY",
    "SUFFICIENCY_INSUFFICIENT",
    "SUFFICIENCY_TARGET_KEY",
    "DossierReceipt",
    "EvidenceReceipt",
    "ObservedAtSource",
    "record_evidence",
    "open_dossier",
    "record_snapshot",
    "snapshot_payload",
    "sufficiency_of",
]
