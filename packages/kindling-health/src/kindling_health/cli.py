"""``kindling``: stand up the reference stack and run the zero-to-dashboard pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__, pipeline
from .config import Settings

PROFILES = ("core", "analytics", "quality", "full")


def _settings(args: argparse.Namespace) -> Settings:
    kw = {}
    for name in ("patients", "seed", "state", "fhir_url", "concurrency", "reference_date"):
        v = getattr(args, name, None)
        if v is not None:
            kw[name] = v
    if getattr(args, "data_dir", None):
        kw["data_dir"] = Path(args.data_dir)
    return Settings(**kw)


def _compose(s: Settings, *args: str) -> int:
    if not s.compose_file.exists():
        print(f"error: {s.compose_file} not found; run from a Kindling checkout", file=sys.stderr)
        return 2
    return subprocess.call(["docker", "compose", "-f", str(s.compose_file), *args])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kindling", description=__doc__)
    parser.add_argument("--version", action="version", version=f"kindling {__version__}")
    parser.add_argument("--data-dir", help="Where generated data and the warehouse live (default: .kindling)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("up", help="Start the reference stack with docker compose")
    up.add_argument("--profile", choices=PROFILES, default="core")
    down = sub.add_parser("down", help="Stop the reference stack")
    down.add_argument("--volumes", action="store_true", help="Also delete the FHIR database volume")

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--patients", type=int, help="Living patients to generate (default 100)")
        p.add_argument("--seed", type=int, help="Synthea seed (default 42)")
        p.add_argument("--state", help="US state for Synthea (default Massachusetts)")
        p.add_argument("--reference-date", help="Synthea reference date (default 2026-01-01)")
        p.add_argument("--fhir-url", help="FHIR base URL (default http://localhost:8080/fhir)")
        p.add_argument("--concurrency", type=int, help="Parallel bundle uploads (default 4)")

    run = sub.add_parser("run", help="Run the whole pipeline, or selected steps")
    add_common(run)
    run.add_argument(
        "steps", nargs="*", help=f"Steps to run, in order (default: all of {', '.join(pipeline.STEPS)})"
    )
    run.add_argument("--report", help="Write the pipeline report JSON here")

    step_help = {
        "generate": "Generate synthetic patients with Synthea",
        "load": "Load Synthea bundles into the FHIR server",
        "export": "Bulk-export everything from the FHIR server as NDJSON",
        "flatten": "Flatten NDJSON into DuckDB tables with SQL on FHIR views",
        "tuva-assets": "Download Tuva's terminology files to a local mirror",
        "transform": "Map FHIR tables to Tuva's input layer and run Tuva (dbt)",
    }
    for name in pipeline.STEPS:
        add_common(sub.add_parser(name, help=step_help[name]))

    sub.add_parser("summary", help="Print headline numbers from the warehouse")

    args = parser.parse_args(argv)
    s = _settings(args)

    if args.cmd == "up":
        return _compose(s, "--profile", args.profile, "up", "-d")
    if args.cmd == "down":
        return _compose(s, "--profile", "full", "down", *(["--volumes"] if args.volumes else []))
    if args.cmd == "summary":
        print(json.dumps(pipeline.summarize(s, log=lambda m: None), indent=2, default=str))
        return 0
    if args.cmd == "run":
        unknown = [x for x in args.steps if x not in pipeline.STEPS]
        if unknown:
            parser.error(f"unknown step(s) {unknown}; choose from {list(pipeline.STEPS)}")
        report = pipeline.run_pipeline(
            s, steps=args.steps or None, report_path=Path(args.report) if args.report else None
        )
        total = sum(step.seconds for step in report.steps)
        print(f"\nDone in {total / 60:.1f} min. Report: {args.report or s.data / 'pipeline-report.json'}")
        return 0
    pipeline.STEPS[args.cmd](s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
