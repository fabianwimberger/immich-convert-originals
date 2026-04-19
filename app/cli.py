"""Command-line interface for immich-convert-originals."""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def _positive_int(value: str) -> int:
    iv = int(value)
    if iv < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {iv}")
    return iv


def _non_negative_float(value: str) -> float:
    fv = float(value)
    if fv < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {fv}")
    return fv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="immich-convert-originals",
        description="Batch-transcode Immich library assets to JPEG XL and AV1.",
    )

    # Connection
    parser.add_argument(
        "--immich-api-base",
        "--api-base",
        help="Immich API base URL (env: IMMICH_API_BASE)",
    )
    parser.add_argument(
        "--immich-api-key",
        "--api-key",
        help="Immich API key (env: IMMICH_API_KEY)",
    )

    # Core behavior
    parser.add_argument(
        "--dry-run",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Preview changes without executing (default: true from env)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Number of parallel workers (env: CONCURRENCY)",
    )
    parser.add_argument(
        "--max-assets",
        type=_positive_int,
        help="Maximum assets to process, 0 = unlimited (env: MAX_ASSETS)",
    )

    # Filtering
    parser.add_argument(
        "--asset-types",
        help="Comma-separated asset types: IMAGE, VIDEO (env: ASSET_TYPES)",
    )
    parser.add_argument(
        "--include-archived",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Include archived assets (env: INCLUDE_ARCHIVED)",
    )
    parser.add_argument(
        "--include-deleted",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Include deleted assets (env: INCLUDE_DELETED)",
    )
    parser.add_argument(
        "--filter-date-after",
        help="Only process assets after this date (env: FILTER_DATE_AFTER)",
    )
    parser.add_argument(
        "--filter-date-before",
        help="Only process assets before this date (env: FILTER_DATE_BEFORE)",
    )
    parser.add_argument(
        "--filter-album-id",
        help="Only process assets in this album UUID (env: FILTER_ALBUM_ID)",
    )

    # Image encoding
    parser.add_argument(
        "--image-distance",
        type=_non_negative_float,
        help="JXL distance: 0=lossless, 1=visually lossless (env: IMAGE_DISTANCE)",
    )
    parser.add_argument(
        "--image-distance-retry",
        type=_non_negative_float,
        help="JXL distance for retry if output is larger (env: IMAGE_DISTANCE_RETRY)",
    )

    # Video encoding
    parser.add_argument(
        "--video-crf",
        type=int,
        help="AV1 quality 0-63, lower=better (env: VIDEO_CRF)",
    )
    parser.add_argument(
        "--video-preset",
        type=int,
        help="AV1 speed preset 0-13, lower=slower (env: VIDEO_PRESET)",
    )
    parser.add_argument(
        "--video-max-dimension",
        type=_positive_int,
        help="Max shorter-side dimension, 0=disable (env: VIDEO_MAX_DIMENSION)",
    )
    parser.add_argument(
        "--video-audio-bitrate",
        help="Audio bitrate for Opus (env: VIDEO_AUDIO_BITRATE)",
    )
    parser.add_argument(
        "--video-crf-retry",
        type=int,
        help="AV1 CRF for retry if output is larger (env: VIDEO_CRF_RETRY)",
    )

    # Retry behavior
    parser.add_argument(
        "--enable-retry",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Retry with looser settings if output is larger (env: ENABLE_RETRY)",
    )
    parser.add_argument(
        "--accept-retry-output",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Accept retry output even if still larger (env: ACCEPT_RETRY_OUTPUT)",
    )

    # Safety
    parser.add_argument(
        "--allow-larger",
        default=None,
        action=argparse.BooleanOptionalAction,
        help="Allow output larger than input without retry (env: ALLOW_LARGER)",
    )

    # Paths
    parser.add_argument(
        "--workdir",
        help="Working directory for downloads and outputs (env: WORKDIR)",
    )

    # Logging
    parser.add_argument(
        "--log-level",
        choices=["debug", "info", "warning", "error"],
        help="Console log level",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        help="Log output format",
    )

    # Interaction
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Run interactive wizard",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Auto-confirm interactive prompts",
    )

    # Output
    parser.add_argument(
        "--stats-json",
        metavar="PATH",
        help="Write machine-readable summary to PATH",
    )

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(argv)


class JsonFormatter(logging.Formatter):
    """Simple JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging(level: str = "info", fmt: str = "text") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    if fmt == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers = [handler]
