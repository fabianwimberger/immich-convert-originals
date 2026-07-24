"""Run execution: resolves an asset list and processes it through the
download -> transcode -> upload -> copy-metadata -> delete pipeline,
persisting per-asset outcomes and broadcasting live progress.

_process_asset_sync is a direct port of the old CLI's app/main.py
process_asset() (git history has the original). The async layer around it
is new: asyncio.to_thread for the blocking client/transcode calls, a
semaphore for concurrency, AssetOutcome rows instead of a flat state.db,
and WebSocket broadcasts instead of tqdm/logging.
"""

import asyncio
import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.asset_outcome import FINAL_STATUSES, AssetOutcome
from app.models.run import Run
from app.services.immich_client import Asset, ImmichClient
from app.services.transcode import (
    transcode,
    transcode_video,
    validate_output,
    validate_video_output,
)
from app.services.websocket_manager import websocket_manager

logger = logging.getLogger(__name__)

_cancelled_runs: set[int] = set()

# Concurrent assets each persist their outcome in their own transaction; SQLite
# serializes the writes, but that commit order isn't guaranteed to match the
# order in which each asset's asyncio task resumes afterwards. Without this
# lock, two assets finishing close together can broadcast run_progress out of
# commit order, making the displayed counters briefly jump backwards.
_progress_locks: dict[int, asyncio.Lock] = {}

# run_progress carries the same aggregate counters on every asset -- sending
# it once per asset is wasted work once a run is processing hundreds of
# assets a second (fast skips have no I/O to pace them). Throttling it still
# leaves the live per-asset log (asset_progress) untouched; the true final
# counters are always attached to run_completed regardless of throttling.
PROGRESS_BROADCAST_INTERVAL = 0.2
_last_progress_broadcast: dict[int, float] = {}


def request_cancel(run_id: int) -> None:
    _cancelled_runs.add(run_id)


def _is_cancelled(run_id: int) -> bool:
    return run_id in _cancelled_runs


def _get_target_format(asset: Asset, cfg: dict[str, Any]) -> str:
    if asset.type == "VIDEO":
        return "mp4"
    return cfg.get("image_target_format", "jxl")


def _get_image_quality(
    cfg: dict[str, Any], target_format: str, *, retry: bool
) -> float:
    """Resolves the quality/distance value for the given target format.

    JXL uses distance (0-25, lower=better); HEIC/AVIF use ImageMagick
    -quality (0-100, higher=better) -- not the same scale, so each format
    keeps its own setting rather than sharing one field.
    """
    if target_format == "heic":
        key = "image_quality_heic_retry" if retry else "image_quality_heic"
        return cfg.get(key, 60 if retry else 80)
    if target_format == "avif":
        key = "image_quality_avif_retry" if retry else "image_quality_avif"
        return cfg.get(key, 55 if retry else 75)
    key = "image_distance_retry" if retry else "image_distance"
    return cfg.get(key, 2.0 if retry else 1.0)


# Best-effort format guess from Immich metadata alone (mime type, then
# filename extension), so an excluded format can be skipped before spending
# any bandwidth downloading it. Mirrors transcode.detect_format()'s magic-byte
# detection, just working off what the Immich API already told us instead of
# file contents.
_FORMAT_MIME_MAP = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
    "image/heif": "heic",
    "image/avif": "avif",
    "image/tiff": "tiff",
    "image/gif": "gif",
    "image/bmp": "bmp",
}
_FORMAT_EXTENSION_MAP = {
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".png": "png",
    ".webp": "webp",
    ".heic": "heic",
    ".heif": "heic",
    ".avif": "avif",
    ".tiff": "tiff",
    ".tif": "tiff",
    ".gif": "gif",
    ".bmp": "bmp",
}

# Matches Settings.convert_image_formats' default (models/settings.py) -- used
# as the fallback here too, so a config_snapshot persisted before this setting
# existed (e.g. retry-failed on an old run) still converts every format
# instead of KeyError-ing or skipping everything.
ALL_IMAGE_FORMATS = "jpg,png,webp,heic,avif,tiff,gif,bmp"


def _detect_image_format_from_metadata(asset: Asset) -> str | None:
    mime_type = asset.original_mime_type.lower() if asset.original_mime_type else None
    if mime_type in _FORMAT_MIME_MAP:
        return _FORMAT_MIME_MAP[mime_type]
    _, ext = os.path.splitext(asset.original_file_name.lower())
    return _FORMAT_EXTENSION_MAP.get(ext)


