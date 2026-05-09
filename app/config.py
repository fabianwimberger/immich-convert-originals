"""Configuration from environment variables and CLI arguments."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
    filter_album_id: str | None = None  # Album UUID to filter by

    # Image encoding (JXL distance: 0=lossless, 1=visually lossless, higher=more compression)
    # Used by ImageMagick for non-JPEG images. JPEGs use cjxl lossless.
    image_distance: float = 1.0
    image_distance_retry: float = 2.0

    # Video encoding (SVT-AV1)
    video_crf: int = 36  # 0-63, lower=better quality
    video_preset: str = "4"  # 0-13, lower=slower/better quality
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

    # State / resumability
    use_state: bool = True
    reset_state: bool = False
    only_failed: bool = False
    export_failures: str | None = None

    def state_db_path(self) -> str:
        return os.path.join(self.workdir, "state.db")

    @classmethod
    def from_env(cls) -> "Config":
        values = _read_env_values()
        return cls._from_values(values)

    @classmethod
    def from_args_and_env(cls, args: Any) -> "Config":
        values = _read_env_values()

        if args is not None:
            # Connection
            if getattr(args, "immich_api_base", None) is not None:
                values["immich_api_base"] = args.immich_api_base
            if getattr(args, "immich_api_key", None) is not None:
                values["immich_api_key"] = args.immich_api_key

            # Core behavior
            if args.dry_run is not None:
                values["dry_run"] = args.dry_run
            if args.concurrency is not None:
                values["concurrency"] = args.concurrency
            if args.max_assets is not None:
                values["max_assets"] = args.max_assets

            # Filtering
            if args.asset_types is not None:
                values["asset_types_str"] = args.asset_types
            if args.include_archived is not None:
                values["include_archived"] = args.include_archived
            if args.include_deleted is not None:
                values["include_deleted"] = args.include_deleted
            if args.filter_date_after is not None:
                values["filter_date_after"] = args.filter_date_after
            if args.filter_date_before is not None:
                values["filter_date_before"] = args.filter_date_before
            if args.filter_album_id is not None:
                values["filter_album_id"] = args.filter_album_id

            # Image encoding
            if args.image_distance is not None:
                values["image_distance"] = args.image_distance
            if args.image_distance_retry is not None:
                values["image_distance_retry"] = args.image_distance_retry

            # Video encoding
            if args.video_crf is not None:
                values["video_crf"] = args.video_crf
            if args.video_preset is not None:
                values["video_preset"] = str(args.video_preset)
            if args.video_max_dimension is not None:
                values["video_max_dimension"] = args.video_max_dimension
            if args.video_audio_bitrate is not None:
                values["video_audio_bitrate"] = args.video_audio_bitrate
            if args.video_crf_retry is not None:
                values["video_crf_retry"] = args.video_crf_retry

            # Retry behavior
            if args.enable_retry is not None:
                values["enable_retry"] = args.enable_retry
            if args.accept_retry_output is not None:
                values["accept_retry_output"] = args.accept_retry_output

            # Safety
            if args.allow_larger is not None:
                values["allow_larger"] = args.allow_larger

            # Paths
            if args.workdir is not None:
                values["workdir"] = args.workdir

            # State / resumability
            if getattr(args, "no_state", None) is not None:
                values["use_state"] = not args.no_state
            if getattr(args, "reset_state", None):
                values["reset_state"] = True
            if getattr(args, "only_failed", None):
                values["only_failed"] = True
            if getattr(args, "export_failures", None) is not None:
                values["export_failures"] = args.export_failures

        return cls._from_values(values)

    @classmethod
    def _from_values(cls, values: dict[str, Any]) -> "Config":
        immich_api_base = values["immich_api_base"]
        if not immich_api_base:
            raise ValueError("IMMICH_API_BASE is required")
        immich_api_key = values["immich_api_key"]
        if not immich_api_key:
            raise ValueError("IMMICH_API_KEY is required")

        if not immich_api_base.endswith("/"):
            immich_api_base += "/"

        # Core behavior
        dry_run = values["dry_run"]
        concurrency = values["concurrency"]
        max_assets = values["max_assets"]

        # Asset types
        asset_types_str = values.get("asset_types_str", "")
        if asset_types_str:
            asset_types_list = [
                t.strip().upper() for t in asset_types_str.split(",") if t.strip()
            ]
            valid_types = {"IMAGE", "VIDEO"}
            invalid_types = set(asset_types_list) - valid_types
            if invalid_types:
                raise ValueError(
                    f"Invalid ASSET_TYPES values: {invalid_types}. Valid: IMAGE, VIDEO"
                )
            asset_types = tuple(asset_types_list)
        else:
            asset_types = ("IMAGE", "VIDEO")

        # Filtering
        include_archived = values["include_archived"]
        include_deleted = values["include_deleted"]
        filter_date_after = _parse_date_value(
            values.get("filter_date_after") or "", before=False
        )
        filter_date_before = _parse_date_value(
            values.get("filter_date_before") or "", before=True
        )
        filter_album_id = values.get("filter_album_id")

        # Image encoding
        image_distance = values["image_distance"]
        image_distance_retry = values["image_distance_retry"]

        # Video encoding
        video_crf = values["video_crf"]
        video_preset = values["video_preset"]
        video_max_dimension = values["video_max_dimension"]
        video_audio_bitrate = values["video_audio_bitrate"]
        video_crf_retry = values["video_crf_retry"]

        # Retry behavior
        enable_retry = values["enable_retry"]
        accept_retry_output = values["accept_retry_output"]

        # Safety
        allow_larger = values["allow_larger"]

        # Paths
        workdir = values["workdir"]

        # State
        use_state = values["use_state"]
        reset_state = values["reset_state"]
        only_failed = values["only_failed"]
        export_failures = values.get("export_failures")

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
            filter_album_id=filter_album_id,
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
            use_state=use_state,
            reset_state=reset_state,
            only_failed=only_failed,
            export_failures=export_failures,
        )

    def input_dir(self) -> str:
        return f"{self.workdir}/in"

    def output_dir(self) -> str:
        return f"{self.workdir}/out"


def _read_env_values() -> dict[str, Any]:
    """Read all configuration values from environment variables."""
    immich_api_base = os.environ.get("IMMICH_API_BASE", "")
    immich_api_key = os.environ.get("IMMICH_API_KEY", "")

    dry_run = _parse_bool("DRY_RUN", default=True)
    concurrency = _parse_int("CONCURRENCY", default=1, min=1)
    max_assets = _parse_int("MAX_ASSETS", default=0, min=0)

    asset_types_str = os.environ.get("ASSET_TYPES", "").strip()

    include_archived = _parse_bool("INCLUDE_ARCHIVED", default=False)
    include_deleted = _parse_bool("INCLUDE_DELETED", default=False)
    filter_date_after = os.environ.get("FILTER_DATE_AFTER", "").strip() or None
    filter_date_before = os.environ.get("FILTER_DATE_BEFORE", "").strip() or None
    filter_album_id = os.environ.get("FILTER_ALBUM_ID", "").strip() or None

    image_distance = _parse_float("IMAGE_DISTANCE", default=1.0, min=0.0, max=25.0)
    image_distance_retry = _parse_float(
        "IMAGE_DISTANCE_RETRY", default=2.0, min=0.0, max=25.0
    )

    video_crf = _parse_int("VIDEO_CRF", default=36, min=0, max=63)
    video_preset = str(_parse_int("VIDEO_PRESET", default=4, min=0, max=13))
    video_max_dimension = _parse_int("VIDEO_MAX_DIMENSION", default=0, min=0)
    video_audio_bitrate = os.environ.get("VIDEO_AUDIO_BITRATE", "64k").strip() or "64k"
    video_crf_retry = _parse_int("VIDEO_CRF_RETRY", default=40, min=0, max=63)

    enable_retry = _parse_bool("ENABLE_RETRY", default=True)
    accept_retry_output = _parse_bool("ACCEPT_RETRY_OUTPUT", default=False)

    allow_larger = _parse_bool("ALLOW_LARGER", default=False)

    workdir = os.environ.get("WORKDIR", "/work").strip() or "/work"

    use_state = _parse_bool("USE_STATE", default=True)
    reset_state = _parse_bool("RESET_STATE", default=False)
    only_failed = _parse_bool("ONLY_FAILED", default=False)
    export_failures = os.environ.get("EXPORT_FAILURES", "").strip() or None

    return {
        "immich_api_base": immich_api_base,
        "immich_api_key": immich_api_key,
        "dry_run": dry_run,
        "concurrency": concurrency,
        "max_assets": max_assets,
        "asset_types_str": asset_types_str,
        "include_archived": include_archived,
        "include_deleted": include_deleted,
        "filter_date_after": filter_date_after,
        "filter_date_before": filter_date_before,
        "filter_album_id": filter_album_id,
        "image_distance": image_distance,
        "image_distance_retry": image_distance_retry,
        "video_crf": video_crf,
        "video_preset": video_preset,
        "video_max_dimension": video_max_dimension,
        "video_audio_bitrate": video_audio_bitrate,
        "video_crf_retry": video_crf_retry,
        "enable_retry": enable_retry,
        "accept_retry_output": accept_retry_output,
        "allow_larger": allow_larger,
        "workdir": workdir,
        "use_state": use_state,
        "reset_state": reset_state,
        "only_failed": only_failed,
        "export_failures": export_failures,
    }


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("true", "1", "yes", "on"):
        return True
    if value in ("false", "0", "no", "off"):
        return False
    logger.warning(
        "Invalid boolean value for %s: '%s', using default %s", name, raw, default
    )
    return default


def _parse_int(
    name: str, default: int, min: int | None = None, max: int | None = None
) -> int:
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


def _parse_float(
    name: str, default: float, min: float | None = None, max: float | None = None
) -> float:
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


def _parse_date_value(value: str, before: bool = False) -> str | None:
    if not value:
        return None

    # YYYY-MM-DD -> ISO format with time
    if len(value) == 10 and value.count("-") == 2:
        try:
            year, month, day = value.split("-")
            datetime(int(year), int(month), int(day))
            if before:
                return f"{value}T23:59:59.999Z"
            return f"{value}T00:00:00.000Z"
        except ValueError as e:
            raise ValueError(
                f"Invalid date: {value}. Use YYYY-MM-DD or ISO 8601."
            ) from e

    # Accept ISO 8601 strings (must start with a valid date)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"Invalid date: {value}. Use YYYY-MM-DD or ISO 8601.") from e

    return value
