"""The "zero to dashboard" pipeline:

    Synthea → FHIR server (HAPI) → Bulk $export → SQL on FHIR views → DuckDB → Tuva (dbt)

Each step is a plain function taking :class:`Settings`, so steps can be run one at a
time from the CLI or chained by :func:`run_pipeline`.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import Settings

Log = Callable[[str], None]


def _print(msg: str) -> None:
    print(msg, flush=True)


@dataclass
class StepResult:
    name: str
    seconds: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineReport:
    settings: dict[str, Any]
    steps: list[StepResult] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str) + "\n")


# -- steps ---------------------------------------------------------------------------


def generate(s: Settings, log: Log = _print) -> dict[str, Any]:
    from kindling_synthea import generate as synthea_generate

    log(f"Generating {s.patients} patients with Synthea (seed {s.seed})…")
    result = synthea_generate(
        population=s.patients,
        seed=s.seed,
        out_dir=s.synthea_dir,
        state=s.state,
        reference_date=s.reference_date,
    )
    log(f"  {len(result.patient_bundles)} patient bundles, {len(result.info_bundles)} provider bundles")
    return {"patient_bundles": len(result.patient_bundles), "synthea_version": result.version}


def load(s: Settings, log: Log = _print) -> dict[str, Any]:
    from kindling_fhir_load import load_bundles, wait_for_server

    fhir_dir = s.synthea_dir / "fhir"
    bundles = sorted(fhir_dir.glob("*.json"))
    if not bundles:
        raise SystemExit(f"No bundles in {fhir_dir}; run `kindling generate` first")
    log(f"Waiting for FHIR server at {s.fhir_url}…")
    wait_for_server(s.fhir_url)
    done = {"n": 0}

    def progress(r: Any) -> None:
        done["n"] += 1
        if done["n"] % 25 == 0 or done["n"] == len(bundles):
            log(f"  {done['n']}/{len(bundles)} bundles")

    log(f"Loading {len(bundles)} bundles…")
    report = load_bundles(bundles, s.fhir_url, concurrency=s.concurrency, on_result=progress)
    log(f"  {report.summary()}")
    if report.failed:
        for f in report.failed[:5]:
            log(f"  FAILED {f.path.name}: {f.error}")
        raise SystemExit(f"{len(report.failed)} bundles failed to load")
    return {
        "bundles": report.bundles,
        "resources": report.resources,
        "resources_per_second": round(report.resources / max(report.seconds, 1e-9)),
    }


def export(s: Settings, log: Log = _print) -> dict[str, Any]:
    from kindling_bulk import bulk_export

    log(f"Running Bulk Data $export from {s.fhir_url}…")
    result = bulk_export(s.fhir_url, s.bulk_dir)
    log(f"  {result.summary()}")
    return {"files": len(result.files), "types": sorted(result.by_type())}


def flatten(s: Settings, log: Log = _print) -> dict[str, Any]:
    from kindling_sof import runner

    s.warehouse.parent.mkdir(parents=True, exist_ok=True)
    log(f"Flattening FHIR with SQL on FHIR views into {s.warehouse}…")
    report = runner.run_views(runner.bundled_views("us_core"), s.bulk_dir, duckdb=s.warehouse, schema="fhir")
    log(f"  {report.summary()}")
    return {"rows": {v.name: v.rows for v in report.views}, "resources": report.resources}


def tuva_assets(s: Settings, log: Log = _print) -> dict[str, Any]:
    from .tuva_assets import mirror

    log(f"Mirroring Tuva terminology into {s.tuva_assets} (cached after the first run)…")
    n = {"files": 0}

    def on_file(key: str, size: int, stub: bool) -> None:
        n["files"] += 1

    mirror(s.tuva_assets, on_file=on_file)
    log(f"  {n['files']} files downloaded")
    return {"downloaded": n["files"]}


def _dbt(s: Settings, args: list[str], log: Log) -> None:
    env = {
        **os.environ,
        "KINDLING_DUCKDB": str(s.warehouse),
        "KINDLING_TUVA_ASSETS": str(s.tuva_assets),
        "DBT_PROFILES_DIR": str(s.dbt_dir),
    }
    local = Path(sys.executable).with_name("dbt")
    exe = str(local) if local.exists() else shutil.which("dbt")
    if exe is None:
        raise SystemExit(
            "dbt is not installed. Use `uv sync --group dbt` in a checkout, or `pip install 'kindling-health[dbt]'`."
        )
    log(f"  $ dbt {' '.join(args)}")
    proc = subprocess.run([exe, *args], cwd=s.dbt_dir, env=env, check=False)
    if proc.returncode != 0:
        raise SystemExit(f"dbt {args[0]} failed with exit code {proc.returncode}")


def transform(s: Settings, log: Log = _print, deps: bool = True) -> dict[str, Any]:
    log("Running Tuva with dbt…")
    if deps and os.environ.get("KINDLING_DBT_SKIP_DEPS") != "1":
        _dbt(s, ["deps"], log)
    _dbt(s, ["build", "--exclude", "test_type:data"], log)
    return {}


def summarize(s: Settings, log: Log = _print) -> dict[str, Any]:
    import duckdb

    con = duckdb.connect(str(s.warehouse), read_only=True)

    def scalar(sql: str) -> Any:
        try:
            return con.execute(sql).fetchone()[0]  # type: ignore[index]
        except duckdb.Error:
            return None

    summary: dict[str, Any] = {
        "patients": scalar("select count(*) from core.patient"),
        "encounters": scalar("select count(*) from core.encounter"),
        "medical_claim_lines": scalar("select count(*) from core.medical_claim"),
        "pharmacy_claim_lines": scalar("select count(*) from core.pharmacy_claim"),
        "paid_amount": scalar("select round(sum(paid_amount), 2) from core.medical_claim"),
    }
    try:
        rows = con.execute(
            "select measure_id, measure_name, denominator_sum, numerator_sum, exclusion_sum, performance_rate "
            "from quality_measures.summary_counts order by measure_id"
        ).fetchall()
        summary["quality_measures"] = [
            dict(
                zip(["measure_id", "name", "denominator", "numerator", "exclusions", "rate"], r, strict=True)
            )
            for r in rows
        ]
    except duckdb.Error:
        summary["quality_measures"] = []
    con.close()
    log(
        f"  {summary['patients']} patients, {summary['encounters']} encounters, "
        f"{summary['medical_claim_lines']} medical claim lines, {len(summary['quality_measures'])} quality measures"
    )
    return summary


STEPS: dict[str, Callable[..., dict[str, Any]]] = {
    "generate": generate,
    "load": load,
    "export": export,
    "flatten": flatten,
    "tuva-assets": tuva_assets,
    "transform": transform,
}


def run_pipeline(
    s: Settings,
    steps: list[str] | None = None,
    log: Log = _print,
    report_path: Path | None = None,
) -> PipelineReport:
    steps = steps or list(STEPS)
    report = PipelineReport(
        settings={
            "patients": s.patients,
            "seed": s.seed,
            "state": s.state,
            "reference_date": s.reference_date,
            "fhir_url": s.fhir_url,
        }
    )
    for name in steps:
        t0 = time.monotonic()
        log(f"\n▶ {name}")
        detail = STEPS[name](s, log)
        report.steps.append(StepResult(name, round(time.monotonic() - t0, 1), detail))
        log(f"  ✓ {name} in {report.steps[-1].seconds:.1f}s")
    if "transform" in steps:
        log("\n▶ summary")
        report.summary = summarize(s, log)
    report.write(report_path or (s.data / "pipeline-report.json"))
    return report
