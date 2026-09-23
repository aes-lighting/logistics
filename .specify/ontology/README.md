# AES Logistics Domain Ontology — Spec Kit

**Namespace:** `http://aes-lighting.internal/logistics#` · **prefix:** `aesl:`
**Version:** 0.1.0 · **Status:** Phase 2 (baseline axioms + SHACL + closed vocabularies)

This is the **neurosymbolic contract** for the AES Logistics Spec Kit. It is a
JSON-driven domain ontology: the "schema" is not SQL — it is the two mutable
stores and their code constants. The single source of semantic truth is:

- `specs/001-server/data-model.md` — authoritative record shapes (the JSON schema).
- `server/scheduling.py` — delivery lifecycle, ticket-source, reminder semantics.
- `server/inventory.py` — `LOCATIONS`, incoming-entry semantics, job→PM directory.
- `.specify/ontology/` — the OWL/SHACL projection of that contract.

The OWL/SHACL layer **does not replace** the code. It *reflects*, *gates*, and
*groom* the contract so that scenarios like a driver being visible before
packing, a pallet split summing to the wrong count, or a rolled-back ticket
staying packed are caught **at contract time**, not by a field operator.

## Neurosymbolic ownership (who decides what)

| Concern | Owned by |
|---|---|
| Record shape, status transitions, storage, file layout | code (as at HEAD) |
| Instance existence, types, closed enums | SHACL shapes + `validate_instances.py` |
| TBox consistency (disjointness, functional props) | OWL-RL via `validate_owl.py` |
| Access control, "who can see what" at runtime | auth layer + `deliveries_assigned_to` |
| Schema drift (data-model.md vs code) | snapshot freshness gates |

## Phase map (mirrors iv-org pattern)

- **Phase 0** — foundation: namespace, ordering, neurosymbolic boundary.
- **Phase 1** — generated structural TBox (classes + data props from the two stores).
- **Phase 2** — curated axioms (disjointness, functional props, lifecycle) + curated SHACL.
- **Phase 3** — closed vocabularies (status, ticket-source, removed-reason, 13 locations) as blocking sh:in.
- **Phase 4** — absent for now (no graph-edge set beyond delivery→ticket/line-item; add when the PM-portal/inventory/scheduling edges are reconciled).
- **No Phase 9** in this repository — policy `aesl:PolicyNoOntologyPhase9`.

## Layout & commands

```
.specify/ontology/
  README.md          ← this file
  aesl_domain.ttl             thin catalog (imports generated + axioms)
  aesl_domain.generated.ttl   AUTO-GENERATED structural TBox (+ same-file enums)
  aesl_domain.axioms.ttl      curated axioms + lifecycle
  aesl_domain.shacl.ttl       curated SHACL shapes
  aesl_domain.shacl.enums.ttl AUTO-GENERATED closed sh:in lists
  catalog-v001.xml           Protégé / tooling catalog
  residuals.md               accepted residuals + parked work
  snapshots/                 regenerated freshness + coverage snapshots
  fixtures/phase2-valid.ttl  SHACL-positive instance set
.specify/scripts/
  extract_schema_snapshot.py      builds schema.snapshot.json (+ freshness)
  extract_status_vocabularies.py  builds status-vocab.snapshot.json
  extract_entity_coverage.py      builds entity-coverage.snapshot.json
  generate_ontology.py            emits generated.ttl + shacl.enums.ttl
  validate_instances.py           SHACL gate
  validate_owl.py                 OWL-RL TBox gate
  validate_spec.py                contract + SHACL + OWL-RL (run this)
  run_validate_spec.sh            venv-aware wrapper
  requirements.txt                rdflib / pyshacl / owlrl
```

```bash
.specify/scripts/run_validate_spec.sh          # all three gates
# iterate after schema/code change:
python3 .specify/scripts/extract_schema_snapshot.py
python3 .specify/scripts/extract_status_vocabularies.py
python3 .specify/scripts/generate_ontology.py
```

## Principles

1. **HEAD is truth.** If the code changes, snapshots/generated TTL must be
   regenerated; the freshness gate fails otherwise. README is never ground truth.
2. **Generated ≠ curated, and the file-name suffix enforces it.** Never hand-edit
   `*.generated.ttl` or `*.shacl.enums.ttl`; both carry `AUTO-GENERATED` markers.
3. **enums live in the generator, never duplicated by hand in curated SHACL.**
4. **Foreign keys become object properties; data columns become data properties.**
   Here the JSON stores are the "columns"; record-to-record links (delivery→ticket,
   delivery→line-items, entry→location) are object properties.
5. **Closed vocabularies are `intentional_closed_set`s** — every enum value has
   provenance to a live source file+line, so a deleted location or a new status
   triggers a visible stale snapshot instead of silent drift.
6. **Blocking > warning.** Every shape here is severity = Violation by default.
7. **No invented IDs.** Instance projections use the store's real UUID carries
   (`id` key). Coverage maps by store key, not by synthetic identity.