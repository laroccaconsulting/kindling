from pathlib import Path

import pytest
from kindling_synthea.runner import SyntheaError, SyntheaResult, build_command


def test_build_command_is_reproducible(tmp_path: Path) -> None:
    cmd = build_command(Path("s.jar"), population=10, seed=7, out_dir=tmp_path, reference_date="2026-01-01")
    assert cmd[:4] == ["java", "-jar", "s.jar", "-s"]
    assert cmd[cmd.index("-s") + 1] == "7"
    assert cmd[cmd.index("-cs") + 1] == "7"
    assert cmd[cmd.index("-r") + 1] == "20260101"
    assert (
        "--exporter.fhir.excluded_resources=DocumentReference,Provenance,ImagingStudy,SupplyDelivery" in cmd
    )
    assert cmd[-1] == "Massachusetts"


def test_config_overrides_preset(tmp_path: Path) -> None:
    cmd = build_command(
        Path("s.jar"),
        population=1,
        seed=1,
        out_dir=tmp_path,
        config={"exporter.fhir.excluded_resources": ""},
        city="Boston",
    )
    assert "--exporter.fhir.excluded_resources=" in cmd
    assert cmd[-2:] == ["Massachusetts", "Boston"]


def test_unknown_preset(tmp_path: Path) -> None:
    with pytest.raises(SyntheaError):
        build_command(Path("s.jar"), population=1, seed=1, out_dir=tmp_path, preset="nope")


def test_bundle_ordering(tmp_path: Path) -> None:
    for name in ["Zed_1.json", "Amy_2.json", "practitionerInformation1.json", "hospitalInformation1.json"]:
        (tmp_path / name).write_text("{}")
    r = SyntheaResult(tmp_path, tmp_path, 1, 1, "x")
    assert [p.name for p in r.bundles] == [
        "hospitalInformation1.json",
        "practitionerInformation1.json",
        "Amy_2.json",
        "Zed_1.json",
    ]
