"""Run the shared SQL on FHIR v2 conformance suite against kindling-sof."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from kindling_sof import View, ViewDefinitionError

SUITE = Path(__file__).parent / "conformance"


def _cases() -> list[Any]:
    cases = []
    for f in sorted(SUITE.glob("*.json")):
        suite = json.loads(f.read_text(), parse_float=Decimal)
        for t in suite["tests"]:
            cases.append(pytest.param(suite["resources"], t, id=f"{f.stem}::{t['title']}"))
    return cases


def _canon(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, list):
        return [_canon(x) for x in v]
    return v


def _key(row: dict[str, Any]) -> str:
    return json.dumps({k: _canon(v) for k, v in sorted(row.items())}, sort_keys=True, default=str)


@pytest.mark.parametrize(("resources", "case"), _cases())
def test_conformance(resources: list[dict[str, Any]], case: dict[str, Any]) -> None:
    if case.get("expectError"):
        with pytest.raises(ViewDefinitionError):
            list(View(case["view"]).rows(resources))
        return
    view = View(case["view"])
    rows = list(view.rows(resources))
    if "expectColumns" in case:
        assert view.column_names == case["expectColumns"]
    if "expect" in case:
        got = sorted(_key(r) for r in rows)
        want = sorted(_key(r) for r in case["expect"])
        assert got == want
