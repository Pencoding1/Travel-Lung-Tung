"""CR062: portable capture file names and sanitized submit transport errors.

All captures and transports here are SYNTHETIC; no network request is made.
"""

import json

import pytest

from crawler_service.app.acquisition.storage import OutputCollisionError
from crawler_service.app.social_ingest.fetch import Capture
from crawler_service.app.social_ingest.ingest import IngestError, _submit
from crawler_service.app.social_ingest.runner import write_capture

BODY = b"<!doctype html><title>CR062 synthetic capture</title>\n"
FETCHED_AT = "2026-10-18T00:00:00Z"

FORBIDDEN = set('<>:"/\\|?*')
RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"COM{index}" for index in range(1, 10)
} | {f"LPT{index}" for index in range(1, 10)}

HOSTILE_STEMS = [
    "policy-wiki_Wikivoyage:Copyleft",
    "..\\..\\escape",
    "../../escape",
    "/absolute",
    "C:\\folder\\escape",
    "colon:asterisk*question?quote\"apos'angle<>pipe|",
    "nul\x00control\x01\t\n",
    "trailingdots...   ",
    "",
    "!!!???...",
    "caf\u00e9-\u65e5\u672c\u8a9e",
    "A" * 1000,
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "LPT1",
]

HOSTILE_IDS = [
    "wikivoyage-colon",
    "backslash-traversal",
    "slash-traversal",
    "absolute",
    "drive-path",
    "windows-punctuation",
    "nul-controls",
    "trailing-dots-spaces",
    "empty",
    "punctuation-only",
    "non-ascii",
    "very-long",
    "device-CON",
    "device-PRN",
    "device-AUX",
    "device-NUL",
    "device-COM1",
    "device-LPT1",
]


def _capture(content_type="text/html; charset=utf-8", body=BODY):
    return Capture(
        url="https://example.test/pois",
        final_url="https://example.test/pois",
        status=200,
        content_type=content_type,
        fetched_at=FETCHED_AT,
        elapsed_ms=1,
        body=body,
    )


@pytest.mark.parametrize("stem", HOSTILE_STEMS, ids=HOSTILE_IDS)
def test_write_capture_sanitizes_hostile_stem(tmp_path, stem):
    directory = tmp_path / "raw"
    directory.mkdir()
    capture = _capture()

    returned = write_capture(capture, directory, stem=stem)

    directory_name, file_name = returned.split("/")
    assert directory_name == directory.name
    target = directory / file_name
    assert target.is_file()
    assert target.parent.resolve() == directory.resolve()
    # Exactly one immediate file: the stem created no descendant or sibling.
    assert list(directory.iterdir()) == [target]
    assert target.read_bytes() == BODY
    assert f"__{capture.sha256[:12]}.html" in file_name

    stem_part = file_name.rsplit("__", 1)[0]
    assert stem_part
    assert len(stem_part) <= 80
    assert stem_part.isascii()
    assert stem_part == stem_part.rstrip(" .")
    assert not (set(stem_part) & FORBIDDEN)
    assert all(ord(char) >= 32 for char in stem_part)
    assert file_name.split(".")[0].upper() not in RESERVED


RESERVED_LONG_STEMS = [
    ("CON." + "x" * 1000, "CON"),
    ("con." + "x" * 1000, "con"),
    ("NUL." + "x" * 1000, "NUL"),
    ("COM1.log" + "x" * 1000, "COM1"),
    ("LPT9." + "x" * 1000, "LPT9"),
]


