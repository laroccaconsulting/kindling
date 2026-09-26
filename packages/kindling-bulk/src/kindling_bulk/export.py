"""FHIR Bulk Data Access ($export) client.

Implements the async request pattern from the Bulk Data IG: kick off the export, poll
the status URL (honouring ``Retry-After``), then download each NDJSON output file.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode

import httpx

log = logging.getLogger(__name__)


class BulkExportError(RuntimeError):
    pass


@dataclass
class ExportFile:
    type: str
    url: str
    path: Path | None = None
    count: int | None = None


@dataclass
class ExportResult:
    out_dir: Path
    files: list[ExportFile] = field(default_factory=list)
    transaction_time: str | None = None
    seconds: float = 0.0

    def by_type(self) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        for f in self.files:
            if f.path is not None:
                out.setdefault(f.type, []).append(f.path)
        return out

    def summary(self) -> str:
        types = self.by_type()
        return f"{len(self.files)} files, {len(types)} resource types in {self.seconds:.1f}s"


class BulkClient:
    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 300.0,
        client: httpx.Client | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout, connect=30.0), headers=headers or {}, follow_redirects=True
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> BulkClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def kick_off(
        self,
        level: str = "system",
        *,
        group_id: str | None = None,
        types: Sequence[str] | None = None,
        since: str | None = None,
    ) -> str:
        """Start an export and return the content-location (status) URL."""
        if level == "system":
            path = "$export"
        elif level == "patient":
            path = "Patient/$export"
        elif level == "group":
            if not group_id:
                raise BulkExportError("group_id is required for a group-level export")
            path = f"Group/{group_id}/$export"
        else:
            raise BulkExportError(f"Unknown export level {level!r}")
        params: dict[str, str] = {"_outputFormat": "application/fhir+ndjson"}
        if types:
            params["_type"] = ",".join(types)
        if since:
            params["_since"] = since
        url = f"{self.base_url}/{path}?{urlencode(params, safe=',$')}"
        r = self.client.get(url, headers={"Accept": "application/fhir+json", "Prefer": "respond-async"})
        if r.status_code != 202:
            raise BulkExportError(f"Export kick-off failed: HTTP {r.status_code} {r.text[:500]}")
        status_url = r.headers.get("Content-Location")
        if not status_url:
            raise BulkExportError("Export kick-off response had no Content-Location header")
        return str(status_url)

    def wait(
        self,
        status_url: str,
        *,
        timeout: float = 3600.0,
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, object]:
        """Poll until the export completes; return the completion manifest."""
        deadline = time.monotonic() + timeout
        delay = 1.0
        while time.monotonic() < deadline:
            r = self.client.get(status_url, headers={"Accept": "application/json"})
            if r.status_code == 200:
                manifest: dict[str, object] = r.json()
                return manifest
            if r.status_code == 202:
                progress = r.headers.get("X-Progress", "in progress")
                if on_progress:
                    on_progress(progress)
                retry_after = r.headers.get("Retry-After")
                delay = (
                    float(retry_after) if retry_after and retry_after.isdigit() else min(delay * 1.5, 15.0)
                )
                time.sleep(delay)
                continue
            raise BulkExportError(f"Export failed: HTTP {r.status_code} {r.text[:500]}")
        raise BulkExportError(f"Export did not finish within {timeout:.0f}s")

    def download(self, manifest: dict[str, object], out_dir: Path) -> list[ExportFile]:
        out_dir.mkdir(parents=True, exist_ok=True)
        files: list[ExportFile] = []
        counters: dict[str, int] = {}
        outputs = manifest.get("output") or []
        assert isinstance(outputs, list)
        for item in outputs:
            rtype, url = item["type"], item["url"]
            n = counters[rtype] = counters.get(rtype, 0) + 1
            dest = out_dir / f"{rtype}.{n:03d}.ndjson"
            lines = 0
            with (
                self.client.stream("GET", url, headers={"Accept": "application/fhir+ndjson"}) as r,
                dest.open("wb") as fh,
            ):
                if r.status_code != 200:
                    raise BulkExportError(f"Download of {url} failed: HTTP {r.status_code}")
                for chunk in r.iter_bytes():
                    fh.write(chunk)
                    lines += chunk.count(b"\n")
            files.append(ExportFile(rtype, url, dest, item.get("count", lines)))
        return files

    def delete(self, status_url: str) -> None:
        """Tell the server it can discard the export files."""
        try:
            self.client.delete(status_url)
        except httpx.HTTPError as e:  # best effort
            log.debug("Could not delete export %s: %s", status_url, e)


def bulk_export(
    base_url: str,
    out_dir: str | Path,
    *,
    level: str = "system",
    group_id: str | None = None,
    types: Sequence[str] | None = None,
    since: str | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 3600.0,
    clean: bool = True,
    on_progress: Callable[[str], None] | None = None,
) -> ExportResult:
    """Run a complete Bulk Data export and write ``<Type>.<n>.ndjson`` files to ``out_dir``."""
    out = Path(out_dir)
    if clean and out.exists():
        for p in out.glob("*.ndjson"):
            p.unlink()
    start = time.monotonic()
    with BulkClient(base_url, headers=headers) as client:
        status_url = client.kick_off(level, group_id=group_id, types=types, since=since)
        manifest = client.wait(status_url, timeout=timeout, on_progress=on_progress)
        files = client.download(manifest, out)
        client.delete(status_url)
    tt = manifest.get("transactionTime")
    return ExportResult(out, files, str(tt) if tt else None, time.monotonic() - start)
