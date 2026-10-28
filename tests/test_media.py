import shutil
import subprocess
from pathlib import Path

import pytest

from content_rewards.media import MediaError, inspect_video, render_short


@pytest.fixture
def source_video(tmp_path: Path) -> Path:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg and ffprobe are required for media integration tests")
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "color=c=blue:s=320x180:r=30", "-t", "0.4", "-c:v", "libx264",
            "-pix_fmt", "yuv420p", str(source),
        ],
        check=True, timeout=30,
    )
    return source


def test_real_render_preserves_literal_caption_and_adds_audio(source_video: Path, tmp_path: Path):
    output = tmp_path / "short.mp4"
    result = render_short(
        source_video, output, rights_verified=True, duration_seconds=0.2,
        caption="Approved clip: 100% %{metadata:secret} ' [test]",
    )
    assert result["path"] == str(output)
    assert result["width"] == 1080 and result["height"] == 1920
    assert result["video_codec"] == "h264"
    assert result["audio_codec"] == "aac"
    assert result["pixel_format"] == "yuv420p"
    assert result["frame_rate"] == "30/1"
    assert 0 < result["duration_seconds"] < 0.4
    assert inspect_video(output)["width"] == 1080
    assert not list(tmp_path.glob(".render-*"))


def test_rights_are_required_before_any_media_work(tmp_path: Path):
    with pytest.raises(MediaError, match="rights"):
        render_short(tmp_path / "missing.mp4", tmp_path / "output.mp4", rights_verified=False)


@pytest.mark.parametrize("kwargs", [
    {"duration_seconds": 0}, {"duration_seconds": 61}, {"duration_seconds": float("nan")},
    {"start_seconds": -1}, {"start_seconds": float("inf")}, {"duration_seconds": True},
    {"caption": "\x00"},
])
def test_invalid_arguments_are_rejected(tmp_path: Path, kwargs: dict):
    with pytest.raises(MediaError):
        render_short(tmp_path / "source.mp4", tmp_path / "output.mp4", rights_verified=True, **kwargs)


def test_missing_source_is_rejected(tmp_path: Path):
    with pytest.raises(MediaError, match="does not exist"):
        render_short(tmp_path / "missing.mp4", tmp_path / "output.mp4", rights_verified=True)


def test_never_overwrites_source_or_destination(source_video: Path, tmp_path: Path):
    before = source_video.read_bytes()
    with pytest.raises(MediaError, match="differ"):
        render_short(source_video, source_video, rights_verified=True)
    destination = tmp_path / "already.mp4"
    destination.write_bytes(b"preserve")
    with pytest.raises(MediaError, match="already exists"):
        render_short(source_video, destination, rights_verified=True)
    assert source_video.read_bytes() == before
    assert destination.read_bytes() == b"preserve"


def test_start_beyond_end_is_rejected(source_video: Path, tmp_path: Path):
    with pytest.raises(MediaError, match="beyond"):
        render_short(source_video, tmp_path / "out.mp4", rights_verified=True, start_seconds=5)


def test_protocol_source_is_rejected(tmp_path: Path):
    with pytest.raises(MediaError, match="Only local"):
        render_short("https://example.com/clip.mp4", tmp_path / "out.mp4", rights_verified=True)
