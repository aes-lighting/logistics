# Phase 2/3 residuals / won't-dos (not closure blockers)

The AES Logistics ontology Spec Kit program is at **Phase 2/3 closure**. Further
work is maintenance when the JSON data model / store keys / code constants
change — **not a Phase 9.** Policy: `aesl:PolicyNoOntologyPhase9`.

## Accepted residuals

- **Phase 4 (graph edges) is empty** — no rich edge set beyond delivery→ticket,
  delivery→line-item, entry→location-slit yet. This is deliberate: the PM-portal
  / inventory / scheduling route reconciliation (specs 001/005/006 F4) changes the
  edges before they are worth locking. Add Phase 4 after those contracts close.
- **Ad-hoc "New Delivery" flow** entity remains deferred (`ad_hoc_delivery`):
  `/api/upload` now has a handler (files to `organized/` + a per-delivery
  `<id>_metadata.json`, mirrors to the File Service), but there is still no JSON
  store for ad-hoc deliveries, so the entity is not TBox'd yet.
- **OCR extraction outcome** is not an entity (`ocr_extraction`): job/PO numbers
  read off the slip are flattened into the entry; a dedicated extraction class is
  deferred until the OCR path is reconciled.
- **SMS/ETA external results** (`sms_notification`, `maps.get_eta()` dict) stay
  values attached to a delivery, not linked entities. They become classes only if
  they gain their own store.
- **Pallet-split sum invariant** (`sum(LocationSlit.count) == palletCount`) is
  now enforced **server-side** in `POST /api/incoming/finalize` (A3), plus
  client-side in the wizard. The ontology states the invariant; the code gate
  lives in `app.py`.
- **Access control / role gating** is owned by the auth layer + `deliveries_assigned_to`
  (scheduling.py:201); the ontology reflects visibility policy, it does not decide it
  at runtime. Spec 004 is the authority for auth decisions.

## Parked later (explicit non-next)

Each requires Markus approval and a new numbered Spec before implementation.

| Item | When it may start | Policy |
|------|-------------------|--------|
| Phase 4 graph edges | After spec 001/005/006 F4 contract reconciliation closes | `aesl:PolicyNoPhase4BeforeReconcile` |
| Ad-hoc delivery / upload entity | Handler landed 2026-09-23; start when ad-hoc deliveries get a JSON store | `aesl:PolicyAdHocDeferred` |
| OCR extraction entity | Dedicated Spec or promotion in data-model.md | `aesl:PolicyOcrDeferred` |
| SMS/ETA entities | When they gain a store / persisted state | `aesl:PolicySmsEtaDeferred` |
| ~~Pallet-split server-side gate~~ — landed with A3 (`api_incoming_finalize`) | Done | `aesl:PolicyPalletSplitCodeGate` |
| Ontology Phase 9 | Does not exist | `aesl:PolicyNoOntologyPhase9` |

## Hermes / agents

Consume `.specify/spec.md` + `.specify/ontology/` + `validate_spec.py` as the
single contract. Do not invent a second ontology for the frontends or MCP tools.

**An agent must never auto-complete a delivery**, fabricate a signature, photo,
or geotag, or mark inventory removed on its own. That is human-owned work
(`aesl:PolicyNoAutoCompletesDelivery`). The OWL/SHACL layer gates the contract;
the Flask app + frontends + sync scripts remain authoritative at runtime
(`aesl:PolicyOntologyDoesNotReplacePipelines`).