def _should_skip_by_mime_type(asset: Asset, cfg: dict[str, Any]) -> str | None:
    """Returns a skip reason if this image shouldn't be processed, else None."""
    if asset.type != "IMAGE":
        return None

    mime_type = asset.original_mime_type.lower() if asset.original_mime_type else None
    is_jxl = mime_type == "image/jxl" or asset.original_file_name.lower().endswith(
        ".jxl"
    )
    if is_jxl:
        return "Already JPEG XL"

    detected = _detect_image_format_from_metadata(asset)
    allowed_formats = set(
        cfg.get("convert_image_formats", ALL_IMAGE_FORMATS).split(",")
    )
    if detected is not None and detected not in allowed_formats:
        return "Format excluded by settings"

    return None


def _process_asset_sync(
    asset: Asset, client: ImmichClient, cfg: dict[str, Any], work_dir: str
) -> dict[str, Any]:
    """Blocking pipeline for a single asset. Runs on a worker thread."""
    input_path = ""
    output_path = ""
    result: dict[str, Any] = {
        "status": "unknown",
        "input_bytes": 0,
        "output_bytes": 0,
    }

    is_video = asset.type == "VIDEO"
    target_format = _get_target_format(asset, cfg)
    result["target_format"] = target_format
    dry_run = cfg["dry_run"]

    if not is_video:
        skip_reason = _should_skip_by_mime_type(asset, cfg)
        if skip_reason:
            result["status"] = "skipped"
            result["error"] = skip_reason
            return result

    try:
        input_path = os.path.join(work_dir, f"{asset.id}.bin")
        output_path = os.path.join(work_dir, f"{asset.id}.{target_format}")

        input_bytes, error = client.download_original(asset.id, input_path)
        if error:
            result["status"] = "failed_download"
            result["error"] = error
            return result
        if input_bytes == 0:
            result["status"] = "failed_download"
            result["error"] = "Downloaded file is empty"
            return result
        result["input_bytes"] = input_bytes

        if is_video:
            tx = transcode_video(
                input_path,
                output_path,
                crf=cfg["video_crf"],
                preset=str(cfg["video_preset"]),
                max_dimension=cfg["video_max_dimension"],
                audio_bitrate=cfg["video_audio_bitrate"],
            )
            is_valid = validate_video_output(output_path)
        else:
            tx = transcode(
                input_path,
                output_path,
                target_format,
                _get_image_quality(cfg, target_format, retry=False),
            )
            is_valid = validate_output(output_path, target_format)

        if not tx.success:
            # No output was produced, so input_bytes must not carry a
            # before/after size comparison -- otherwise the UI reads
            # "output_bytes stayed 0" as "100% saved by producing nothing".
            result["input_bytes"] = 0
            if tx.error and tx.error.startswith("Already "):
                result["status"] = "skipped"
                return result
            result["status"] = "failed_transcode"
            result["error"] = tx.error
            return result
        if not is_valid:
            result["input_bytes"] = 0
            result["status"] = "failed_transcode"
            result["error"] = "Output validation failed"
            return result

        output_bytes = tx.output_bytes
        result["output_bytes"] = output_bytes

        if output_bytes > input_bytes:
            if cfg["allow_larger"]:
                pass
            elif cfg["enable_retry"]:
                if is_video:
                    tx = transcode_video(
                        input_path,
                        output_path,
                        crf=cfg["video_crf_retry"],
                        preset=str(cfg["video_preset"]),
                        max_dimension=cfg["video_max_dimension"],
                        audio_bitrate=cfg["video_audio_bitrate"],
                    )
                    is_valid = validate_video_output(output_path)
                else:
                    tx = transcode(
                        input_path,
                        output_path,
                        target_format,
                        _get_image_quality(cfg, target_format, retry=True),
                    )
                    is_valid = validate_output(output_path, target_format)

                if not tx.success or not is_valid:
                    result["status"] = "skipped"
                    return result

                output_bytes = tx.output_bytes
                result["output_bytes"] = output_bytes

                if output_bytes > input_bytes and not cfg["accept_retry_output"]:
                    result["status"] = "skipped"
                    return result
            else:
                result["status"] = "skipped"
                return result

        if dry_run:
            # Real download + transcode already ran above, so this reflects
            # the actual size a real run would produce -- just stop short of
            # touching the user's Immich library.
            result["status"] = "dry_run_preview"
            return result

        base_name = os.path.splitext(asset.original_file_name)[0]
        new_filename = f"{base_name}.{target_format}"

        new_asset_id, error = client.upload_asset(
            file_path=output_path,
            file_created_at=asset.file_created_at,
            file_modified_at=asset.file_modified_at,
            filename=new_filename,
        )
        if error or not new_asset_id:
            result["status"] = "failed_upload"
            result["error"] = error
            return result
        result["new_asset_id"] = new_asset_id

        success, error = client.copy_asset_data(
            from_asset_id=asset.id, to_asset_id=new_asset_id
        )
        if not success:
            client.delete_assets([new_asset_id])
            result["status"] = "failed_copy"
            result["error"] = error
            return result

        verified, verify_error = client.get_asset(new_asset_id)
        if not verified:
            client.delete_assets([new_asset_id])
            result["status"] = "failed_verification"
            result["error"] = verify_error
            return result

        success, error = client.delete_assets([asset.id])
        if not success:
            result["status"] = "partial_success"
            result["error"] = error
            return result

        result["status"] = "success"
        return result

    finally:
        for path in (input_path, output_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning("Failed to clean up %s: %s", path, e)


async def _resolve_assets(client: ImmichClient, cfg: dict[str, Any]) -> list[Asset]:
    if cfg.get("asset_ids"):
        fetched = await asyncio.gather(
            *[
                asyncio.to_thread(client.get_asset_full, asset_id)
                for asset_id in cfg["asset_ids"]
            ]
        )
        return [a for a in fetched if a is not None]

    assets = []
    if cfg.get("album_id"):
        album_assets = await asyncio.to_thread(client.get_album_assets, cfg["album_id"])
        asset_types = cfg["asset_types"].split(",")
        assets = [a for a in album_assets if a.type in asset_types]
        if cfg.get("taken_after"):
            assets = [a for a in assets if a.file_created_at >= cfg["taken_after"]]
        if cfg.get("taken_before"):
            assets = [a for a in assets if a.file_created_at <= cfg["taken_before"]]
    else:
        for atype in cfg["asset_types"].split(","):
            page = 1
            while True:
                page_assets = await asyncio.to_thread(
                    client.search_assets,
                    page=page,
                    size=500,
                    asset_type=atype,
                    with_archived=cfg["include_archived"],
                    with_deleted=cfg["include_deleted"],
                    original_filename=cfg.get("original_filename"),
                    taken_after=cfg.get("taken_after"),
                    taken_before=cfg.get("taken_before"),
                )
                if not page_assets:
                    break
                assets.extend(page_assets)
                page += 1

    if not cfg.get("skip_done_filter"):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(AssetOutcome.asset_id, AssetOutcome.status).order_by(
                    AssetOutcome.updated_at.desc()
                )
            )
            latest_status: dict[str, str] = {}
            for asset_id, status in result.all():
                latest_status.setdefault(asset_id, status)
        done_ids = {aid for aid, s in latest_status.items() if s in FINAL_STATUSES}
        assets = [a for a in assets if a.id not in done_ids]

    max_assets = cfg.get("max_assets")
    if max_assets:
        assets = assets[:max_assets]

    return assets


