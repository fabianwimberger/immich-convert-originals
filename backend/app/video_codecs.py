"""Single source of truth for the video codec lists and HEVC defaults.

Imports nothing from models/ or services/, so any layer can use it. The
frontend keeps its own copies of SOURCE_VIDEO_CODECS and X265_PRESETS for
rendering; tests/test_video_codecs.py fails if they drift from these.
"""

# Source codecs the allow-list can name. "other" is not an ffprobe codec name:
# it is the bucket for any codec not listed before it.
SOURCE_VIDEO_CODECS = (
    "h264",
    "hevc",
    "av1",
    "vp9",
    "vp8",
    "mpeg4",
    "mjpeg",
    "prores",
    "other",
)

# Every source codec, comma-joined: the Settings default, and the fallback for
# a config_snapshot saved before the allow-list existed.
DEFAULT_CONVERT_VIDEO_CODECS = ",".join(SOURCE_VIDEO_CODECS)

X265_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
    "placebo",
)

# HEVC quality defaults (x265 CRF is 0-51, a different scale from AV1's 0-63).
DEFAULT_HEVC_CRF = 26
DEFAULT_HEVC_CRF_RETRY = 30
DEFAULT_HEVC_PRESET = "slow"


def source_codec_bucket(codec_name: str) -> str:
    """The allow-list entry an ffprobe codec name falls under."""
    return codec_name if codec_name in SOURCE_VIDEO_CODECS else "other"
