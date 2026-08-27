#!/usr/bin/env python3
"""Parse a WebVTT subtitle file into a clean, timestamped transcript.

YouTube auto-subs scroll, so every spoken line is emitted three times: as the
newly painted line of one cue, as a 10ms cue restating it once finished, and as
the leading carry-over line of the next cue. Deduping on whole-cue text misses
the third form, because there the overlap is the previous cue's *tail* against
this cue's *head* -- which is what leaves "a b / b c / c d" in the transcript.
So dedup works line by line, dropping the leading run a cue merely carries over,
and only then applies the whole-text rules other caption sources need.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


TS_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
# How many recently emitted lines a cue may carry over. YouTube rolls one or two
# lines of context; a wider window would start matching unrelated repeats.
ROLL_WINDOW = 4


def _to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(path: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    segments: list[dict] = []
    i = 0
    while i < len(lines):
        match = TS_RE.match(lines[i])
        if not match:
            i += 1
            continue

        start = _to_seconds(*match.groups()[:4])
        end = _to_seconds(*match.groups()[4:])
        i += 1

        cue_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            cleaned = TAG_RE.sub("", lines[i]).strip()
            if cleaned:
                cue_lines.append(cleaned)
            i += 1

        if cue_lines:
            segments.append({"start": round(start, 2), "end": round(end, 2), "lines": cue_lines})
        i += 1

    return _dedupe(segments)


def _strip_carryover(lines: list[str], emitted: list[str]) -> list[str]:
    """Drop the leading lines that only repeat the tail already emitted.

    Matches the longest run first, so a cue carrying over two lines is handled
    as well as the usual one. Anchoring on the *leading* run is what keeps a
    genuinely repeated line (a refrain, a repeated "thank you") from being
    eaten: it is only dropped when it sits exactly where the scroll puts it.
    """
    for k in range(min(len(lines), len(emitted)), 0, -1):
        if emitted[-k:] == lines[:k]:
            return lines[k:]
    return list(lines)


def _dedupe(segments: list[dict]) -> list[dict]:
    """Collapse the rolling duplicates YouTube auto-subs emit."""
    out: list[dict] = []
    emitted: list[str] = []
    for seg in segments:
        fresh = _strip_carryover(seg["lines"], emitted)
        if not fresh:
            # Nothing new: a 10ms cue restating a finished line. Stretch the
            # previous segment over it rather than emitting an empty one.
            if out:
                out[-1]["end"] = seg["end"]
            continue
        emitted.extend(fresh)
        del emitted[:-ROLL_WINDOW]

        text = " ".join(fresh).strip()
        if not text:
            continue
        if out and text == out[-1]["text"]:
            out[-1]["end"] = seg["end"]
            continue
        if out and text.startswith(out[-1]["text"] + " "):
            out[-1]["text"] = text
            out[-1]["end"] = seg["end"]
            continue
        out.append({"start": seg["start"], "end": seg["end"], "text": text})
    return out


def filter_range(
    segments: list[dict],
    start_seconds: float | None,
    end_seconds: float | None,
) -> list[dict]:
    """Return segments whose time range overlaps [start, end]."""
    if start_seconds is None and end_seconds is None:
        return segments
    lo = start_seconds if start_seconds is not None else float("-inf")
    hi = end_seconds if end_seconds is not None else float("inf")
    return [seg for seg in segments if seg["end"] >= lo and seg["start"] <= hi]


def format_transcript(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        start = int(seg["start"])
        stamp = f"[{start // 60:02d}:{start % 60:02d}]"
        lines.append(f"{stamp} {seg['text']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: transcribe.py <vtt-path>", file=sys.stderr)
        raise SystemExit(2)
    print(format_transcript(parse_vtt(sys.argv[1])))
