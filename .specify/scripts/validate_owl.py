#!/usr/bin/env python3
"""OWL-RL TBox consistency gate for AES Logistics Spec Kit.

Loads generated TBox + curated axioms, expands with owlrl, then runs
deterministic consistency probes and deliberate fail-closed proofs.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / ".specify" / "ontology"
GENERATED = ONTOLOGY / "aesl_domain.generated.ttl"
AXIOMS = ONTOLOGY / "aesl_domain.axioms.ttl"

AESL = "http://aes-lighting.internal/logistics#"


class BlockingFailure(Exception):
    pass


def load_tbox_graph():
    from rdflib import Graph

    g = Graph()
    for path in (GENERATED, AXIOMS):
        if not path.is_file():
            raise BlockingFailure(f"missing ontology file: {path.relative_to(ROOT)}")
        g.parse(path.resolve().as_uri(), format="turtle")
    return g


def expand_owlrl(g) -> None:
    from owlrl import DeductiveClosure, OWLRL_Semantics

    DeductiveClosure(OWLRL_Semantics).expand(g)


def probe_sameas_differentfrom(g) -> list[str]:
    from rdflib import OWL

    issues = []
    for s, _, o in g.triples((None, OWL.sameAs, None)):
        if (s, OWL.differentFrom, o) in g or (o, OWL.differentFrom, s) in g:
            issues.append(f"sameAs+differentFrom conflict: {s} / {o}")
    return issues


def probe_disjoint_typed_individuals(g) -> list[str]:
    from rdflib import OWL, RDF

    issues = []
    types_by_ind = {}
    for s, _, o in g.triples((None, RDF.type, None)):
        types_by_ind.setdefault(s, set()).add(o)
    disjoint_pairs = set()
    for a, _, b in g.triples((None, OWL.disjointWith, None)):
        disjoint_pairs.add((a, b))
        disjoint_pairs.add((b, a))
    for ind, types in types_by_ind.items():
        typed = list(types)
        for i, t1 in enumerate(typed):
            for t2 in typed[i + 1 :]:
                if (t1, t2) in disjoint_pairs and (t1 != t2):
                    issues.append(f"individual {ind} typed with disjoint classes {t1} and {t2}")
    return issues


def require_markers(g) -> None:
    from rdflib import Namespace, OWL, RDF

    ns = Namespace(AESL)
    for name in ["Delivery", "InventoryEntry", "CalendarEvent", "DeliveryTicket",
                 "LineItem", "LocationSlit", "Geotag", "LogisticsEntity"]:
        if not list(g.triples((ns[name], None, None))):
            raise BlockingFailure(f"missing required class marker: aesl:{name}")


def deliberate_rejects() -> None:
    from rdflib import Graph, Namespace, OWL, RDF
    from owlrl import DeductiveClosure, OWLRL_Semantics

    ns = Namespace(AESL)

    # Disjoint Delivery/InventoryEntry collision (explicit owl:disjointWith).
    g1 = load_tbox_graph()
    g1.add((ns.badEnt, RDF.type, ns.Delivery))
    g1.add((ns.badEnt, RDF.type, ns.InventoryEntry))
    DeductiveClosure(OWLRL_Semantics).expand(g1)
    issues = probe_disjoint_typed_individuals(g1)
    if not issues:
        raise BlockingFailure("expected disjoint Delivery/LineItem collision")

    # sameAs + differentFrom.
    g2 = load_tbox_graph()
    g2.add((ns.Delivery, OWL.sameAs, ns.otherClass))
    g2.add((ns.Delivery, OWL.differentFrom, ns.otherClass))
    DeductiveClosure(OWLRL_Semantics).expand(g2)
    if not probe_sameas_differentfrom(g2):
        raise BlockingFailure("expected sameAs+differentFrom reject")


def main() -> int:
    try:
        g = load_tbox_graph()
        expand_owlrl(g)
        issues = probe_sameas_differentfrom(g) + probe_disjoint_typed_individuals(g)
        if issues:
            raise BlockingFailure("OWL-RL inconsistencies:\n  - " + "\n  - ".join(issues))
        require_markers(g)
        deliberate_rejects()
        print("OWL-RL TBox consistency: OK (probes + deliberate rejects)")
        return 0
    except BlockingFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())