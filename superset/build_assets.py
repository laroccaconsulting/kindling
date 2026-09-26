"""Generate Kindling's Superset dashboards as an import bundle (dashboards as code).

    uv run python superset/build_assets.py   # rewrites superset/assets/kindling/

Datasets are virtual (SQL) datasets over the DuckDB warehouse; charts and the dashboard
layout are defined below. UUIDs are derived from names, so regenerating is stable and
diffs stay readable. The container imports the bundle on start (entrypoint.sh).
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

import yaml

OUT = Path(__file__).parent / "assets" / "kindling"
NS = uuid.UUID("7f3c2a4e-6b1d-4e0a-9c55-6b696e646c69")  # "kindling" namespace


def uid(kind: str, name: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{name}"))


DB_NAME = "Kindling warehouse (DuckDB)"
DB_UUID = uid("database", DB_NAME)

# name → (description, SQL, {column: type}, datetime column or None)
DATASETS: dict[str, tuple[str, str, dict[str, str], str | None]] = {
    "patients": (
        "One row per person (Tuva core.patient).",
        "select person_id, sex, race, ethnicity, age, age_group, death_flag, state from core.patient",
        {
            "person_id": "VARCHAR",
            "sex": "VARCHAR",
            "race": "VARCHAR",
            "ethnicity": "VARCHAR",
            "age": "INTEGER",
            "age_group": "VARCHAR",
            "death_flag": "INTEGER",
            "state": "VARCHAR",
        },
        None,
    ),
    "medical_claims": (
        "Medical claim lines with Tuva service categories.",
        "select claim_id, person_id, claim_type, payer, service_category_1, service_category_2, "
        "encounter_type, claim_start_date, paid_amount, allowed_amount from core.medical_claim",
        {
            "claim_id": "VARCHAR",
            "person_id": "VARCHAR",
            "claim_type": "VARCHAR",
            "payer": "VARCHAR",
            "service_category_1": "VARCHAR",
            "service_category_2": "VARCHAR",
            "encounter_type": "VARCHAR",
            "claim_start_date": "DATE",
            "paid_amount": "DOUBLE",
            "allowed_amount": "DOUBLE",
        },
        "claim_start_date",
    ),
    "pmpm": (
        "Medical paid per member per month by year (2016-2025).",
        "with mm as (select substr(year_month, 1, 4) as year, count(*) as member_months "
        "from core.member_month group by 1), "
        "paid as (select cast(year(claim_start_date) as varchar) as year, sum(paid_amount) as paid "
        "from core.medical_claim group by 1) "
        "select mm.year, mm.member_months, coalesce(paid.paid, 0) as paid, "
        "coalesce(paid.paid, 0) / mm.member_months as pmpm "
        "from mm left join paid on mm.year = paid.year where mm.year between '2016' and '2025'",
        {"year": "VARCHAR", "member_months": "BIGINT", "paid": "DOUBLE", "pmpm": "DOUBLE"},
        None,
    ),
    "encounters": (
        "Encounters (clinical and claims-derived) from Tuva core.encounter.",
        "select encounter_id, person_id, encounter_type, encounter_group, encounter_start_date, "
        "length_of_stay, paid_amount from core.encounter",
        {
            "encounter_id": "VARCHAR",
            "person_id": "VARCHAR",
            "encounter_type": "VARCHAR",
            "encounter_group": "VARCHAR",
            "encounter_start_date": "DATE",
            "length_of_stay": "INTEGER",
            "paid_amount": "DOUBLE",
        },
        "encounter_start_date",
    ),
    "conditions": (
        "Conditions grouped by Tuva's condition grouper.",
        "select person_id, condition_family, condition_name from core.condition where condition_name is not null",
        {"person_id": "VARCHAR", "condition_family": "VARCHAR", "condition_name": "VARCHAR"},
        None,
    ),
    "quality_measures": (
        "Tuva quality measure results (quality_measures.summary_counts).",
        "select measure_id, measure_name, performance_period_end, denominator_sum as denominator, "
        "numerator_sum as numerator, exclusion_sum as exclusions, performance_rate "
        "from quality_measures.summary_counts",
        {
            "measure_id": "VARCHAR",
            "measure_name": "VARCHAR",
            "performance_period_end": "DATE",
            "denominator": "BIGINT",
            "numerator": "BIGINT",
            "exclusions": "BIGINT",
            "performance_rate": "DOUBLE",
        },
        None,
    ),
}


def metric(sql: str, label: str) -> dict[str, Any]:
    return {
        "expressionType": "SQL",
        "sqlExpression": sql,
        "label": label,
        "hasCustomLabel": True,
        "optionName": "metric_" + uid("metric", label).replace("-", "")[:12],
    }


PATIENTS = metric("COUNT(DISTINCT person_id)", "Patients")
PAID = metric("SUM(paid_amount)", "Paid")
ENCOUNTERS = metric("COUNT(*)", "Encounters")
PMPM = metric("SUM(paid) / SUM(member_months)", "PMPM")


def big_number(metric_: dict[str, Any], fmt: str = "SMART_NUMBER") -> dict[str, Any]:
    return {
        "viz_type": "big_number_total",
        "metric": metric_,
        "adhoc_filters": [],
        "header_font_size": 0.4,
        "subheader_font_size": 0.15,
        "y_axis_format": fmt,
    }


def bar(
    x: str,
    metric_: dict[str, Any],
    *,
    limit: int = 15,
    horizontal: bool = False,
    fmt: str = "SMART_NUMBER",
    sort_by_value: bool = True,
) -> dict[str, Any]:
    return {
        "viz_type": "echarts_timeseries_bar",
        "x_axis": x,
        "metrics": [metric_],
        "groupby": [],
        "adhoc_filters": [],
        "row_limit": limit,
        "order_desc": True,
        "truncate_metric": True,
        "show_legend": False,
        "orientation": "horizontal" if horizontal else "vertical",
        "x_axis_sort": metric_["label"] if sort_by_value else x,
        "x_axis_sort_asc": not sort_by_value,
        "y_axis_format": fmt,
        "rich_tooltip": True,
        "show_value": True,
    }


def pie(groupby: str, metric_: dict[str, Any]) -> dict[str, Any]:
    return {
        "viz_type": "pie",
        "groupby": [groupby],
        "metric": metric_,
        "adhoc_filters": [],
        "row_limit": 20,
        "donut": True,
        "show_labels": True,
        "label_type": "key_percent",
        "show_legend": False,
        "sort_by_metric": True,
    }


def table(columns: list[str]) -> dict[str, Any]:
    return {
        "viz_type": "table",
        "query_mode": "raw",
        "all_columns": columns,
        "adhoc_filters": [],
        "order_by_cols": [],
        "row_limit": 100,
        "server_page_length": 10,
        "include_search": False,
    }


# name → (dataset, params, width in grid units of 12, height)
CHARTS: dict[str, tuple[str, dict[str, Any], int, int]] = {
    "Patients": ("patients", big_number(PATIENTS), 3, 25),
    "Medical paid": ("medical_claims", big_number(PAID, "$,.0f"), 3, 25),
    "Encounters": ("encounters", big_number(ENCOUNTERS), 3, 25),
    "Average PMPM (2016-2025)": ("pmpm", big_number(PMPM, "$,.0f"), 3, 25),
    "Medical PMPM by year": ("pmpm", bar("year", PMPM, limit=20, fmt="$,.0f", sort_by_value=False), 6, 50),
    "Paid by service category": (
        "medical_claims",
        bar("service_category_2", PAID, horizontal=True, fmt="$,.0f"),
        6,
        50,
    ),
    "Patients by age group": ("patients", bar("age_group", PATIENTS, sort_by_value=False), 4, 50),
    "Patients by sex": ("patients", pie("sex", PATIENTS), 4, 50),
    "Patients by race": ("patients", pie("race", PATIENTS), 4, 50),
    "Encounters by type": ("encounters", bar("encounter_type", ENCOUNTERS, horizontal=True), 6, 50),
    "Most common condition groups": ("conditions", bar("condition_name", PATIENTS, horizontal=True), 6, 50),
    "Quality measures (Tuva)": (
        "quality_measures",
        table(["measure_id", "measure_name", "denominator", "numerator", "exclusions", "performance_rate"]),
        12,
        40,
    ),
}

ROWS = [
    ["Patients", "Medical paid", "Encounters", "Average PMPM (2016-2025)"],
    ["Medical PMPM by year", "Paid by service category"],
    ["Patients by age group", "Patients by sex", "Patients by race"],
    ["Encounters by type", "Most common condition groups"],
    ["Quality measures (Tuva)"],
]

DASHBOARD = "Kindling: population overview"


def write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    write(
        OUT / "metadata.yaml",
        {"version": "1.0.0", "type": "Dashboard", "timestamp": "2026-01-01T00:00:00+00:00"},
    )
    write(
        OUT / "databases" / "kindling_warehouse.yaml",
        {
            "database_name": DB_NAME,
            "sqlalchemy_uri": "duckdb:////data/kindling.duckdb",
            "cache_timeout": None,
            "expose_in_sqllab": True,
            "allow_run_async": False,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
            "allow_file_upload": False,
            "extra": {
                "allows_virtual_table_explore": True,
                "engine_params": {"connect_args": {"read_only": True}},
            },
            "uuid": DB_UUID,
            "version": "1.0.0",
        },
    )
    for name, (desc, sql, cols, dttm) in DATASETS.items():
        write(
            OUT / "datasets" / "kindling_warehouse" / f"{name}.yaml",
            {
                "table_name": name,
                "main_dttm_col": dttm,
                "description": desc,
                "default_endpoint": None,
                "offset": 0,
                "cache_timeout": None,
                "schema": "main",
                "sql": sql,
                "params": None,
                "template_params": None,
                "filter_select_enabled": True,
                "fetch_values_predicate": None,
                "extra": None,
                "normalize_columns": False,
                "always_filter_main_dttm": False,
                "uuid": uid("dataset", name),
                "metrics": [
                    {
                        "metric_name": "count",
                        "verbose_name": "COUNT(*)",
                        "metric_type": "count",
                        "expression": "COUNT(*)",
                        "description": None,
                        "d3format": None,
                        "currency": None,
                        "extra": {"warning_markdown": ""},
                        "warning_text": None,
                    }
                ],
                "columns": [
                    {
                        "column_name": c,
                        "verbose_name": None,
                        "is_dttm": c == dttm or t == "DATE",
                        "is_active": True,
                        "type": t,
                        "advanced_data_type": None,
                        "groupby": True,
                        "filterable": True,
                        "expression": None,
                        "description": None,
                        "python_date_format": None,
                        "extra": {},
                    }
                    for c, t in cols.items()
                ],
                "version": "1.0.0",
                "database_uuid": DB_UUID,
            },
        )
    for name, (ds, params, _w, _h) in CHARTS.items():
        slug = name.lower().replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_")
        write(
            OUT / "charts" / f"{slug}.yaml",
            {
                "slice_name": name,
                "description": None,
                "certified_by": None,
                "certification_details": None,
                "viz_type": params["viz_type"],
                "params": {**params, "datasource": f"{ds}__table"},
                "query_context": None,
                "cache_timeout": None,
                "uuid": uid("chart", name),
                "version": "1.0.0",
                "dataset_uuid": uid("dataset", ds),
            },
        )

    position: dict[str, Any] = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
        "HEADER_ID": {"id": "HEADER_ID", "meta": {"text": DASHBOARD}, "type": "HEADER"},
        "GRID_ID": {"children": [], "id": "GRID_ID", "parents": ["ROOT_ID"], "type": "GRID"},
    }
    for i, row in enumerate(ROWS, 1):
        row_id = f"ROW-{i}"
        position["GRID_ID"]["children"].append(row_id)
        position[row_id] = {
            "children": [],
            "id": row_id,
            "meta": {"background": "BACKGROUND_TRANSPARENT"},
            "parents": ["ROOT_ID", "GRID_ID"],
            "type": "ROW",
        }
        for name in row:
            _ds, _p, width, height = CHARTS[name]
            chart_id = f"CHART-{uid('pos', name)[:8]}"
            position[row_id]["children"].append(chart_id)
            position[chart_id] = {
                "children": [],
                "id": chart_id,
                "parents": ["ROOT_ID", "GRID_ID", row_id],
                "type": "CHART",
                "meta": {
                    "chartId": 0,
                    "height": height,
                    "width": width,
                    "sliceName": name,
                    "uuid": uid("chart", name),
                },
            }
    write(
        OUT / "dashboards" / "kindling_population_overview.yaml",
        {
            "dashboard_title": DASHBOARD,
            "description": None,
            "css": "",
            "slug": "kindling-overview",
            "certified_by": None,
            "certification_details": None,
            "published": True,
            "uuid": uid("dashboard", DASHBOARD),
            "position": position,
            "metadata": {
                "color_scheme": "supersetColors",
                "refresh_frequency": 0,
                "expanded_slices": {},
                "label_colors": {},
                "timed_refresh_immune_slices": [],
                "cross_filters_enabled": True,
                "native_filter_configuration": [],
                "shared_label_colors": [],
                "color_scheme_domain": [],
            },
            "version": "1.0.0",
        },
    )
    print(f"Wrote {sum(1 for _ in OUT.rglob('*.yaml'))} files to {OUT}")


if __name__ == "__main__":
    main()
