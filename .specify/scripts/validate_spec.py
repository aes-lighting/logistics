#!/usr/bin/env python3
"""Spec Kit ontology validation for AES Logistics.

Three labeled gates (all required):
  1. Spec Kit ontology contract validation
  2. SHACL instance validation
  3. OWL-RL TBox consistency
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from ontology_map import STORE_TO_CLASS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SPECIFY = ROOT / ".specify"
ONTOLOGY = SPECIFY / "ontology"
SNAPSHOT = ONTOLOGY / "snapshots" / "schema.snapshot.json"
VOCAB_SNAPSHOT = ONTOLOGY / "snapshots" / "status-vocab.snapshot.json"
COVERAGE_SNAPSHOT = ONTOLOGY / "snapshots" / "entity-coverage.snapshot.json"
GENERATE = SCRIPTS / "generate_ontology.py"

REQUIRED_FILES = [
    SPECIFY / "spec.md",
    ONTOLOGY / "README.md",
    ONTOLOGY / "aesl_domain.ttl",
    ONTOLOGY / "aesl_domain.generated.ttl",
    ONTOLOGY / "aesl_domain.axioms.ttl",
    ONTOLOGY / "aesl_domain.shacl.ttl",
    ONTOLOGY / "aesl_domain.shacl.enums.ttl",
    ONTOLOGY / "catalog-v001.xml",
    ONTOLOGY / "fixtures" / "phase2-valid.ttl",
    SNAPSHOT,
    VOCAB_SNAPSHOT,
    COVERAGE_SNAPSHOT,
    SCRIPTS / "requirements.txt",
    SCRIPTS / "ontology_map.py",
    SCRIPTS / "ontology_vocabularies.py",
    SCRIPTS / "ontology_entity_coverage.py",
    SCRIPTS / "validate_spec.py",
    SCRIPTS / "validate_instances.py",
    SCRIPTS / "validate_owl.py",
    SCRIPTS / "generate_ontology.py",
    SCRIPTS / "extract_schema_snapshot.py",
    SCRIPTS / "extract_status_vocabularies.py",
    SCRIPTS / "extract_entity_coverage.py",
    ONTOLOGY / "residuals.md",
]

REQUIRED_AXIOM_SNIPPETS = [
    "aesl:Entity",
    "aesl:Delivery",
    "owl:disjointWith",
    "aesl:entityId",
    "owl:FunctionalProperty",
    "aesl:jobNumber",
    "aesl:calendarEventUid",
    "aesl:status",
    "aesl:PolicyNoAutoCompletesDelivery",
    "aesl:PolicyOntologyDoesNotReplacePipelines",
    "aesl:HumanOwner",
    "aesl:CodingAgent",
]

REQUIRED_SHACL_SNIPPETS = [
    "sh:NodeShape",
    "aesl:DeliveryShape",
    "aesl:InventoryEntryShape",
    "aesl:LocationSlitShape",
    "sh:minCount",
    "aesl:hasTicket",
    "aesl:hasLocationSlit",
    "Do not hand-duplicate",
]

REQUIRED_SHACL_ENUM_SNIPPETS = [
    "sh:in",
    "aesl:DeliveryEnumShape",
    "aesl:InventoryEntryEnumShape",
    "aesl:status",
    "AUTO-GENERATED",
]

REQUIRED_CATALOG_SNIPPETS = [
    "aesl_domain.generated.ttl",
    "aesl_domain.axioms.ttl",
    "http://aes-lighting.internal/logistics",
]


class Failure(Exception):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_deps() -> None:
    missing = []
    for mod in ("rdflib", "pyshacl", "owlrl"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise Failure(
            "missing required ontology deps: "
            + ", ".join(missing)
            + " — install with: pip install -r .specify/scripts/requirements.txt"
        )


def _require_files() -> None:
    missing = [p for p in REQUIRED_FILES if not p.is_file()]
    if missing:
        raise Failure(
            "missing required Spec Kit ontology files:\n  - "
            + "\n  - ".join(str(p.relative_to(ROOT)) for p in missing)
        )


def _require_snippets(path: Path, snippets: list[str], label: str) -> None:
    text = path.read_text(encoding="utf-8")
    absent = [s for s in snippets if s not in text]
    if absent:
        raise Failure(f"{label} missing required markers:\n  - " + "\n  - ".join(absent))


def _parse_turtle(path: Path) -> None:
    from rdflib import Graph

    g = Graph()
    g.parse(path.resolve().as_uri(), format="turtle")


def _check_snapshot_freshness() -> None:
    """Re-run the generator; if it mutates the committed artifacts, fail."""
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    for rel, expected in sorted((snap.get("fileHashes") or {}).items()):
        path = ROOT / rel
        if not path.is_file():
            raise Failure(f"schema snapshot references missing file: {rel}")
        live = _sha256_file(path)
        if live != expected:
            raise Failure(
                f"schema snapshot stale for {rel}: live={live[:12]}… snapshot={expected[:12]}… "
                "run extract_schema_snapshot.py then generate_ontology.py"
            )
    vocab = json.loads(VOCAB_SNAPSHOT.read_text(encoding="utf-8"))
    for rel, expected in sorted((vocab.get("fileHashes") or {}).items()):
        path = ROOT / rel
        if not path.is_file():
            raise Failure(f"status-vocab snapshot references missing file: {rel}")
        live = _sha256_file(path)
        if live != expected:
            raise Failure(
                f"status-vocab snapshot stale for {rel}: "
                f"live={live[:12]}… snapshot={expected[:12]}… "
                "run extract_status_vocabularies.py then generate_ontology.py"
            )

    before_gen = (ONTOLOGY / "aesl_domain.generated.ttl").read_text(encoding="utf-8")
    before_enums = (ONTOLOGY / "aesl_domain.shacl.enums.ttl").read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(GENERATE)], cwd=str(ROOT), capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Failure(f"generate_ontology.py failed:\n{proc.stdout}\n{proc.stderr}")
    after_gen = (ONTOLOGY / "aesl_domain.generated.ttl").read_text(encoding="utf-8")
    after_enums = (ONTOLOGY / "aesl_domain.shacl.enums.ttl").read_text(encoding="utf-8")
    if after_gen != before_gen or after_enums != before_enums:
        raise Failure(
            "generated ontology artifacts drifted from committed files — "
            "commit regenerated TTL/enums after generate_ontology.py"
        )


def _check_coverage() -> None:
    from ontology_entity_coverage import data_model_path, parse_data_model_entities

    dm = data_model_path(ROOT)
    if not dm.is_file():
        raise Failure(f"missing data-model: {dm.relative_to(ROOT)}")
    required, deferred = parse_data_model_entities(dm.read_text(encoding="utf-8"))
    generated = (ONTOLOGY / "aesl_domain.generated.ttl").read_text(encoding="utf-8")
    missing = [
        c for c in required if f"aesl:{c}" not in generated
    ]
    if missing:
        raise Failure("mapped classes missing from generated TTL:\n  - " + "\n  - ".join(missing))
    if not STORE_TO_CLASS:
        raise Failure("STORE_TO_CLASS is empty")
    for store, cls in STORE_TO_CLASS.items():
        if cls is None:
            continue
        if f"aesl:{cls}" not in generated:
            raise Failure(f"store class missing from generated TTL: aesl:{cls}")
    print(
        f"Entity↔TBox coverage: OK (required={len(required)} deferred={len(deferred)})"
    )


def gate_contract() -> None:
    print("=== Spec Kit ontology contract validation ===")
    _require_deps()
    _require_files()
    _require_snippets(ONTOLOGY / "aesl_domain.axioms.ttl", REQUIRED_AXIOM_SNIPPETS, "axioms")
    _require_snippets(ONTOLOGY / "aesl_domain.shacl.ttl", REQUIRED_SHACL_SNIPPETS, "SHACL")
    _require_snippets(
        ONTOLOGY / "aesl_domain.shacl.enums.ttl", REQUIRED_SHACL_ENUM_SNIPPETS, "SHACL enums"
    )
    _require_snippets(ONTOLOGY / "catalog-v001.xml", REQUIRED_CATALOG_SNIPPETS, "catalog")
    for name in (
        "aesl_domain.ttl",
        "aesl_domain.generated.ttl",
        "aesl_domain.axioms.ttl",
        "aesl_domain.shacl.ttl",
        "aesl_domain.shacl.enums.ttl",
        "fixtures/phase2-valid.ttl",
    ):
        _parse_turtle(ONTOLOGY / name)
    _check_snapshot_freshness()
    _check_coverage()
    print("Contract gate: OK")


def gate_shacl() -> None:
    print("=== SHACL instance validation ===")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_instances.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise Failure(proc.stderr or proc.stdout or "SHACL gate failed")
    print("SHACL gate: OK")


def gate_owl() -> None:
    print("=== OWL-RL TBox consistency ===")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_owl.py")],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        raise Failure(proc.stderr or proc.stdout or "OWL-RL gate failed")
    print("OWL-RL gate: OK")


def main() -> int:
    try:
        gate_contract()
        gate_shacl()
        gate_owl()
    except Failure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print()
    print("All Spec Kit ontology gates passed (Phase 2/3 closure).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())