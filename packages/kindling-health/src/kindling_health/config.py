"""Paths and settings shared by the CLI and the pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path | None:
    """The Kindling checkout containing ``stack/compose.yaml``, if we're inside one."""
    p = (start or Path.cwd()).resolve()
    for candidate in (p, *p.parents):
        if (candidate / "stack" / "compose.yaml").exists() and (
            candidate / "dbt" / "dbt_project.yml"
        ).exists():
            return candidate
    return None


@dataclass
class Settings:
    root: Path = field(default_factory=lambda: find_repo_root() or Path.cwd())
    data_dir: Path | None = None
    fhir_url: str = field(
        default_factory=lambda: os.environ.get("KINDLING_FHIR_URL", "http://localhost:8080/fhir")
    )
    patients: int = 100
    seed: int = 42
    state: str = "Massachusetts"
    reference_date: str = "2026-01-01"
    concurrency: int = 4

    def __post_init__(self) -> None:
        if self.data_dir is None:
            self.data_dir = Path(os.environ.get("KINDLING_DATA_DIR", self.root / ".kindling"))
        self.data_dir = Path(self.data_dir).resolve()

    @property
    def data(self) -> Path:
        assert self.data_dir is not None
        return self.data_dir

    @property
    def synthea_dir(self) -> Path:
        return self.data / "synthea"

    @property
    def bulk_dir(self) -> Path:
        return self.data / "bulk"

    @property
    def warehouse(self) -> Path:
        return self.data / "warehouse" / "kindling.duckdb"

    @property
    def tuva_assets(self) -> Path:
        return Path(os.environ.get("KINDLING_TUVA_ASSETS", self.data / "tuva-assets"))

    @property
    def dbt_dir(self) -> Path:
        return self.root / "dbt"

    @property
    def compose_file(self) -> Path:
        return self.root / "stack" / "compose.yaml"
