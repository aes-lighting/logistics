"""Entity coverage policy for the AES Logistics domain ontology.

Defines which data-model.md entities are (a) required on the TBox, (b) deferred,
and which files feed the coverage freshness snapshot.
"""
from __future__ import annotations

from pathlib import Path

# Entities that must appear as TBox classes in the generated TTL.
REQUIRED_CLASSES = [
    "Delivery", "InventoryEntry", "JobDirectoryEntry",
    "CalendarEvent", "DeliveryTicket", "LineItem", "LocationSlit", "Geotag",
    "SupplyItem", "JitNeed", "Geofence",
]

# Explicitly deferred (accepted, no TBox class yet) — recorded so agents do not
# silently add them without review.
DEFERRED = [
    "ad_hoc_delivery",      # still exists in driver app as new-delivery flow; not a TBox class yet
    "ocr_extraction",       # server does OCR; extraction outcome not yet an entity
    "sms_notification",     # SMS/ETA external service results stay values initially
]

COVERAGE_EXCEPTIONS: dict[str, str] = {
    "delivery_ticket": "Artifact wrapper; not a store root.",
    "calendar_event": "ICS feed projection; read-only, not a store root.",
}


def data_model_path(root: Path) -> Path:
    return root / "specs" / "001-server" / "data-model.md"


def coverage_freshness_files(root: Path) -> list[Path]:
    return [
        data_model_path(root),
        root / ".specify" / "scripts" / "ontology_map.py",
        root / ".specify" / "scripts" / "ontology_vocabularies.py",
        root / ".specify" / "scripts" / "ontology_entity_coverage.py",
    ]


def parse_data_model_entities(text: str) -> tuple[list[str], list[str]]:
    """Return (required, deferred) entity names from data-model.md.

    We currently use the static REQUIRED_CLASSES list; this function returns it
    plus DEFERRED so callers have a single parse path regardless of markdown drift.
    """
    return list(REQUIRED_CLASSES), list(DEFERRED)