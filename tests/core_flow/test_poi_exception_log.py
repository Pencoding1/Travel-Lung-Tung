"""POI global exception log: constant event, safe method, exception type only.

A synthetic marker is carried in the path, query string and exception text.
None of it may survive into the log record or the response body.
"""

import asyncio
import logging

from starlette.requests import Request

from app import main as poi_main

MARKER = "SYNTHETIC_MARKER_Q7"


def _request():
    return Request({
        "type": "http",
        "method": "GET",
        "path": f"/api/{MARKER}",
        "query_string": f"token={MARKER}".encode("ascii"),
        "headers": [],
    })


def test_global_exception_log_is_constant_and_redacted(caplog):
    caplog.set_level(logging.ERROR)

    response = asyncio.run(poi_main.global_exception_handler(
        _request(), RuntimeError(f"raw failure {MARKER}")))

    assert response.status_code == 500
    record_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "POI_UNHANDLED_EXCEPTION" in record_text
    assert "method=GET" in record_text
    assert "type=RuntimeError" in record_text
    assert MARKER not in caplog.text
    assert "/api/" not in record_text
    assert "token=" not in record_text
    assert "raw failure" not in record_text

    body = response.body.decode("utf-8")
    assert MARKER not in body
    assert "internal_server_error" in body


def test_global_exception_response_is_the_documented_shape():
    response = asyncio.run(poi_main.global_exception_handler(
        _request(), ValueError("boom")))
    payload = response.body.decode("utf-8")
    assert '"is_success":false' in payload.replace(" ", "")
    assert "An unexpected error occurred" in payload
