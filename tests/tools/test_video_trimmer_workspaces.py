"""Concat runs as one decoded filter graph: it owns no temporary workspace,
leaves unrelated files alone and cleans up only its own partial output."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.video.video_trimmer import VideoTrimmer

PROBE = json.dumps({"format": {"duration": "2.0"},
                    "streams": [{"codec_type": "video"}, {"codec_type": "audio"}]})


def _runner(on_encode=None):
    calls = []

    def run(cmd):
        calls.append(cmd)
        if cmd[0] == "ffprobe":
            return SimpleNamespace(stdout=PROBE, returncode=0)
        if on_encode:
            on_encode(cmd)
        return SimpleNamespace(stdout="", returncode=0)

    return run, calls


def test_concat_creates_no_temporary_workspace(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    before = set(tmp_path.iterdir())
    run, calls = _runner()
    tool = VideoTrimmer()
    with patch.object(tool, "run_command", side_effect=run):
        result = tool.execute({"operation": "concat",
                               "segments": [{"input_path": str(source)}, {"input_path": str(source), "start_seconds": 1}],
                               "output_path": str(tmp_path / "outer.mp4")})
    assert result.success, result.error
    encodes = [c for c in calls if c[0] == "ffmpeg"]
    assert len(encodes) == 1, "concat must encode once, without intermediate cuts"
    assert "concat=n=2:v=1:a=1" in " ".join(encodes[0])
    assert set(tmp_path.iterdir()) == before
    assert source.read_bytes() == b"source"


def test_failed_encode_removes_partial_output_without_masking_error(tmp_path):
    source = tmp_path / "source.mp4"
    source.touch()
    output = tmp_path / "output.mp4"

    def fail(cmd):
        Path(cmd[-1]).write_bytes(b"partial")
        raise RuntimeError("encode failed")

    run, _ = _runner(on_encode=fail)
    tool = VideoTrimmer()
    with patch.object(tool, "run_command", side_effect=run):
        result = tool.execute({"operation": "concat", "segments": [{"input_path": str(source), "start_seconds": 1}],
                               "output_path": str(output)})
    assert not result.success
    assert result.error == "encode failed"
    assert not output.exists()


def test_existing_concat_directory_is_not_owned_by_call(tmp_path):
    directory = tmp_path / ".concat_tmp"
    directory.mkdir()
    source = directory / "original.mp4"
    source.write_bytes(b"original")
    run, _ = _runner()
    tool = VideoTrimmer()
    with patch.object(tool, "run_command", side_effect=run):
        result = tool.execute({"operation": "concat", "segments": [{"input_path": str(source)}],
                               "output_path": str(tmp_path / "output.mp4")})
    assert result.success, result.error
    assert directory.is_dir()
    assert source.read_bytes() == b"original"
