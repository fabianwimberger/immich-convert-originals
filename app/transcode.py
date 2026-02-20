"""Transcoding pipeline for JPEG XL and video conversion."""

import logging
import os
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Subprocess timeouts (seconds)
IMAGE_TIMEOUT = 600  # 10 minutes for image transcoding (cjxl, magick)
VIDEO_TIMEOUT = 43200  # 12 hours for video transcoding (ffmpeg)
PROBE_TIMEOUT = 60  # 1 minute for ffprobe
METADATA_TIMEOUT = 120  # 2 minutes for exiftool

# Unambiguous magic byte signatures.
# Ambiguous formats (RIFF, ftyp-based) are resolved in detect_format().
MAGIC_BYTES = {
    b"\x00\x00\x00\x0c\x4a\x58\x4c\x20\x0d\x0a\x87\x0a": "jxl",  # ISOBMFF container
    b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a": "png",
    b"\xff\xd8\xff": "jpg",
    b"\xff\x0a": "jxl",  # Bare codestream
    b"\x49\x49\x2a\x00": "tiff",  # Little-endian TIFF
    b"\x4d\x4d\x00\x2a": "tiff",  # Big-endian TIFF
    b"\x47\x49\x46\x38": "gif",  # GIF87a or GIF89a
    b"\x42\x4d": "bmp",
}


@dataclass(frozen=True)
class TranscodeResult:
    success: bool
    input_path: str
    output_path: str
    input_bytes: int
    output_bytes: int
    input_format: str
    error: str | None = None


def detect_format(path: str) -> str | None:
    """Detect image or video format from magic bytes."""
    try:
        with open(path, "rb") as f:
            header = f.read(32)

        for magic, fmt in MAGIC_BYTES.items():
            if header.startswith(magic):
                return fmt

        # RIFF container: WebP or AVI
        if header.startswith(b"\x52\x49\x46\x46") and len(header) >= 12:
            if header[8:12] in (b"WEBP", b"WEBX"):
                return "webp"
            if header[8:12] == b"AVI ":
                return "avi"

        # Matroska / WebM
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            return "mkv"

        # ftyp-based containers: HEIC, AVIF, or video (MP4/MOV)
        if len(header) >= 12 and header[4:8] == b"ftyp":
            brand = header[8:12].decode("ascii", errors="ignore").lower()
            if brand in ("heic", "heix", "mif1", "msf1"):
                return "heic"
            if brand in ("avif", "avis"):
                return "avif"
            return "mp4"

        # Older QuickTime without ftyp
        if len(header) >= 8:
            atom_type = header[4:8]
            if atom_type in (b"moov", b"mdat", b"wide", b"skip", b"free", b"pnot"):
                return "mp4"

        return None
    except OSError:
        return None


