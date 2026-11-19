"""Real ffmpeg: H.264 fixture -> HEVC/AV1, checked with ffprobe."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.services.transcode import transcode_video, validate_video_output

FIXTURE = Path(__file__).parent / "integration" / "fixtures" / "sample-h264.mp4"


def _encoders() -> str:
    if not shutil.which("ffmpeg"):
        return ""
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True
    ).stdout


def _streams(path: Path) -> dict[str, dict]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return {s["codec_type"]: s for s in json.loads(out)["streams"]}


@pytest.mark.skipif("libx265" not in _encoders(), reason="ffmpeg without libx265")
def test_h264_to_hevc_is_tagged_hvc1_with_aac_audio(tmp_path):
    out = tmp_path / "out.mp4"

    result = transcode_video(
        str(FIXTURE), str(out), 28, "ultrafast", 0, "96k", codec="hevc"
    )

    assert result.success, result.error
    assert validate_video_output(str(out))
    streams = _streams(out)
    assert streams["video"]["codec_name"] == "hevc"
    assert streams["video"]["codec_tag_string"] == "hvc1"
    assert streams["video"]["pix_fmt"] == "yuv420p"
    assert streams["audio"]["codec_name"] == "aac"


@pytest.mark.skipif("libx265" not in _encoders(), reason="ffmpeg without libx265")
def test_hevc_output_is_skipped_on_a_second_pass(tmp_path):
    first = tmp_path / "first.mp4"
    transcode_video(str(FIXTURE), str(first), 28, "ultrafast", 0, "96k", codec="hevc")

    again = transcode_video(
        str(first), str(tmp_path / "again.mp4"), 28, "ultrafast", 0, "96k", codec="hevc"
    )

    assert again.success is False
    assert again.error == "Already HEVC"


@pytest.mark.skipif("libsvtav1" not in _encoders(), reason="ffmpeg without libsvtav1")
def test_h264_to_av1_still_uses_opus(tmp_path):
    out = tmp_path / "out.mp4"

    result = transcode_video(str(FIXTURE), str(out), 40, "10", 0, "64k")

    assert result.success, result.error
    streams = _streams(out)
    assert streams["video"]["codec_name"] == "av1"
    assert streams["audio"]["codec_name"] == "opus"
