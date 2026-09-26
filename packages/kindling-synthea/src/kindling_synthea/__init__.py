"""Run Synthea reproducibly from Python.

from kindling_synthea import generate
result = generate(population=100, seed=42, out_dir="data/synthea")
result.patient_bundles  # FHIR R4 transaction bundles, one per patient
"""

from .runner import (
    DEFAULT_VERSION,
    PRESETS,
    SyntheaError,
    SyntheaResult,
    ensure_jar,
    generate,
)

__all__ = ["DEFAULT_VERSION", "PRESETS", "SyntheaError", "SyntheaResult", "ensure_jar", "generate"]
__version__ = "0.1.0"