def detect_video_codec(path: str) -> str | None:
    """Detect video codec using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
        if result.returncode == 0:
            codec = result.stdout.strip().lower()
            return codec if codec else None
        return None
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out detecting codec for %s", path)
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def validate_output(path: str, expected_format: str) -> bool:
    """Validate output file exists, is non-zero, and has correct magic bytes."""
    if not os.path.exists(path):
        return False
    if os.path.getsize(path) == 0:
        return False
    return detect_format(path) == expected_format


def copy_metadata(source_path: str, dest_path: str) -> bool:
    """Copy EXIF/XMP metadata from source to dest using exiftool."""
    try:
        subprocess.run(
            [
                "exiftool",
                "-overwrite_original",
                "-tagsFromFile",
                source_path,
                dest_path,
            ],
            capture_output=True,
            check=True,
            timeout=METADATA_TIMEOUT,
        )
        return True
    except subprocess.TimeoutExpired:
        logger.warning("exiftool timed out copying metadata from %s", source_path)
        return False
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _transcode_with_magick(
    input_path: str, output_path: str, distance: float
) -> TranscodeResult:
    """Transcode using ImageMagick with specified JXL distance."""
    input_bytes = os.path.getsize(input_path)
    input_format = detect_format(input_path)

    cmd = [
        "magick",
        input_path,
        "-define",
        f"jxl:distance={distance}",
        output_path,
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=IMAGE_TIMEOUT)
        if not copy_metadata(input_path, output_path):
            logger.warning(
                "Failed to copy metadata for %s, file EXIF may be incomplete",
                input_path,
            )

        output_bytes = (
            os.path.getsize(output_path) if os.path.exists(output_path) else 0
        )
        return TranscodeResult(
            success=True,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            input_format=input_format or "unknown",
        )
    except subprocess.TimeoutExpired:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=input_format or "unknown",
            error=f"ImageMagick timed out after {IMAGE_TIMEOUT}s",
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=input_format or "unknown",
            error=f"ImageMagick failed: {stderr}",
        )
    except FileNotFoundError:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=input_format or "unknown",
            error="magick not found",
        )


def transcode(
    input_path: str,
    output_path: str,
    distance: float,
) -> TranscodeResult:
    """Transcode an image to JPEG XL.

    JPEG: cjxl lossless repack (distance ignored - always lossless).
    Other formats: ImageMagick with configured distance.
    """
    input_bytes = os.path.getsize(input_path)
    input_format = detect_format(input_path)

    if not input_format:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format="unknown",
            error="Could not detect input format",
        )

    if input_format == "jxl":
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=input_bytes,
            input_format=input_format,
            error="Already JXL",
        )

    is_jpeg = input_format == "jpg"

    if is_jpeg:
        # JPEG: Use cjxl for lossless repack (no distance parameter)
        try:
            result = subprocess.run(
                ["cjxl", input_path, output_path],
                capture_output=True,
                timeout=IMAGE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return TranscodeResult(
                success=False,
                input_path=input_path,
                output_path=output_path,
                input_bytes=input_bytes,
                output_bytes=0,
                input_format=input_format,
                error=f"cjxl timed out after {IMAGE_TIMEOUT}s",
            )
        except FileNotFoundError:
            # cjxl not installed - fall back to ImageMagick
            return _transcode_with_magick(input_path, output_path, distance)

        if result.returncode == 0:
            output_bytes = (
                os.path.getsize(output_path) if os.path.exists(output_path) else 0
            )
            return TranscodeResult(
                success=True,
                input_path=input_path,
                output_path=output_path,
                input_bytes=input_bytes,
                output_bytes=output_bytes,
                input_format=input_format,
            )
        else:
            # cjxl failed (e.g., progressive JPEG) - fall back to ImageMagick
            return _transcode_with_magick(input_path, output_path, distance)
    else:
        # Non-JPEG: Use ImageMagick directly with configured distance
        return _transcode_with_magick(input_path, output_path, distance)


def transcode_video(
    input_path: str,
    output_path: str,
    crf: int,
    preset: str,
    max_dimension: int,
    audio_bitrate: str,
) -> TranscodeResult:
    """Transcode a video to MP4/AV1 using ffmpeg + SVT-AV1.

    Args:
        crf: Quality (0-63, lower=better)
        preset: Speed preset (0-13, lower=slower/better)
        max_dimension: Maximum dimension for the shorter side (width or height).
                       Set to 0 to disable scaling. Portrait videos will have their
                       width limited to this value, landscape videos will have their
                       height limited. Aspect ratio is always preserved.
        audio_bitrate: Audio bitrate for Opus encoder
    """
    input_bytes = os.path.getsize(input_path)

    current_codec = detect_video_codec(input_path)
    if current_codec is None:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format="unknown",
            error="Could not detect video codec",
        )

    if current_codec == "av1":
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=input_bytes,
            input_format=current_codec,
            error="Already AV1",
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-c:v",
        "libsvtav1",
        "-crf",
        str(crf),
        "-preset",
        preset,
    ]

    if max_dimension > 0:
        # Scale based on the shorter side (min of width/height)
        # This ensures portrait videos get proper resolution (e.g., 1080x1920 instead of 607x1080)
        scale_filter = (
            f"scale='trunc(if(gt(min(iw,ih),{max_dimension}),iw*{max_dimension}/min(iw,ih),iw)/2)*2':"
            f"'trunc(if(gt(min(iw,ih),{max_dimension}),ih*{max_dimension}/min(iw,ih),ih)/2)*2'"
        )
        cmd.extend(["-vf", scale_filter])

    cmd.extend(
        [
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "libopus",
            "-b:a",
            audio_bitrate,
            "-map_metadata",
            "0",
            "-movflags",
            "+faststart",
            output_path,
        ]
    )

    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=VIDEO_TIMEOUT)
        output_bytes = (
            os.path.getsize(output_path) if os.path.exists(output_path) else 0
        )
        return TranscodeResult(
            success=True,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            input_format=current_codec,
        )
    except subprocess.TimeoutExpired:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=current_codec,
            error=f"ffmpeg timed out after {VIDEO_TIMEOUT}s",
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode(errors="replace") if e.stderr else ""
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=current_codec,
            error=f"ffmpeg failed: {stderr}",
        )
    except FileNotFoundError:
        return TranscodeResult(
            success=False,
            input_path=input_path,
            output_path=output_path,
            input_bytes=input_bytes,
            output_bytes=0,
            input_format=current_codec,
            error="ffmpeg not found",
        )


def validate_video_output(path: str) -> bool:
    """Validate output video using ffprobe."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
        duration = result.stdout.strip()
        return duration != "N/A" and float(duration) > 0
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out validating %s", path)
        return False
    except (subprocess.SubprocessError, FileNotFoundError, ValueError):
        return False
