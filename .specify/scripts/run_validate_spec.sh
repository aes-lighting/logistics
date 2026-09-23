#!/usr/bin/env bash
# Run Spec Kit ontology validation with the ontology venv when present.
# Prefer .specify/scripts/.venv; fall back to python3 with deps installed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
VENV_PY="$ROOT/.specify/scripts/.venv/bin/python"
SCRIPT="$ROOT/.specify/scripts/validate_spec.py"

if [[ -x "$VENV_PY" ]]; then
  exec "$VENV_PY" "$SCRIPT" "$@"
fi

if ! python3 -c "import rdflib, pyshacl, owlrl" >/dev/null 2>&1; then
  echo "error: rdflib, pyshacl, and owlrl are required for Spec Kit ontology validation." >&2
  echo "Install with:" >&2
  echo "  python3 -m venv .specify/scripts/.venv" >&2
  echo "  .specify/scripts/.venv/bin/pip install -r .specify/scripts/requirements.txt" >&2
  echo "  .specify/scripts/run_validate_spec.sh" >&2
  echo "or (when not on an externally-managed Python):" >&2
  echo "  pip install -r .specify/scripts/requirements.txt" >&2
  exit 1
fi

exec python3 "$SCRIPT" "$@"