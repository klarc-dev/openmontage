#!/usr/bin/env python3
"""Regression coverage for audio-safe VideoTrimmer concatenation."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.video.video_trimmer import VideoTrimmer

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required",
)


def _make_clip(path: Path, *, channels: int) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=navy:s=320x180:d=1:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-ac", str(channels), "-shortest",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _make_silent_clip(path: Path) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=black:s=320x180:d=1:r=30",
            "-c:v", "libx264", "-crf", "30", "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    return path


def _audio_stream(path: Path) -> dict:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_streams", "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)["streams"][0]


def _streams(path: Path) -> list[dict]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)["streams"]


def test_concat_reencodes_audio_to_one_delivery_layout(tmp_path):
    mono = _make_clip(tmp_path / "mono.mp4", channels=1)
    stereo = _make_clip(tmp_path / "stereo.mp4", channels=2)
    output = tmp_path / "joined.mp4"

    result = VideoTrimmer().execute({
        "operation": "concat",
        "segments": [
            {"input_path": str(mono)},
            {"input_path": str(stereo)},
        ],
        "output_path": str(output),
    })

    assert result.success, result.error
    assert result.data["audio_method"] == "continuous_aac_encode"
    audio = _audio_stream(output)
    assert int(audio["sample_rate"]) == 48000
    assert int(audio["channels"]) == 2


def test_cut_arbitrary_non_keyframe_range_keeps_video_and_audio(tmp_path):
    source = _make_clip(tmp_path / "source.mp4", channels=2)
    output = tmp_path / "cut.mp4"

    result = VideoTrimmer().execute({
        "operation": "cut",
        "input_path": str(source),
        "start_seconds": 0.17,
        "end_seconds": 0.83,
        "output_path": str(output),
    })

    assert result.success, result.error
    streams = _streams(output)
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert video["codec_name"] == "h264"
    assert audio["codec_name"] == "aac"
    assert abs(float(video["duration"]) - 0.66) < 0.10
    assert abs(float(audio["duration"]) - float(video["duration"])) < 0.10


def test_concat_arbitrary_non_keyframe_cuts_keep_video(tmp_path):
    first = _make_clip(tmp_path / "first.mp4", channels=2)
    second = _make_clip(tmp_path / "second.mp4", channels=2)
    output = tmp_path / "non-keyframe-joined.mp4"

    result = VideoTrimmer().execute({
        "operation": "concat",
        "segments": [
            {"input_path": str(first), "start_seconds": 0.17, "end_seconds": 0.83},
            {"input_path": str(second), "start_seconds": 0.11, "end_seconds": 0.89},
        ],
        "output_path": str(output),
    })

    assert result.success, result.error
    assert result.data["video_method"] == "decoded_trim_single_encode"
    streams = _streams(output)
    assert {stream["codec_type"] for stream in streams} == {"video", "audio"}
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert video["codec_name"] == "h264"
    assert audio["codec_name"] == "aac"
    assert abs(float(video["duration"]) - 1.44) < 0.10
    assert abs(float(audio["duration"]) - float(video["duration"])) < 0.10


def test_concat_pads_video_only_segment_with_silence(tmp_path):
    silent = _make_silent_clip(tmp_path / "silent.mp4")
    voiced = _make_clip(tmp_path / "voiced.mp4", channels=2)
    output = tmp_path / "silent-then-voiced.mp4"

    result = VideoTrimmer().execute({
        "operation": "concat",
        "segments": [
            {"input_path": str(silent)},
            {"input_path": str(voiced)},
        ],
        "output_path": str(output),
    })

    assert result.success, result.error
    streams = _streams(output)
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    audio = next(stream for stream in streams if stream["codec_type"] == "audio")
    assert int(audio["sample_rate"]) == 48000
    assert int(audio["channels"]) == 2
    assert abs(float(video["duration"]) - 2.0) < 0.10
    assert abs(float(audio["duration"]) - float(video["duration"])) < 0.10
