"""WebVTT parsing, with the rolling-duplicate shape YouTube actually emits."""
from __future__ import annotations

from pathlib import Path

import transcribe


def _vtt(tmp_path: Path, body: str) -> str:
    path = tmp_path / "subs.vtt"
    path.write_text("WEBVTT\nKind: captions\nLanguage: en\n\n" + body, encoding="utf-8")
    return str(path)


# Trimmed from a real youtube auto-caption file: each spoken line appears as a
# painted line with per-word timing tags, then as a 10ms cue restating it, then
# as the carry-over head of the next cue.
ROLLING = """00:00:00.000 --> 00:00:01.990 align:start position:0%
alpha<00:00:00.120><c> one</c>

00:00:01.990 --> 00:00:02.000 align:start position:0%
alpha one

00:00:02.000 --> 00:00:04.430 align:start position:0%
alpha one
bravo<00:00:02.120><c> two</c>

00:00:04.430 --> 00:00:04.440 align:start position:0%
bravo two

00:00:04.440 --> 00:00:06.950 align:start position:0%
bravo two
charlie<00:00:05.360><c> three</c>
"""


def test_rolling_captions_emit_each_line_once(tmp_path: Path):
    segments = transcribe.parse_vtt(_vtt(tmp_path, ROLLING))
    assert [s["text"] for s in segments] == ["alpha one", "bravo two", "charlie three"]


def test_rolling_captions_keep_the_painted_line_timestamp(tmp_path: Path):
    segments = transcribe.parse_vtt(_vtt(tmp_path, ROLLING))
    # Each line is stamped when it started being painted, not when it scrolled
    # off, so a cue-restating 10ms entry must not become its own segment.
    assert [s["start"] for s in segments] == [0.0, 2.0, 4.44]


def test_timing_tags_are_stripped(tmp_path: Path):
    segments = transcribe.parse_vtt(_vtt(tmp_path, ROLLING))
    assert not any("<" in s["text"] for s in segments)


def test_identical_consecutive_cues_collapse(tmp_path: Path):
    body = """00:00:00.000 --> 00:00:02.000
same line

00:00:02.000 --> 00:00:04.000
same line
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert [s["text"] for s in segments] == ["same line"]
    assert segments[0]["end"] == 4.0


def test_growing_cue_keeps_only_the_longest(tmp_path: Path):
    body = """00:00:00.000 --> 00:00:01.000
hello there

00:00:01.000 --> 00:00:02.000
hello there general kenobi
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert [s["text"] for s in segments] == ["hello there general kenobi"]


def test_repeated_line_survives_outside_carryover_position(tmp_path: Path):
    """A refrain must not be eaten: dedup only drops a cue's *leading* run."""
    body = """00:00:00.000 --> 00:00:02.000
la la la
verse one

00:00:02.000 --> 00:00:04.000
verse two
la la la
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert [s["text"] for s in segments] == ["la la la verse one", "verse two la la la"]


def test_two_line_carryover_is_dropped(tmp_path: Path):
    body = """00:00:00.000 --> 00:00:02.000
first
second

00:00:02.000 --> 00:00:04.000
first
second
third
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert [s["text"] for s in segments] == ["first second", "third"]


def test_filter_range_keeps_overlapping_segments(tmp_path: Path):
    segments = transcribe.parse_vtt(_vtt(tmp_path, ROLLING))
    assert [s["text"] for s in transcribe.filter_range(segments, 4.0, 10.0)] == [
        "bravo two",
        "charlie three",
    ]


def test_format_transcript_stamps_minutes_and_seconds(tmp_path: Path):
    body = """00:01:05.000 --> 00:01:07.000
past the minute mark
"""
    out = transcribe.format_transcript(transcribe.parse_vtt(_vtt(tmp_path, body)))
    assert out == "[01:05] past the minute mark"


def test_html_entities_are_unescaped(tmp_path: Path):
    """YouTube escapes its speaker-change marker as `&gt;&gt;`."""
    body = """00:00:00.000 --> 00:00:02.000
&gt;&gt; Ben &amp; Jerry said &quot;hello&quot;
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert segments[0]["text"] == '>> Ben & Jerry said "hello"'


def test_escaped_markup_is_not_eaten_as_a_tag(tmp_path: Path):
    """Unescaping must run after tag stripping, or `&lt;b&gt;` would vanish."""
    body = """00:00:00.000 --> 00:00:02.000
use &lt;b&gt; for bold
"""
    segments = transcribe.parse_vtt(_vtt(tmp_path, body))
    assert segments[0]["text"] == "use <b> for bold"
