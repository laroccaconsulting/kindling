"""Download a pinned Synthea release and run it with reproducible settings."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_VERSION = "3.4.0"
_URL = "https://github.com/synthetichealth/synthea/releases/download/v{version}/synthea-with-dependencies.jar"

# Known-good checksums for pinned releases. A version missing here still runs, but
# without integrity verification.
KNOWN_SHA256: dict[str, str] = {}

# Resource types that are large and not used by the analytics or quality pipelines:
# clinical notes (DocumentReference, and DiagnosticReport.presentedForm), provenance,
# imaging metadata and supply deliveries make up about 40% of Synthea's output.
_HEAVY = ["DocumentReference", "Provenance", "ImagingStudy", "SupplyDelivery"]

PRESETS: dict[str, dict[str, str]] = {
    # Everything Synthea produces.
    "full": {},
    # What Kindling's analytics and quality pipelines use. The default.
    "analytics": {
        "exporter.fhir.excluded_resources": ",".join(_HEAVY),
    },
}


class SyntheaError(RuntimeError):
    pass


@dataclass
class SyntheaResult:
    out_dir: Path
    fhir_dir: Path
    seed: int
    population: int
    version: str
    command: list[str] = field(default_factory=list)

    @property
    def info_bundles(self) -> list[Path]:
        """Organization/Location and Practitioner bundles. Load these before patients."""
        return sorted(
            p
            for p in self.fhir_dir.glob("*.json")
            if p.name.startswith(("hospitalInformation", "practitionerInformation"))
        )

    @property
    def patient_bundles(self) -> list[Path]:
        info = set(self.info_bundles)
        return sorted(p for p in self.fhir_dir.glob("*.json") if p not in info)

    @property
    def bundles(self) -> list[Path]:
        """All bundles in dependency order."""
        return self.info_bundles + self.patient_bundles


def cache_dir() -> Path:
    base = os.environ.get("KINDLING_CACHE_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "kindling"
    )
    return Path(base)


def ensure_jar(version: str = DEFAULT_VERSION, jar: str | Path | None = None) -> Path:
    """Return the path to a Synthea jar, downloading the pinned release if needed."""
    if jar is None:
        jar = os.environ.get("KINDLING_SYNTHEA_JAR")
    if jar:
        path = Path(jar)
        if not path.exists():
            raise SyntheaError(f"Synthea jar not found: {path}")
        return path
    path = cache_dir() / "synthea" / version / "synthea-with-dependencies.jar"
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = _URL.format(version=version)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        try:
            with urllib.request.urlopen(url) as resp:
                shutil.copyfileobj(resp, tmp)
        except Exception as e:  # pragma: no cover - network
            os.unlink(tmp.name)
            raise SyntheaError(f"Could not download Synthea {version} from {url}: {e}") from e
    expected = KNOWN_SHA256.get(version)
    if expected:
        digest = hashlib.sha256(Path(tmp.name).read_bytes()).hexdigest()
        if digest != expected:
            os.unlink(tmp.name)
            raise SyntheaError(f"Checksum mismatch for Synthea {version}: {digest}")
    os.replace(tmp.name, path)
    return path


def build_command(
    jar: Path,
    *,
    population: int,
    seed: int,
    out_dir: Path,
    state: str = "Massachusetts",
    city: str | None = None,
    reference_date: str | None = None,
    years_of_history: int = 10,
    preset: str = "analytics",
    config: dict[str, str] | None = None,
    java: str = "java",
    java_opts: list[str] | None = None,
) -> list[str]:
    if preset not in PRESETS:
        raise SyntheaError(f"Unknown preset {preset!r}; choose from {sorted(PRESETS)}")
    settings = {
        "exporter.baseDirectory": str(out_dir),
        "exporter.fhir.export": "true",
        "exporter.fhir.transaction_bundle": "true",
        "exporter.hospital.fhir.export": "true",
        "exporter.practitioner.fhir.export": "true",
        "exporter.csv.export": "false",
        "exporter.years_of_history": str(years_of_history),
        "generate.log_patients.detail": "none",
        **PRESETS[preset],
        **(config or {}),
    }
    cmd = [
        java,
        *(java_opts or []),
        "-jar",
        str(jar),
        "-s",
        str(seed),
        "-cs",
        str(seed),
        "-p",
        str(population),
    ]
    if reference_date:
        cmd += ["-r", reference_date.replace("-", "")]
    cmd += [f"--{k}={v}" for k, v in settings.items()]
    cmd.append(state)
    if city:
        cmd.append(city)
    return cmd


def generate(
    population: int = 100,
    seed: int = 42,
    out_dir: str | Path = "data/synthea",
    *,
    state: str = "Massachusetts",
    city: str | None = None,
    reference_date: str | None = "2026-01-01",
    years_of_history: int = 10,
    preset: str = "analytics",
    config: dict[str, str] | None = None,
    version: str = DEFAULT_VERSION,
    jar: str | Path | None = None,
    clean: bool = True,
    quiet: bool = True,
) -> SyntheaResult:
    """Generate ``population`` living patients (Synthea adds the deceased on top).

    The same seed, reference date, version and settings always produce the same patients,
    which is what lets Kindling assert on measure counts in CI.
    """
    if shutil.which("java") is None:
        raise SyntheaError("Synthea needs Java 17+ on PATH (e.g. `apt install openjdk-21-jre-headless`).")
    out = Path(out_dir).resolve()
    if clean and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    jar_path = ensure_jar(version, jar)
    cmd = build_command(
        jar_path,
        population=population,
        seed=seed,
        out_dir=out,
        state=state,
        city=city,
        reference_date=reference_date,
        years_of_history=years_of_history,
        preset=preset,
        config=config,
    )
    proc = subprocess.run(cmd, capture_output=quiet, text=True, check=False)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-2000:] if quiet else ""
        raise SyntheaError(f"Synthea exited with {proc.returncode}\n{tail}")
    fhir_dir = out / "fhir"
    if not fhir_dir.exists():
        raise SyntheaError(f"Synthea produced no FHIR output in {fhir_dir}")
    return SyntheaResult(out, fhir_dir, seed, population, version, cmd)
