"""yt-dlp argv construction for download.py.

Regression guard: caption discovery should request the video's source language
instead of hard-coding English or fetching every auto-translated track.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "skills" / "watch" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import download  # noqa: E402

URL = "https://www.youtube.com/watch?v=rlOpbu3Enkw"


def _capture_argv(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub subprocess.run inside download.py and record every argv."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        class _Result:
            returncode = 0
            stdout = '{"language":"es","subtitles":{"es":[{}]}}' if "--dump-single-json" in cmd else ""
            stderr = ""
        return _Result()

    monkeypatch.setattr(download.subprocess, "run", fake_run)
    return calls


def _sub_langs(calls: list[list[str]]) -> str:
    argv = next(call for call in calls if "--sub-langs" in call)
    return argv[argv.index("--sub-langs") + 1]


def _assert_source_language(langs: str) -> None:
    assert "es" in langs.split(","), f"source language must be requested, got {langs!r}"


def test_fetch_captions_requests_source_language(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    download.fetch_captions(URL, tmp_path / "download")
    _assert_source_language(_sub_langs(calls))


def test_download_url_requests_source_language(monkeypatch, tmp_path):
    calls = _capture_argv(monkeypatch)
    # _pick_video returns None with no real file, which raises SystemExit after
    # the yt-dlp argv is already built — that's all we need to inspect.
    with pytest.raises(SystemExit):
        download.download_url(URL, tmp_path / "download")
    _assert_source_language(_sub_langs(calls))
