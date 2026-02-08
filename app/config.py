"""Configuration from environment variables."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    # Required
    immich_api_base: str
    immich_api_key: str

    # Core behavior
    dry_run: bool
    concurrency: int
    max_assets: int = 0  # 0 = unlimited

    # Filtering
    asset_types: tuple[str, ...] = ("IMAGE", "VIDEO")
    include_archived: bool = False
    include_deleted: bool = False
    filter_date_after: str | None = None  # YYYY-MM-DD or ISO
    filter_date_before: str | None = None  # YYYY-MM-DD or ISO

    # Image encoding (JXL distance: 0=lossless, 1=visually lossless, higher=more compression)
    # Used by ImageMagick for non-JPEG images. JPEGs use cjxl lossless.
    image_distance: float = 1.0
    image_distance_retry: float = 2.0

    # Video encoding (SVT-AV1)
    video_crf: int = 36           # 0-63, lower=better quality
    video_preset: str = "4"       # 0-13, lower=slower/better quality
    video_max_dimension: int = 0  # 0=no scaling, else limits shorter side
    video_audio_bitrate: str = "64k"
    video_crf_retry: int = 40

    # Retry behavior
    enable_retry: bool = True
    accept_retry_output: bool = False

    # Safety
    allow_larger: bool = False

    # Paths
    workdir: str = "/work"

    @classmethod
    def from_env(cls) -> "Config":
        immich_api_base = os.environ.get("IMMICH_API_BASE", "")
        if not immich_api_base:
            raise ValueError("IMMICH_API_BASE is required")
        immich_api_key = os.environ.get("IMMICH_API_KEY", "")
        if not immich_api_key:
            raise ValueError("IMMICH_API_KEY is required")

        if not immich_api_base.endswith("/"):
            immich_api_base += "/"

        # Core behavior
        dry_run = _parse_bool("DRY_RUN", default=True)
        concurrency = _parse_int("CONCURRENCY", default=1, min=1)
        max_assets = _parse_int("MAX_ASSETS", default=0, min=0)

        # Asset types (default: both)
        asset_types_str = os.environ.get("ASSET_TYPES", "").strip()
        if asset_types_str:
            asset_types_list = [t.strip().upper() for t in asset_types_str.split(",") if t.strip()]
            valid_types = {"IMAGE", "VIDEO"}
            invalid_types = set(asset_types_list) - valid_types
            if invalid_types:
                raise ValueError(f"Invalid ASSET_TYPES values: {invalid_types}. Valid: IMAGE, VIDEO")
            asset_types = tuple(asset_types_list)
        else:
            asset_types = ("IMAGE", "VIDEO")

        # Filtering
        include_archived = _parse_bool("INCLUDE_ARCHIVED", default=False)
        include_deleted = _parse_bool("INCLUDE_DELETED", default=False)
        filter_date_after = _parse_date("FILTER_DATE_AFTER")
        filter_date_before = _parse_date("FILTER_DATE_BEFORE")

        # Image encoding
        image_distance = _parse_float("IMAGE_DISTANCE", default=1.0, min=0.0, max=25.0)
        image_distance_retry = _parse_float("IMAGE_DISTANCE_RETRY", default=2.0, min=0.0, max=25.0)

        # Video encoding
        video_crf = _parse_int("VIDEO_CRF", default=36, min=0, max=63)
        video_preset = str(_parse_int("VIDEO_PRESET", default=4, min=0, max=13))
        video_max_dimension = _parse_int("VIDEO_MAX_DIMENSION", default=0, min=0)
        video_audio_bitrate = os.environ.get("VIDEO_AUDIO_BITRATE", "64k").strip() or "64k"
        video_crf_retry = _parse_int("VIDEO_CRF_RETRY", default=40, min=0, max=63)

        # Retry behavior
        enable_retry = _parse_bool("ENABLE_RETRY", default=True)
        accept_retry_output = _parse_bool("ACCEPT_RETRY_OUTPUT", default=False)

        # Safety
        allow_larger = _parse_bool("ALLOW_LARGER", default=False)

        # Paths
        workdir = os.environ.get("WORKDIR", "/work").strip() or "/work"

        return cls(
            immich_api_base=immich_api_base,
            immich_api_key=immich_api_key,
            dry_run=dry_run,
            concurrency=concurrency,
            max_assets=max_assets,
            asset_types=asset_types,
            include_archived=include_archived,
            include_deleted=include_deleted,
            filter_date_after=filter_date_after,
            filter_date_before=filter_date_before,
            image_distance=image_distance,
            image_distance_retry=image_distance_retry,
            video_crf=video_crf,
            video_preset=video_preset,
            video_max_dimension=video_max_dimension,
            video_audio_bitrate=video_audio_bitrate,
            video_crf_retry=video_crf_retry,
            enable_retry=enable_retry,
            accept_retry_output=accept_retry_output,
            allow_larger=allow_larger,
            workdir=workdir,
        )

    def input_dir(self) -> str:
        return f"{self.workdir}/in"

    def output_dir(self) -> str:
        return f"{self.workdir}/out"


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    logger.warning("Invalid boolean value for %s: '%s', using default %s", name, raw, default)
    return default


def _parse_int(name: str, default: int, min: int | None = None, max: int | None = None) -> int:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        int_value = int(value)
        if min is not None and int_value < min:
            raise ValueError(f"{name} must be >= {min}, got {int_value}")
        if max is not None and int_value > max:
            raise ValueError(f"{name} must be <= {max}, got {int_value}")
        return int_value
    except ValueError as e:
        if "invalid literal" in str(e):
            raise ValueError(f"Invalid integer value for {name}: {value}") from e
        raise


def _parse_float(name: str, default: float, min: float | None = None, max: float | None = None) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    try:
        float_value = float(value)
        if min is not None and float_value < min:
            raise ValueError(f"{name} must be >= {min}, got {float_value}")
        if max is not None and float_value > max:
            raise ValueError(f"{name} must be <= {max}, got {float_value}")
        return float_value
    except ValueError as e:
        if "could not convert" in str(e).lower():
            raise ValueError(f"Invalid float value for {name}: {value}") from e
        raise


def _parse_date(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None

    # YYYY-MM-DD -> ISO format with time
    if len(value) == 10 and value.count("-") == 2:
        try:
            year, month, day = value.split("-")
            datetime(int(year), int(month), int(day))
            if "BEFORE" in name:
                return f"{value}T23:59:59.999Z"
            return f"{value}T00:00:00.000Z"
        except ValueError as e:
            raise ValueError(f"Invalid date for {name}: {value}. Use YYYY-MM-DD.") from e

    # Accept ISO 8601 strings (must start with a valid date)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid date for {name}: {value}. Use YYYY-MM-DD or ISO 8601.") from e

    return value
