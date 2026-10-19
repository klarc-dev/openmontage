"""Video trimmer tool wrapping FFmpeg.

Provides cut, trim, speed adjustment, and concatenation of video segments.
All operations are deterministic and produce lossless or near-lossless output
by default.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolTier,
)


class VideoTrimmer(BaseTool):
    name = "video_trimmer"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["cmd:ffmpeg", "cmd:ffprobe"]
    install_instructions = (
        "Install FFmpeg: https://ffmpeg.org/download.html\n"
        "Windows: winget install FFmpeg\n"
        "macOS: brew install ffmpeg\n"
        "Linux: sudo apt install ffmpeg"
    )
    agent_skills = ["ffmpeg", "video-toolkit"]

    capabilities = ["cut", "trim", "speed_adjust", "concat"]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["cut", "speed", "concat"],
            },
            "input_path": {"type": "string"},
            "output_path": {"type": "string"},
            "start_seconds": {"type": "number", "minimum": 0},
            "end_seconds": {"type": "number", "minimum": 0},
            "speed_factor": {"type": "number", "minimum": 0.1, "maximum": 100.0},
            "segments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "input_path": {"type": "string"},
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                    },
                },
            },
            "codec": {"type": "string", "default": "copy"},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=2, ram_mb=1024, vram_mb=0, disk_mb=2000, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["FFmpeg error"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["operation", "input_path", "start_seconds", "end_seconds", "speed_factor"]
    side_effects = ["writes video file to output_path"]
    user_visible_verification = ["Play trimmed output and verify cut points"]

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs["operation"]
        start = time.time()

        try:
            if operation == "cut":
                result = self._cut(inputs)
            elif operation == "speed":
                result = self._speed(inputs)
            elif operation == "concat":
                result = self._concat(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        result.duration_seconds = round(time.time() - start, 2)
        return result

    def _probe_media(self, path: Path) -> dict[str, Any]:
        proc = self.run_command([
            "ffprobe", "-v", "error", "-show_streams", "-show_format",
            "-of", "json", str(path),
        ])
        return json.loads(proc.stdout)

    @staticmethod
    def _media_duration(probe: dict[str, Any]) -> float:
        value = probe.get("format", {}).get("duration")
        if value is not None:
            return float(value)
        durations = [
            float(stream["duration"])
            for stream in probe.get("streams", [])
            if stream.get("duration") is not None
        ]
        return max(durations, default=0.0)

    def _cut(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        start_s = float(inputs.get("start_seconds", 0))
        end_s = inputs.get("end_seconds")
        output_path = Path(
            inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_cut")))
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        probe = self._probe_media(input_path)
        has_audio = any(
            stream.get("codec_type") == "audio"
            for stream in probe.get("streams", [])
        )
        source_duration = self._media_duration(probe)
        effective_end = float(end_s) if end_s is not None else source_duration
        segment_duration = max(0.0, effective_end - start_s)
        video_trim_args = [f"start={start_s}"]
        audio_trim_args = [f"start={start_s}"]
        if end_s is not None:
            video_trim_args.append(f"end={end_s}")
            audio_trim_args.append(f"end={end_s}")

        filter_parts = [
            f"[0:v:0]trim={':'.join(video_trim_args)},setpts=PTS-STARTPTS[outv]"
        ]
        if has_audio:
            filter_parts.append(
                f"[0:a:0]atrim={':'.join(audio_trim_args)},asetpts=PTS-STARTPTS,"
                "aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[outa]"
            )
        else:
            filter_parts.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={segment_duration},"
                "asetpts=PTS-STARTPTS[outa]"
            )

        cmd = [
            "ffmpeg", "-y", "-i", str(input_path),
            "-filter_complex", ";".join(filter_parts),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "cut",
                "input": str(input_path),
                "output": str(output_path),
                "start_seconds": start_s,
                "end_seconds": end_s,
                "audio_method": "continuous_aac_encode",
                "video_method": "decoded_trim_single_encode",
            },
            artifacts=[str(output_path)],
        )

    def _speed(self, inputs: dict[str, Any]) -> ToolResult:
        input_path = Path(inputs["input_path"])
        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        factor = inputs.get("speed_factor", 1.0)
        output_path = Path(
            inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_speed")))
        )

        # Video: setpts adjusts presentation timestamps (inverse of speed)
        # Audio: atempo adjusts audio speed (must chain for >2x)
        video_filter = f"setpts={1.0/factor}*PTS"
        audio_filters = self._build_atempo_chain(factor)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-filter:v", video_filter,
            "-filter:a", audio_filters,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "speed",
                "input": str(input_path),
                "output": str(output_path),
                "speed_factor": factor,
            },
            artifacts=[str(output_path)],
        )

    def _concat(self, inputs: dict[str, Any]) -> ToolResult:
        segments = inputs.get("segments", [])
        if not segments:
            return ToolResult(success=False, error="No segments provided for concat")

        output_path = Path(inputs.get("output_path", "concat_output.mp4"))

        # Decode every source into one filter graph, trim on decoded timestamps,
        # then encode the complete delivery once. Stream-copying arbitrary cuts
        # can begin before the next video keyframe and silently produce an
        # audio-only segment. It is also unsafe at independently encoded AAC
        # boundaries because of encoder priming and decoder state.
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y"]
        filter_parts: list[str] = []
        concat_inputs: list[str] = []

        for i, seg in enumerate(segments):
            seg_input = Path(seg["input_path"])
            if not seg_input.exists():
                return ToolResult(success=False, error=f"Segment input not found: {seg_input}")

            cmd.extend(["-i", str(seg_input)])
            probe = self._probe_media(seg_input)
            has_audio = any(
                stream.get("codec_type") == "audio"
                for stream in probe.get("streams", [])
            )
            source_duration = self._media_duration(probe)
            seg_start = seg.get("start_seconds")
            seg_end = seg.get("end_seconds")
            effective_start = float(seg_start or 0)
            effective_end = float(seg_end) if seg_end is not None else source_duration
            segment_duration = max(0.0, effective_end - effective_start)
            trim_args: list[str] = []
            atrim_args: list[str] = []
            if seg_start is not None:
                trim_args.append(f"start={seg_start}")
                atrim_args.append(f"start={seg_start}")
            if seg_end is not None:
                trim_args.append(f"end={seg_end}")
                atrim_args.append(f"end={seg_end}")

            video_trim = f"trim={':'.join(trim_args)}," if trim_args else ""
            audio_trim = f"atrim={':'.join(atrim_args)}," if atrim_args else ""
            filter_parts.append(
                f"[{i}:v:0]{video_trim}setpts=PTS-STARTPTS[v{i}]"
            )
            if has_audio:
                filter_parts.append(
                    f"[{i}:a:0]{audio_trim}asetpts=PTS-STARTPTS,"
                    f"aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo[a{i}]"
                )
            else:
                filter_parts.append(
                    f"anullsrc=r=48000:cl=stereo,atrim=duration={segment_duration},"
                    f"asetpts=PTS-STARTPTS[a{i}]"
                )
            concat_inputs.extend([f"[v{i}]", f"[a{i}]"])

        filter_parts.append(
            f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=1[outv][outa]"
        )
        cmd.extend([
            "-filter_complex", ";".join(filter_parts),
            "-map", "[outv]", "-map", "[outa]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(output_path),
        ])
        # A single encode leaves no temporary workspace behind. If it fails,
        # remove only the partial output this call created, then surface the
        # original error unchanged.
        existed = output_path.exists()
        try:
            self.run_command(cmd)
        except Exception:
            if not existed and output_path.exists():
                output_path.unlink()
            raise

        return ToolResult(
            success=True,
            data={
                "operation": "concat",
                "segment_count": len(segments),
                "output": str(output_path),
                "audio_method": "continuous_aac_encode",
                "video_method": "decoded_trim_single_encode",
            },
            artifacts=[str(output_path)],
        )

    @staticmethod
    def _build_atempo_chain(factor: float) -> str:
        """Build an atempo filter chain. atempo only accepts [0.5, 100.0]."""
        if factor <= 0:
            factor = 1.0
        # Chain multiple atempo filters for extreme values
        filters = []
        remaining = factor
        while remaining > 100.0:
            filters.append("atempo=100.0")
            remaining /= 100.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.4f}")
        return ",".join(filters)
