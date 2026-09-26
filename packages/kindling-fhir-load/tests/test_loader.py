import json
from pathlib import Path

from kindling_fhir_load import Loader, order_bundles
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response


def _bundle(tmp: Path, name: str, n: int) -> Path:
    p = tmp / name
    p.write_text(json.dumps({"resourceType": "Bundle", "type": "transaction", "entry": [{}] * n}))
    return p


def test_order_bundles(tmp_path: Path) -> None:
    names = ["b.json", "practitionerInformation1.json", "a.json", "hospitalInformation1.json"]
    info, patients = order_bundles(tmp_path / n for n in names)
    assert [p.name for p in info] == ["hospitalInformation1.json", "practitionerInformation1.json"]
    assert [p.name for p in patients] == ["a.json", "b.json"]


def test_load_orders_and_retries(tmp_path: Path, httpserver: HTTPServer) -> None:
    seen: list[int] = []
    calls = {"n": 0}

    def handler(req: Request) -> Response:
        calls["n"] += 1
        entries = len(json.loads(req.data)["entry"])
        seen.append(entries)
        if calls["n"] == 2:  # first patient bundle attempt fails transiently
            return Response("busy", status=503)
        body = {"resourceType": "Bundle", "type": "transaction-response", "entry": [{}] * entries}
        return Response(json.dumps(body), status=200, content_type="application/fhir+json")

    httpserver.expect_request("/fhir", method="POST").respond_with_handler(handler)
    paths = [_bundle(tmp_path, "p1.json", 3), _bundle(tmp_path, "hospitalInformation1.json", 2)]
    with Loader(httpserver.url_for("/fhir"), concurrency=1, retries=2) as loader:
        report = loader.load(paths)
    assert seen[0] == 2  # info bundle first
    assert report.resources == 5
    assert not report.failed


def test_load_reports_failures(tmp_path: Path, httpserver: HTTPServer) -> None:
    outcome = {"resourceType": "OperationOutcome", "issue": [{"diagnostics": "bad reference"}]}
    httpserver.expect_request("/fhir", method="POST").respond_with_json(outcome, status=400)
    with Loader(httpserver.url_for("/fhir"), retries=3) as loader:
        report = loader.load([_bundle(tmp_path, "p1.json", 1)])
    assert len(report.failed) == 1
    assert "bad reference" in (report.failed[0].error or "")