async def _persist_asset_result(
    run_id: int, asset: Asset, result: dict[str, Any]
) -> dict[str, int]:
    """Write the asset's outcome row and bump the run's counters/byte totals
    in a single transaction, instead of three separate connections/commits.
    Under fast, I/O-less skips this used to be the bottleneck: three SQLite
    writers per asset competing for one file lock."""
    status = result["status"]
    input_bytes = result.get("input_bytes", 0)
    output_bytes = result.get("output_bytes", 0)

    increments: dict[str, Any] = {"processed_count": Run.processed_count + 1}
    if status in ("success", "partial_success", "dry_run_preview"):
        increments["success_count"] = Run.success_count + 1
    elif status == "skipped":
        increments["skipped_count"] = Run.skipped_count + 1
    else:
        increments["failed_count"] = Run.failed_count + 1
    if input_bytes or output_bytes:
        increments["input_bytes"] = Run.input_bytes + input_bytes
        increments["output_bytes"] = Run.output_bytes + output_bytes

    async with AsyncSessionLocal() as db:
        outcome = AssetOutcome(
            run_id=run_id,
            asset_id=asset.id,
            filename=asset.original_file_name,
            status=status,
            error=result.get("error"),
            new_asset_id=result.get("new_asset_id"),
            target_format=result.get("target_format"),
            input_bytes=input_bytes,
            output_bytes=output_bytes,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(outcome)
        await db.execute(update(Run).where(Run.id == run_id).values(**increments))
        result_row = await db.execute(select(Run).where(Run.id == run_id))
        run = result_row.scalar_one()
        counters = {
            "processed_count": run.processed_count,
            "success_count": run.success_count,
            "skipped_count": run.skipped_count,
            "failed_count": run.failed_count,
            "total_assets": run.total_assets,
        }
        await db.commit()
        return counters


async def _run_one_asset(
    run_id: int,
    asset: Asset,
    client: ImmichClient,
    cfg: dict[str, Any],
    work_dir: str,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        if _is_cancelled(run_id):
            return

        await websocket_manager.broadcast(
            {
                "type": "asset_progress",
                "run_id": run_id,
                "asset_id": asset.id,
                "filename": asset.original_file_name,
                "stage": "processing",
            }
        )

        try:
            result = await asyncio.to_thread(
                _process_asset_sync, asset, client, cfg, work_dir
            )
        except Exception as e:
            # asyncio.gather() doesn't cancel sibling tasks when one of them
            # raises -- letting this propagate would make execute_run's
            # except/finally run work_dir cleanup while other assets are
            # still mid-download into that same directory.
            logger.exception("Unhandled error processing asset %s", asset.id)
            result = {
                "status": "failed_error",
                "error": str(e),
                "target_format": _get_target_format(asset, cfg),
            }

        lock = _progress_locks.setdefault(run_id, asyncio.Lock())
        async with lock:
            try:
                counters = await _persist_asset_result(run_id, asset, result)
            except Exception:
                logger.exception("Failed to persist outcome for asset %s", asset.id)
                return

            await websocket_manager.broadcast(
                {
                    "type": "asset_progress",
                    "run_id": run_id,
                    "asset_id": asset.id,
                    "filename": asset.original_file_name,
                    "stage": "done",
                    "status": result["status"],
                    "error": result.get("error"),
                    "target_format": result.get("target_format"),
                    "input_bytes": result.get("input_bytes", 0),
                    "output_bytes": result.get("output_bytes", 0),
                }
            )

            now = time.monotonic()
            last_sent = _last_progress_broadcast.get(run_id, 0.0)
            if now - last_sent >= PROGRESS_BROADCAST_INTERVAL:
                _last_progress_broadcast[run_id] = now
                await websocket_manager.broadcast(
                    {"type": "run_progress", "run_id": run_id, **counters}
                )


async def execute_run(run_id: int) -> None:
    """Main entry point, called by run_queue's worker."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one_or_none()
        if run is None or run.status == "cancelled":
            # Already cancelled while still queued (see routes/runs.py).
            # Must still discard here, or a cancelled-while-queued id that
            # never reaches the try/finally below leaks in _cancelled_runs
            # forever and can collide with a future run reusing that id.
            _cancelled_runs.discard(run_id)
            return
        cfg = json.loads(run.config_snapshot)

    api_base = cfg["immich_api_base"]
    if not api_base.endswith("/"):
        api_base += "/"
    client = ImmichClient(api_base=api_base, api_key=cfg["immich_api_key"])

    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(status="running", started_at=datetime.now(timezone.utc))
        )
        await db.commit()
    await websocket_manager.broadcast({"type": "run_started", "run_id": run_id})

    work_dir = os.path.join(
        os.environ.get("TEMP_DIR", "/app/temp"), f"run_{run_id}_{uuid.uuid4().hex[:8]}"
    )
    os.makedirs(work_dir, exist_ok=True)

    error_message = None
    try:
        assets = await _resolve_assets(client, cfg)

        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Run).where(Run.id == run_id).values(total_assets=len(assets))
            )
            await db.commit()

        if assets:
            semaphore = asyncio.Semaphore(max(1, cfg.get("concurrency", 2)))
            await asyncio.gather(
                *[
                    _run_one_asset(run_id, asset, client, cfg, work_dir, semaphore)
                    for asset in assets
                ]
            )
    except Exception as e:
        logger.exception("Run %s failed", run_id)
        error_message = str(e)
    finally:
        # Read the cancellation flag before discarding it -- discard first
        # would always read back False here, so a cancelled run could never
        # actually end up with final_status == "cancelled".
        was_cancelled = _is_cancelled(run_id)
        shutil.rmtree(work_dir, ignore_errors=True)
        _cancelled_runs.discard(run_id)
        _progress_locks.pop(run_id, None)
        _last_progress_broadcast.pop(run_id, None)

    final_status = (
        "cancelled" if was_cancelled else ("failed" if error_message else "completed")
    )
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status=final_status,
                completed_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
        result = await db.execute(select(Run).where(Run.id == run_id))
        run = result.scalar_one()
        counters = {
            "processed_count": run.processed_count,
            "success_count": run.success_count,
            "skipped_count": run.skipped_count,
            "failed_count": run.failed_count,
            "total_assets": run.total_assets,
        }
        await db.commit()
    await websocket_manager.broadcast(
        {"type": "run_completed", "run_id": run_id, "status": final_status, **counters}
    )
