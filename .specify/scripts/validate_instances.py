#!/usr/bin/env python3
"""SHACL instance validation for AES Logistics Spec Kit.

Loads the curated + generated-enum shapes and validates the positive fixture
set (fixtures/phase2-valid.ttl). Deliberately injects a few known-bad triples and
asserts they FAIL, so the gate proves blocking severity rather than tautology.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / ".specify" / "ontology"
SHAPES = [
    ONTOLOGY / "aesl_domain.shacl.ttl",
    ONTOLOGY / "aesl_domain.shacl.enums.ttl",
]
VALID = ONTOLOGY / "fixtures" / "phase2-valid.ttl"


class BlockingFailure(Exception):
    pass


def _graph(path: Path):
    from rdflib import Graph

    g = Graph()
    g.parse(path.resolve().as_uri(), format="turtle")
    return g


def validate():
    from pyshacl import validate as shacl_validate

    data = _graph(VALID).serialize(format="turtle").encode("utf-8")
    shapes = b"\n".join(
        p.read_bytes() for p in SHAPES if p.is_file()
    )
    if not shapes:
        raise BlockingFailure("no SHACL shape files found")
    conforms, results, _ = shacl_validate(
        data,
        shacl_graph=shapes,
        ont_graph=None,
        inference="both",
        meta_shacl=False,
        abort_on_first=False,
        allow_infos=False,
        allow_warnings=False,
    )
    return conforms, results


def positive_fixture_ok(conforms: bool, results_graph=None) -> None:
    if not conforms:
        msg = "positive fixture failed SHACL"
        if results_graph is not None:
            try:
                msg += f"\n{results_graph.decode('utf-8')}"
            except Exception:  # noqa: BLE001
                pass
        raise BlockingFailure(msg)


def deliberate_rejects() -> None:
    from rdflib import Graph, Namespace, RDF, XSD, Literal
    from pyshacl import validate as shacl_validate

    aesl = Namespace("http://aes-lighting.internal/logistics#")
    base = _graph(VALID)

    # Reject 1: delivery with an out-of-vocabulary status.
    bad = Graph(bind_namespaces="rdflib")
    for t in base:
        bad.add(t)
    bad.add((aesl.badDelivery1, RDF.type, aesl.Delivery))
    bad.add((aesl.badDelivery1, aesl.entityId, Literal("aaaaaaaa-bbbb-accc-addd-eeeeeeeeeeee", datatype=XSD.string)))
    bad.add((aesl.badDelivery1, aesl.jobNumber, Literal("9999")))
    bad.add((aesl.badDelivery1, aesl.status, Literal("vanished")))

    shapes = b"\n".join(p.read_bytes() for p in SHAPES if p.is_file())
    conforms, _, _ = shacl_validate(
        bad.serialize(format="turtle").encode("utf-8"), shacl_graph=shapes
    )
    if conforms:
        raise BlockingFailure("expected SHACL to reject out-of-vocabulary status 'vanished'")

    # Reject 2: location slit pointing at an unknown location.
    bad2 = Graph(bind_namespaces="rdflib")
    for t in base:
        bad2.add(t)
    bad2.add((aesl.badLocation1, RDF.type, aesl.LocationSlit))
    bad2.add((aesl.badLocation1, aesl.location, Literal("North Pole")))
    bad2.add((aesl.badLocation1, aesl["count"], Literal(2, datatype=XSD.integer)))

    conforms, _, _ = shacl_validate(
        bad2.serialize(format="turtle").encode("utf-8"), shacl_graph=shapes
    )
    if conforms:
        raise BlockingFailure("expected SHACL to reject unknown storage location")


def main() -> int:
    try:
        conforms, results = validate()
        positive_fixture_ok(conforms, results)
        deliberate_rejects()
        print("SHACL instance validation: OK (positive fixture + 2 deliberate rejects)")
        return 0
    except BlockingFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())