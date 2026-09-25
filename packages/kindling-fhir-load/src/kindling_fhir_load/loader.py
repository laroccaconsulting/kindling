"""Load FHIR transaction bundles into any FHIR R4 server, in the right order."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

FHIR_JSON = "application/fhir+json"
_RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
_INFO_PREFIXES = ("hospitalInformation", "practitionerInformation")


class LoadError(RuntimeError):
    pass


@dataclass
class BundleResult:
    path: Path
    ok: bool
    resources: int = 0
    seconds: float = 0.0
    error: str | None = None


@dataclass
class LoadReport:
    results: list[BundleResult] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def bundles(self) -> int:
        return len(self.results)

    @property
    def failed(self) -> list[BundleResult]:
        return [r for r in self.results if not r.ok]

    @property
    def resources(self) -> int:
        return sum(r.resources for r in self.results)

    def summary(self) -> str:
        rate = self.resources / self.seconds if self.seconds else 0.0
        return (
            f"{self.bundles - len(self.failed)}/{self.bundles} bundles, {self.resources:,} resources "
            f"in {self.seconds:.1f}s ({rate:,.0f} resources/s)"
        )


def order_bundles(paths: Iterable[Path]) -> tuple[list[Path], list[Path]]:
    """Split into (info bundles, patient bundles).

    Synthea patient bundles point at Practitioners, Organizations and Locations with
    conditional references (``Practitioner?identifier=...``), so the shared
    ``hospitalInformation*``/``practitionerInformation*`` bundles must be loaded first.
    """
    info: list[Path] = []
    patients: list[Path] = []
    for p in sorted(Path(x) for x in paths):
        (info if p.name.startswith(_INFO_PREFIXES) else patients).append(p)
    # Organizations/Locations before Practitioners (PractitionerRole references both).
    info.sort(key=lambda p: (not p.name.startswith("hospitalInformation"), p.name))
    return info, patients


def wait_for_server(base_url: str, timeout: float = 300.0, client: httpx.Client | None = None) -> None:
    """Block until ``{base_url}/metadata`` answers 200."""
    c = client or httpx.Client(timeout=10.0)
    deadline = time.monotonic() + timeout
    last: str = ""
    try:
        while time.monotonic() < deadline:
            try:
                r = c.get(f"{base_url.rstrip('/')}/metadata", headers={"Accept": FHIR_JSON})
                if r.status_code == 200:
                    return
                last = f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                last = str(e) or type(e).__name__
            time.sleep(2.0)
    finally:
        if client is None:
            c.close()
    raise LoadError(f"FHIR server at {base_url} not ready after {timeout:.0f}s ({last})")


class Loader:
    """Posts bundles to a FHIR server with retries and bounded concurrency."""

    def __init__(
        self,
        base_url: str,
        *,
        concurrency: int = 4,
        timeout: float = 600.0,
        retries: int = 4,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.concurrency = max(1, concurrency)
        self.retries = retries
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=30.0),
            headers={"Content-Type": FHIR_JSON, "Accept": FHIR_JSON, **(headers or {})},
            limits=httpx.Limits(max_connections=self.concurrency * 2),
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> Loader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def post_bundle(self, path: Path) -> BundleResult:
        body = path.read_bytes()
        start = time.monotonic()
        error = ""
        for attempt in range(self.retries + 1):
            try:
                r = self.client.post(self.base_url, content=body)
            except httpx.TransportError as e:
                error = f"{type(e).__name__}: {e}"
            else:
                if r.status_code < 300:
                    return BundleResult(path, True, _count_entries(r), time.monotonic() - start)
                error = f"HTTP {r.status_code}: {_outcome_text(r)}"
                if r.status_code not in _RETRY_STATUS:
                    break
            if attempt < self.retries:
                time.sleep(min(2**attempt, 30))
        return BundleResult(path, False, 0, time.monotonic() - start, error)

    def load(
        self,
        paths: Sequence[Path | str],
        *,
        on_result: Callable[[BundleResult], None] | None = None,
        fail_fast: bool = False,
    ) -> LoadReport:
        info, patients = order_bundles(Path(p) for p in paths)
        report = LoadReport()
        start = time.monotonic()

        def record(res: BundleResult) -> None:
            report.results.append(res)
            if on_result:
                on_result(res)
            if not res.ok:
                log.warning("Failed to load %s: %s", res.path.name, res.error)
                if fail_fast:
                    raise LoadError(f"{res.path.name}: {res.error}")

        for p in info:  # sequential: later bundles depend on these
            record(self.post_bundle(p))
        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = [pool.submit(self.post_bundle, p) for p in patients]
            for fut in as_completed(futures):
                record(fut.result())
        report.seconds = time.monotonic() - start
        return report


def load_bundles(
    paths: Sequence[Path | str],
    base_url: str,
    *,
    concurrency: int = 4,
    headers: dict[str, str] | None = None,
    on_result: Callable[[BundleResult], None] | None = None,
    fail_fast: bool = False,
) -> LoadReport:
    """Load Synthea-style transaction bundles into ``base_url``."""
    with Loader(base_url, concurrency=concurrency, headers=headers) as loader:
        return loader.load(paths, on_result=on_result, fail_fast=fail_fast)


def _count_entries(r: httpx.Response) -> int:
    try:
        return len(r.json().get("entry") or [])
    except (json.JSONDecodeError, ValueError, AttributeError):
        return 0


def _outcome_text(r: httpx.Response) -> str:
    try:
        issues = r.json().get("issue") or []
        return "; ".join(i.get("diagnostics") or i.get("details", {}).get("text", "") for i in issues)[:500]
    except (json.JSONDecodeError, ValueError, AttributeError):
        return r.text[:500]
