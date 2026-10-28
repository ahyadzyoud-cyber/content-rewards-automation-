"""Local, deterministic short-form editing using free FFmpeg tools.

This editor does not generate footage or grant reuse rights. Callers must verify
the source's campaign-specific editing and publication permissions first.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class MediaError(ValueError):
    """A source or render cannot satisfy the required video format."""


def _run(arguments: list[str], timeout: int = 180) -> str:
    if not shutil.which(arguments[0]):
        raise MediaError(f"Required executable is unavailable: {arguments[0]}")
    try:
        result = subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaError("Media operation exceeded its time limit") from exc
    if result.returncode:
        # Never echo untrusted metadata or source contents into application logs.
        raise MediaError(f"{arguments[0]} failed; check that the local video is decodable")
    return result.stdout


def _local_source(path: Path) -> Path:
    value = str(path)
    if "://" in value or value.startswith(("file:", "pipe:", "http:", "https:")):
        raise MediaError("Only local video files are supported")
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise MediaError("Source video does not exist or is not a regular file")
    return resolved


def inspect_video(path: Path) -> dict[str, Any]:
    """Inspect a local video without allowing network-backed input protocols."""
    source = _local_source(path)
    raw = _run(
        [
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-show_streams", "-show_format", "-of", "json", str(source),
        ],
        timeout=30,
    )
    try:
        data = json.loads(raw)
        video = next(stream for stream in data["streams"] if stream.get("codec_type") == "video")
        audio = next((stream for stream in data["streams"] if stream.get("codec_type") == "audio"), {})
        duration = float(data.get("format", {}).get("duration", video.get("duration", 0)))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid duration")
        return {
            "path": str(source),
            "width": int(video["width"]),
            "height": int(video["height"]),
            "duration_seconds": duration,
            "video_codec": video.get("codec_name"),
            "audio_codec": audio.get("codec_name"),
            "pixel_format": video.get("pix_fmt"),
            "frame_rate": video.get("avg_frame_rate"),
        }
    except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaError("Source must contain a video stream with a known positive duration") from exc


def render_short(
    source: Path,
    output: Path,
    *,
    rights_verified: bool,
    start_seconds: float = 0,
    duration_seconds: float = 30,
    caption: str = "",
) -> dict[str, Any]:
    """Render an approved local source into a portrait MP4 of at most 60 seconds.

    Letterboxing preserves source content. Captions are literal text and FFmpeg
    expression expansion is disabled. The destination must not already exist.
    Silent input receives an AAC silence track for publishing compatibility.
    """
    if rights_verified is not True:
        raise MediaError("Campaign material rights must be verified before rendering")
    if (
        isinstance(start_seconds, bool)
        or isinstance(duration_seconds, bool)
        or not isinstance(start_seconds, (int, float))
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(start_seconds)
        or not math.isfinite(duration_seconds)
        or start_seconds < 0
        or not 0 < duration_seconds <= 60
    ):
        raise MediaError("Start must be nonnegative and duration must be between 0 and 60 seconds")
    if not isinstance(caption, str) or len(caption) > 500 or "\x00" in caption:
        raise MediaError("Caption must be text of at most 500 characters without NUL bytes")
    input_path = _local_source(source)
    output_path = Path(output).expanduser().absolute()
    if output_path.suffix.lower() != ".mp4":
        raise MediaError("Destination must use the .mp4 extension")
    if input_path == output_path.resolve():
        raise MediaError("Source and destination must differ")
    if os.path.lexists(output_path):
        raise MediaError("Destination already exists; use a new filename")
    source_info = inspect_video(input_path)
    if start_seconds >= source_info["duration_seconds"]:
        raise MediaError("Start time is beyond the end of the source")
    duration = min(duration_seconds, source_info["duration_seconds"] - start_seconds)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # A separate temporary directory avoids interpreting caller-controlled path
    # characters in filter syntax. FFmpeg runs there with a constant textfile name.
    with tempfile.TemporaryDirectory(prefix="content-rewards-render-") as scratch:
        caption_path = Path(scratch) / "caption.txt"
        caption_path.write_text(caption, encoding="utf-8")
        filter_text = (
            "scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
        )
        if caption:
            # scratch comes from tempfile and contains no user-controlled filter syntax.
            filter_text += (
                f",drawtext=textfile='{caption_path}':expansion=none:"
                "fontcolor=white:fontsize=48:box=1:boxcolor=black@0.65:"
                "boxborderw=16:x=(w-text_w)/2:y=h-text_h-140"
            )
        # Place the completed MP4 on the destination filesystem so the final
        # atomic, no-clobber hard link also works across filesystem boundaries.
        fd, staged_name = tempfile.mkstemp(prefix=".render-", suffix=".mp4", dir=output_path.parent)
        os.close(fd)
        staged = Path(staged_name)
        try:
            command = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-protocol_whitelist", "file,pipe", "-ss", str(start_seconds), "-i", str(input_path),
                "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                "-map", "0:v:0", "-map", "0:a:0" if source_info["audio_codec"] else "1:a:0",
                "-vf", filter_text, "-t", str(duration), "-r", "30", "-c:v", "libx264",
                "-preset", "veryfast", "-crf", "23", "-threads", "2", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-map_metadata", "-1", "-movflags", "+faststart", "-shortest", str(staged),
            ]
            _run(command)
            metadata = inspect_video(staged)
            if (
                metadata["width"] != 1080 or metadata["height"] != 1920
                or metadata["video_codec"] != "h264" or metadata["audio_codec"] != "aac"
                or metadata["pixel_format"] != "yuv420p"
                or metadata["duration_seconds"] > 60.1
            ):
                raise MediaError("Rendered video failed the required format checks")
            try:
                os.link(staged, output_path)
            except FileExistsError as exc:
                raise MediaError("Destination appeared during rendering; it was not overwritten") from exc
            metadata["path"] = str(output_path.resolve())
            return metadata
        finally:
            staged.unlink(missing_ok=True)