@pytest.mark.parametrize(
    "stem,device",
    RESERVED_LONG_STEMS,
    ids=["CON-dot-long", "con-dot-long", "NUL-dot-long", "COM1-log-long", "LPT9-dot-long"],
)
def test_reserved_device_base_is_prefixed_before_length_cap(tmp_path, stem, device):
    directory = tmp_path / "raw"
    directory.mkdir()
    capture = _capture()

    returned = write_capture(capture, directory, stem=stem)

    file_name = returned.split("/", 1)[1]
    stem_part = file_name.rsplit("__", 1)[0]
    assert stem_part.upper().startswith(f"CAPTURE-{device.upper()}")
    assert len(stem_part) <= 80
    assert stem_part.isascii()
    assert stem_part == stem_part.rstrip(" .")
    assert not (set(stem_part) & FORBIDDEN)
    assert file_name.split(".")[0].upper() not in RESERVED
    assert list(directory.iterdir()) == [directory / file_name]
    assert (directory / file_name).read_bytes() == BODY
    assert f"__{capture.sha256[:12]}.html" in file_name


def test_legacy_safe_stem_name_is_unchanged_and_idempotent(tmp_path):
    directory = tmp_path / "raw"
    directory.mkdir()
    capture = _capture()

    first = write_capture(capture, directory, stem="pois")
    second = write_capture(capture, directory, stem="pois")

    expected = f"raw/pois__{capture.sha256[:12]}.html"
    assert first == expected
    assert second == expected
    assert (directory / f"pois__{capture.sha256[:12]}.html").read_bytes() == BODY


@pytest.mark.parametrize(
    "content_type,suffix",
    [
        ("application/json", ".json"),
        ("text/plain; charset=utf-8", ".txt"),
        ("text/csv", ".csv"),
        ("text/html; charset=utf-8", ".html"),
    ],
)
def test_content_type_extension_and_hash_suffix_are_preserved(
    tmp_path, content_type, suffix
):
    directory = tmp_path / "raw"
    directory.mkdir()
    capture = _capture(content_type=content_type)

    returned = write_capture(capture, directory, stem="ordinary_page")

    file_name = returned.split("/", 1)[1]
    assert file_name == f"ordinary_page__{capture.sha256[:12]}{suffix}"
    assert (directory / file_name).read_bytes() == BODY


def test_conflicting_preexisting_bytes_are_not_overwritten(tmp_path):
    directory = tmp_path / "raw"
    directory.mkdir()
    capture = _capture()
    returned = write_capture(capture, directory, stem="pois")
    target = directory / returned.split("/", 1)[1]
    target.write_bytes(b"different preexisting bytes")

    with pytest.raises(OutputCollisionError):
        write_capture(capture, directory, stem="pois")

    assert target.read_bytes() == b"different preexisting bytes"


SENTINEL = "NONSECRET-SENTINEL-9f3c"
SENTINEL_URL = (
    f"https://user:{SENTINEL}@example.invalid/ingest"
    f"?token={SENTINEL}&path=C:\\private\\{SENTINEL}.json"
)


@pytest.mark.parametrize("error_type", [OSError, TimeoutError, ConnectionError])
def test_transport_oserror_returns_exact_reason_without_leaking(
    error_type, capsys, caplog
):
    calls = []

    def transport(payloads):
        calls.append(payloads)
        raise error_type(f"POST {SENTINEL_URL} failed for {SENTINEL}")

    with caplog.at_level("DEBUG"):
        result = _submit([{"id": "synthetic-poi"}], transport=transport, opt_in=True)

    assert calls == [[{"id": "synthetic-poi"}]]
    assert result == {"status": "failed", "reason": "network_error", "imported": 0}
    out, err = capsys.readouterr()
    for text in (json.dumps(result), repr(result), out, err, caplog.text):
        assert SENTINEL not in text


def test_opt_in_and_transport_refusals_happen_before_transport():
    calls = []

    def transport(payloads):
        calls.append(payloads)
        return 200, b"{}"

    with pytest.raises(IngestError) as opt_in_error:
        _submit([], transport=transport, opt_in=False)
    assert opt_in_error.value.reason == "opt_in_required"

    with pytest.raises(IngestError) as transport_error:
        _submit([], transport=None, opt_in=True)
    assert transport_error.value.reason == "transport_not_configured"

    assert calls == []
