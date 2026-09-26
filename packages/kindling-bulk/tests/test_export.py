import json
from pathlib import Path

from kindling_bulk import bulk_export
from pytest_httpserver import HTTPServer
from werkzeug import Request, Response


def test_bulk_export_round_trip(tmp_path: Path, httpserver: HTTPServer) -> None:
    status = httpserver.url_for("/status/1")
    httpserver.expect_request("/fhir/$export", method="GET").respond_with_data(
        "", status=202, headers={"Content-Location": status}
    )
    manifest = {
        "transactionTime": "2026-01-01T00:00:00Z",
        "output": [
            {"type": "Patient", "url": httpserver.url_for("/files/p1")},
            {"type": "Observation", "url": httpserver.url_for("/files/o1")},
            {"type": "Observation", "url": httpserver.url_for("/files/o2")},
        ],
    }
    polls = {"n": 0}

    def status_handler(req: Request) -> Response:
        polls["n"] += 1
        if polls["n"] == 1:
            return Response("", status=202, headers={"Retry-After": "0", "X-Progress": "50%"})
        return Response(json.dumps(manifest), status=200, content_type="application/json")

    httpserver.expect_request("/status/1", method="GET").respond_with_handler(status_handler)
    httpserver.expect_request("/files/p1").respond_with_data('{"resourceType":"Patient","id":"a"}\n')
    httpserver.expect_request("/files/o1").respond_with_data('{"resourceType":"Observation"}\n' * 2)
    httpserver.expect_request("/files/o2").respond_with_data('{"resourceType":"Observation"}\n')
    httpserver.expect_request("/status/1", method="DELETE").respond_with_data("", status=202)

    progress: list[str] = []
    result = bulk_export(httpserver.url_for("/fhir"), tmp_path, on_progress=progress.append)

    assert progress == ["50%"]
    assert result.transaction_time == "2026-01-01T00:00:00Z"
    by_type = result.by_type()
    assert [p.name for p in by_type["Observation"]] == ["Observation.001.ndjson", "Observation.002.ndjson"]
    assert (tmp_path / "Patient.001.ndjson").read_text().startswith('{"resourceType":"Patient"')
    assert [f.count for f in result.files] == [1, 2, 1]
