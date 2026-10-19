#!/usr/bin/env python3
"""Regression tests for VideoStitch audio handling during concatenation.

Four failure modes are covered:

1. A video-only clip (image-derived footage, a silent brand bumper) used to be
   padded with silence only on crossfade/fade paths. On a plain cut the concat
   demuxer dropped or truncated audio, producing a master whose audio ended
   before its video.
2. Normalization hardcoded 44.1 kHz stereo, silently downsampling 48 kHz
   narration whenever any clip triggered a re-encode.
3. Mono webinar bodies and stereo bookends were treated as concat-compatible,
   so the output layout was inherited from whichever segment came first.
4. Cut stitches stream-copied independently encoded AAC packets. Decoder state
   and priming can differ at every join, producing intermittent clicks, extreme
   decoded peaks, or one-sided audio even when the container opens normally.
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.video.video_stitch import VideoStitch

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _make_clip(
    path: Path,
    *,
    seconds: int,
    with_audio: bool,
    sample_rate: int = 48000,
    channels: int = 2,
) -> Path:
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=navy:s=320x180:d={seconds}:r=30",
    ]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    cmd += ["-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p", "-g", "30"]
    if with_audio:
        cmd += ["-c:a", "aac", "-ar", str(sample_rate), "-ac", str(channels), "-shortest"]
    else:
        cmd += ["-an"]
    cmd.append(str(path))
    subprocess.run(cmd, capture_output=True, check=True)
    return path


def _streams(path: Path) -> dict[str, dict]:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    )
    out: dict[str, dict] = {}
    for stream in json.loads(proc.stdout)["streams"]:
        out.setdefault(stream["codec_type"], stream)
    return out


def _channel_rms_levels(path: Path) -> list[float]:
    proc = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-v", "info",
            "-i", str(path), "-map", "0:a:0", "-af", "astats", "-f", "null", "-",
        ],
        capture_output=True, text=True, check=True,
    )
    channel_section = proc.stderr.split("Overall", 1)[0]
    return [float(value) for value in re.findall(r"RMS level dB: (-?[0-9.]+)", channel_section)]


def test_cut_stitch_pads_silent_clip_so_audio_spans_full_master(tmp_path):
    """A video-only bumper must not shorten the delivered audio track."""
    silent = _make_clip(tmp_path / "silent.mp4", seconds=2, with_audio=False)
    voiced = _make_clip(tmp_path / "voiced.mp4", seconds=3, with_audio=True)
    output = tmp_path / "master.mp4"

    result = VideoStitch().execute({
        "operation": "stitch",
        "clips": [str(silent), str(voiced)],
        "output_path": str(output),
        "transition": "cut",
        "auto_normalize": True,
    })

    assert result.success, result.error
    streams = _streams(output)
    assert "audio" in streams, "delivered master lost its audio stream entirely"

    video_duration = float(streams["video"]["duration"])
    audio_duration = float(streams["audio"]["duration"])
    assert video_duration == pytest.approx(5.0, abs=0.2)
    assert audio_duration == pytest.approx(video_duration, abs=0.2)


def test_normalization_preserves_highest_source_sample_rate(tmp_path):
    """48 kHz narration must survive a normalizing concat."""
    hi = _make_clip(tmp_path / "hi.mp4", seconds=2, with_audio=True, sample_rate=48000)
    silent = _make_clip(tmp_path / "silent.mp4", seconds=1, with_audio=False)
    output = tmp_path / "master.mp4"

    result = VideoStitch().execute({
        "operation": "stitch",
        "clips": [str(hi), str(silent)],
        "output_path": str(output),
        "transition": "cut",
        "auto_normalize": True,
    })

    assert result.success, result.error
    assert int(_streams(output)["audio"]["sample_rate"]) == 48000


def test_explicit_target_sample_rate_is_honoured(tmp_path):
    """Callers can still pin an exact delivery layout."""
    clip_a = _make_clip(tmp_path / "a.mp4", seconds=1, with_audio=True, sample_rate=48000)
    clip_b = _make_clip(tmp_path / "b.mp4", seconds=1, with_audio=True, sample_rate=48000)
    output = tmp_path / "master.mp4"

    result = VideoStitch().execute({
        "operation": "stitch",
        "clips": [str(clip_a), str(clip_b)],
        "output_path": str(output),
        "transition": "cut",
        "auto_normalize": True,
        "target_sample_rate": 44100,
    })

    assert result.success, result.error
    assert int(_streams(output)["audio"]["sample_rate"]) == 44100


def test_cut_stitch_normalizes_mono_body_and_stereo_bookend(tmp_path):
    """Webinar bodies and brand bookends must share one explicit layout."""
    mono_body = _make_clip(
        tmp_path / "body.mp4", seconds=2, with_audio=True, channels=1,
    )
    stereo_bookend = _make_clip(
        tmp_path / "bookend.mp4", seconds=1, with_audio=True, channels=2,
    )
    output = tmp_path / "master.mp4"

    result = VideoStitch().execute({
        "operation": "stitch",
        "clips": [str(mono_body), str(stereo_bookend)],
        "output_path": str(output),
        "transition": "cut",
        "auto_normalize": True,
    })

    assert result.success, result.error
    assert int(_streams(output)["audio"]["channels"]) == 2
    channel_levels = _channel_rms_levels(output)
    assert len(channel_levels) == 2
    assert channel_levels[0] == pytest.approx(channel_levels[1], abs=0.2)


def test_cut_stitch_reencodes_aac_across_join(tmp_path):
    """A cut stitch must create one continuous AAC encode, not copy packets."""
    clip_a = _make_clip(tmp_path / "a.mp4", seconds=1, with_audio=True)
    clip_b = _make_clip(tmp_path / "b.mp4", seconds=1, with_audio=True)
    output = tmp_path / "master.mp4"

    result = VideoStitch().execute({
        "operation": "stitch",
        "clips": [str(clip_a), str(clip_b)],
        "output_path": str(output),
        "transition": "cut",
    })

    assert result.success, result.error
    assert result.data["method"] == "concat_demuxer_audio_reencode"
