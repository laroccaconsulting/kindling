"""``kindling-sof``: run SQL on FHIR ViewDefinitions from the command line."""

from __future__ import annotations

import argparse
import json
import sys

from .runner import bundled_views, load_views, run_views
from .view import View, ViewDefinitionError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kindling-sof", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="Run ViewDefinitions over NDJSON files")
    run.add_argument("input", help="NDJSON file or directory (e.g. a Bulk Data export)")
    run.add_argument(
        "--views", default="us_core", help="Directory/file of ViewDefinitions, or a bundled set name"
    )
    run.add_argument("--duckdb", help="DuckDB database file to write tables into")
    run.add_argument("--schema", default="fhir", help="DuckDB schema for the tables (default: fhir)")
    run.add_argument("--parquet", help="Directory to write one Parquet file per view")

    check = sub.add_parser("validate", help="Validate ViewDefinition JSON files")
    check.add_argument("paths", nargs="+")

    show = sub.add_parser("eval", help="Evaluate one ViewDefinition over NDJSON and print rows as JSON lines")
    show.add_argument("view")
    show.add_argument("input")
    show.add_argument("--limit", type=int, default=20)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "run":
            if not args.duckdb and not args.parquet:
                parser.error("run needs --duckdb and/or --parquet")
            views = bundled_views(args.views) if "/" not in args.views and "." not in args.views else None
            views = views or load_views(args.views)
            report = run_views(
                views, args.input, duckdb=args.duckdb, schema=args.schema, parquet_dir=args.parquet
            )
            for v in report.views:
                print(f"{v.name:40} {v.rows:>10,} rows")
            print(report.summary())
        elif args.cmd == "validate":
            for p in args.paths:
                for view in load_views(p):
                    print(f"ok  {view.name or view.resource}: {len(view.columns)} columns")
        elif args.cmd == "eval":
            from .runner import iter_ndjson, ndjson_files

            view = View.from_file(args.view)
            for i, row in enumerate(view.rows(iter_ndjson(ndjson_files(args.input)))):
                if i >= args.limit:
                    break
                print(json.dumps(row, default=str))
    except ViewDefinitionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
